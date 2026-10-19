from __future__ import annotations
import io
import struct
import threading
import time
from typing import Optional

import numpy as np

from ..debug import debug_log
from ..utils.audio_lock import portaudio_lock


def _generate_thinking_pad_samples() -> tuple[np.ndarray, int]:
    """Generate one short, decaying acknowledgement pulse as int16 mono."""
    sample_rate = 44100
    duration_s = 1.0
    attack_s = 0.008

    chord_roots = (220, 275, 330)
    unison_offsets = (-1, 0, 1)

    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float64) / sample_rate
    two_pi = 2 * np.pi

    attack_len = max(1, int(sample_rate * attack_s))
    envelope = np.zeros(n, dtype=np.float64)
    envelope[:attack_len] = np.linspace(0.0, 1.0, attack_len)
    envelope[attack_len:] = np.exp(-6.0 * np.linspace(0.0, 1.0, n - attack_len))
    fade_len = int(sample_rate * 0.03)
    envelope[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)

    # Build the triad once: three pure sines per chord tone with ±1 Hz
    # unison detune for the characteristic beat.
    tone = np.zeros(n, dtype=np.float64)
    for root in chord_roots:
        for offset in unison_offsets:
            f = root + offset
            tone += np.sin(two_pi * f * t)
    peak = float(np.max(np.abs(tone))) or 1.0
    tone = tone / peak

    signal = tone * envelope * 0.38

    samples = np.clip(signal * 32767, -32768, 32767).astype(np.int16)
    return samples, sample_rate


def _generate_thinking_pad_wav() -> bytes:
    """WAV-wrapped version of the thinking pad (kept for test coverage)."""
    samples, sample_rate = _generate_thinking_pad_samples()
    num_samples = samples.size

    wav_buffer = io.BytesIO()
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align

    wav_buffer.write(b'RIFF')
    wav_buffer.write(struct.pack('<I', 36 + data_size))
    wav_buffer.write(b'WAVE')

    wav_buffer.write(b'fmt ')
    wav_buffer.write(struct.pack('<I', 16))
    wav_buffer.write(struct.pack('<H', 1))
    wav_buffer.write(struct.pack('<H', num_channels))
    wav_buffer.write(struct.pack('<I', sample_rate))
    wav_buffer.write(struct.pack('<I', byte_rate))
    wav_buffer.write(struct.pack('<H', block_align))
    wav_buffer.write(struct.pack('<H', bits_per_sample))

    wav_buffer.write(b'data')
    wav_buffer.write(struct.pack('<I', data_size))
    wav_buffer.write(samples.tobytes())

    return wav_buffer.getvalue()


_THINKING_PAD_WAV: Optional[bytes] = None
_THINKING_PAD_SAMPLES: Optional[tuple[np.ndarray, int]] = None


def _get_thinking_pad_wav() -> bytes:
    """Get cached thinking-pad WAV data, generating on first call."""
    global _THINKING_PAD_WAV
    if _THINKING_PAD_WAV is None:
        _THINKING_PAD_WAV = _generate_thinking_pad_wav()
    return _THINKING_PAD_WAV


def _get_thinking_pad_samples() -> tuple[np.ndarray, int]:
    """Get cached raw int16 samples for sounddevice playback."""
    global _THINKING_PAD_SAMPLES
    if _THINKING_PAD_SAMPLES is None:
        _THINKING_PAD_SAMPLES = _generate_thinking_pad_samples()
    return _THINKING_PAD_SAMPLES


def _prewarm_cache() -> None:
    """Pre-generate samples off the hot path so the first start_tune()
    doesn't compete with the first LLM call for CPU."""
    try:
        _get_thinking_pad_samples()
    except Exception as exc:
        debug_log(f"thinking tune: prewarm failed: {exc!r}", category="tune")


threading.Thread(target=_prewarm_cache, daemon=True).start()


