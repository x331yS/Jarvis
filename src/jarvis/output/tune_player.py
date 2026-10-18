from __future__ import annotations
import threading
import time
from typing import Optional

import numpy as np

from ..debug import debug_log
from ..utils.audio_lock import portaudio_lock


def _generate_acknowledgement_cue_samples() -> tuple[np.ndarray, int]:
    """Generate the acknowledgement cue as a raw int16 mono buffer.

    A single soft "doum": an A major triad (A3 / C#4 / E4) with ±1 Hz
    unison detune for warmth, a fast attack and an exponential decay to
    silence. It plays once when Jarvis accepts a request, so the user
    knows they were heard without a repeating pulse during long replies.

    Returns (int16 mono samples, sample_rate).
    """
    sample_rate = 44100
    tone_s = 1.0
    attack_s = 0.008

    chord_roots = (220, 275, 330)
    unison_offsets = (-1, 0, 1)

    n = int(sample_rate * tone_s)
    t = np.arange(n, dtype=np.float64) / sample_rate
    two_pi = 2 * np.pi

    attack_len = max(1, int(sample_rate * attack_s))
    envelope = np.empty(n, dtype=np.float64)
    envelope[:attack_len] = np.linspace(0.0, 1.0, attack_len, endpoint=True)
    decay_len = n - attack_len
    envelope[attack_len:] = np.exp(-6.0 * np.arange(decay_len) / decay_len)
    # Short linear fade so the buffer ends exactly at zero (no click).
    fade_len = sample_rate // 50
    envelope[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, endpoint=True)

    tone = np.zeros(n, dtype=np.float64)
    for root in chord_roots:
        for offset in unison_offsets:
            tone += np.sin(two_pi * (root + offset) * t)
    peak = float(np.max(np.abs(tone))) or 1.0
    signal = tone / peak * envelope * 0.38

    samples = np.clip(signal * 32767, -32768, 32767).astype(np.int16)
    return samples, sample_rate


_ACKNOWLEDGEMENT_CUE_SAMPLES: Optional[tuple[np.ndarray, int]] = None


def _get_acknowledgement_cue_samples() -> tuple[np.ndarray, int]:
    """Get cached raw int16 samples for sounddevice playback."""
    global _ACKNOWLEDGEMENT_CUE_SAMPLES
    if _ACKNOWLEDGEMENT_CUE_SAMPLES is None:
        _ACKNOWLEDGEMENT_CUE_SAMPLES = _generate_acknowledgement_cue_samples()
    return _ACKNOWLEDGEMENT_CUE_SAMPLES


def _prewarm_cache() -> None:
    """Pre-generate samples off the hot path so the first start_tune()
    doesn't compete with the first LLM call for CPU."""
    try:
        _get_acknowledgement_cue_samples()
    except Exception as exc:
        debug_log(f"thinking tune: prewarm failed: {exc!r}", category="tune")


threading.Thread(target=_prewarm_cache, daemon=True).start()


class TunePlayer:
    """Plays the acknowledgement cue once when Jarvis starts processing.

    The stream stays open (silent) until ``stop_tune`` so repeated starts
    during one request do not replay the cue.

    Uses sounddevice (PortAudio) for playback, which is the same API TTS
    uses. This matters: if the tune held the audio output device via a
    separate path (e.g. afplay subprocess killed mid-stream), macOS
    CoreAudio could take seconds to release the device, stalling TTS.
    The owning worker releases the device; stop uses a bounded wait and
    another tune starts only after teardown finishes.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._is_playing = threading.Event()

    def start_tune(self) -> None:
        with self._lifecycle_lock:
            if not self.enabled or self._thread is not None:
                return

            debug_log("thinking tune: start", category="tune")
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._play_tune, daemon=True)
            try:
                self._thread.start()
            except Exception as exc:
                self._thread = None
                debug_log(f"thinking tune: worker creation failed: {exc!r}", category="tune")
                raise

    def stop_tune(self) -> None:
        """Request stop and wait briefly for audio teardown.

        We deliberately do NOT call ``stream.abort()`` from this thread —
        only the tune thread (`_play_tune`'s finally block) touches the
        stream. Calling abort() here and then close() over there races on
        macOS: PortAudio/CoreAudio emits a spurious
        ``||PaMacCore (AUHAL)|| Error … err=''!obj''`` on every stop
        because the AudioObject is being torn down twice. Setting the
        stop event is enough — `stream.close()` discards pending buffers
        as if abort() had been called.
        """
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return
            debug_log("thinking tune: stop", category="tune")
            self._stop_event.set()

        thread.join(timeout=1.0)
        with self._lifecycle_lock:
            if self._thread is thread:
                debug_log("thinking tune: audio teardown pending; restart deferred", category="tune")

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
                samples, sample_rate = _get_acknowledgement_cue_samples()
            except Exception as exc:
                debug_log(f"thinking tune: sample generation failed: {exc!r}", category="tune")
                self._play_fallback_tune()
                return

            position = [0]  # list so the callback closure can mutate it
            total = samples.size

            def callback(outdata, frames, time_info, status):
                # No I/O here — this runs in the realtime audio thread.
                start = min(position[0], total)
                played = min(frames, total - start)
                outdata[:played, 0] = samples[start:start + played]
                outdata[played:, 0] = 0
                position[0] = start + played

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
                    )
            except Exception as exc:
                debug_log(f"thinking tune: stream open failed: {exc!r}", category="tune")
                self._play_fallback_tune()
                return

            try:
                with portaudio_lock:
                    stream.start()
                # Hand off to the OS audio thread. Wake when stop is
                # requested — no polling loop, no per-iteration gap.
                self._stop_event.wait()
            except Exception as exc:
                debug_log(f"thinking tune: stream playback failed: {exc!r}", category="tune")
            finally:
                try:
                    with portaudio_lock:
                        stream.close()
                except Exception as exc:
                    debug_log(f"thinking tune: stream close failed: {exc!r}", category="tune")
        finally:
            with self._lifecycle_lock:
                self._thread = None
                self._is_playing.clear()
            debug_log("thinking tune: worker finished", category="tune")

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