class TunePlayer:
    """Plays one acknowledgement pulse per processing request.

    Uses sounddevice (PortAudio) for playback, which is the same API TTS
    uses. This matters: if the tune held the audio output device via a
    separate path (e.g. afplay subprocess killed mid-stream), macOS
    CoreAudio could take seconds to release the device, stalling TTS.
    Using one API means clean release — stop returns in milliseconds and
    TTS can open the device immediately after.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_playing = threading.Event()

    def start_tune(self) -> None:
        if not self.enabled or self._thread is not None:
            return

        debug_log("thinking tune: start", category="tune")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._play_tune, daemon=True)
        self._thread.start()

    def stop_tune(self) -> None:
        """Stop the tune immediately, releasing the audio device.

        We deliberately do NOT call ``stream.abort()`` from this thread —
        only the tune thread (`_play_tune`'s finally block) touches the
        stream. Calling abort() here and then close() over there races on
        macOS: PortAudio/CoreAudio emits a spurious
        ``||PaMacCore (AUHAL)|| Error … err=''!obj''`` on every stop
        because the AudioObject is being torn down twice. Setting the
        stop event is enough — `stream.close()` discards pending buffers
        as if abort() had been called.
        """
        if self._thread is None:
            return

        debug_log("thinking tune: stop", category="tune")
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        self._thread = None
        self._is_playing.clear()

    def is_playing(self) -> bool:
        return self._is_playing.is_set()

    def _play_tune(self) -> None:
        self._is_playing.set()
        try:
            try:
                import sounddevice as sd
            except Exception as exc:
                debug_log(f"thinking tune: sounddevice unavailable: {exc!r}", category="tune")
                self._play_fallback_tune()
                return

            try:
                samples, sample_rate = _get_thinking_pad_samples()
            except Exception as exc:
                debug_log(f"thinking tune: sample generation failed: {exc!r}", category="tune")
                self._play_fallback_tune()
                return

            position = [0]  # list so the callback closure can mutate it
            total = samples.size
            playback_finished = threading.Event()

            def callback(outdata, frames, time_info, status):
                # No I/O here — this runs in the realtime audio thread.
                start = position[0]
                count = min(frames, total - start)
                outdata.fill(0)
                outdata[:count, 0] = samples[start:start + count]
                position[0] += count
                if position[0] >= total:
                    raise sd.CallbackStop

            try:
                with portaudio_lock:
                    stream = sd.OutputStream(
                        samplerate=sample_rate,
                        channels=1,
                        dtype='int16',
                        # Large block + high latency: fewer callbacks, fewer
                        # GIL acquisitions, lighter touch on the rest of the
                        # app. 8192 frames ≈ 186ms per wakeup vs 23ms before.
                        blocksize=8192,
                        latency='high',
                        callback=callback,
                        finished_callback=playback_finished.set,
                    )
            except Exception as exc:
                debug_log(f"thinking tune: stream open failed: {exc!r}", category="tune")
                self._play_fallback_tune()
                return

            try:
                with portaudio_lock:
                    stream.start()
                while not self._stop_event.is_set():
                    if playback_finished.wait(0.05):
                        debug_log("thinking tune: pulse complete, waiting silently for response", category="tune")
                        break
            except Exception as exc:
                debug_log(f"thinking tune: stream playback failed: {exc!r}", category="tune")
            finally:
                try:
                    with portaudio_lock:
                        stream.close()
                except Exception as exc:
                    debug_log(f"thinking tune: stream close failed: {exc!r}", category="tune")
        finally:
            self._is_playing.clear()

    def _play_fallback_tune(self) -> None:
        """Fallback for environments without a usable audio output."""
        patterns = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while not self._stop_event.is_set():
            try:
                print(f"\r[jarvis] {patterns[i % len(patterns)]} processing...",
                      end="", flush=True)
                time.sleep(0.2)
                i += 1
            except Exception:
                break
        try:
            print("\r" + " " * 30 + "\r", end="", flush=True)
        except Exception:
            pass
