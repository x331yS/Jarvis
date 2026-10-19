"""Behavioural tests for the thinking-tune player.

Covers:
- Sample / WAV generation: one short pulse with quiet endpoints.
- TunePlayer lifecycle: idempotent start/stop, is_playing state, prompt
  stop even when a "stream" is running.
- Sounddevice dispatch: stop_tune closes the stream cleanly from the
  owning thread (no cross-thread abort — that races with close on
  macOS CoreAudio and logs a spurious !obj error).

The sounddevice stream is exercised via a fake `sounddevice` module
injected into sys.modules — works headlessly in CI.
"""
from __future__ import annotations

import io
import struct
import sys
import time
import types
import wave
import threading
import numpy as np
from unittest.mock import MagicMock

import pytest

from jarvis.output import tune_player
from jarvis.output.tune_player import (
    TunePlayer,
    _generate_thinking_pad_samples,
    _generate_thinking_pad_wav,
    _get_thinking_pad_samples,
    _get_thinking_pad_wav,
)


# --- Sample / WAV generation -----------------------------------------------

def test_thinking_pad_samples_have_expected_shape():
    samples, rate = _generate_thinking_pad_samples()
    assert rate == 44100
    assert samples.dtype.name == "int16"
    assert samples.ndim == 1
    assert 0 < samples.size / rate <= 1.5


def test_thinking_pad_wav_is_well_formed():
    data = _generate_thinking_pad_wav()
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 44100


def test_thinking_pad_samples_cached():
    a = _get_thinking_pad_samples()
    b = _get_thinking_pad_samples()
    assert a is b


def test_thinking_pad_wav_cached():
    assert _get_thinking_pad_wav() is _get_thinking_pad_wav()


def test_thinking_pulse_has_quiet_endpoints():
    samples, _ = _generate_thinking_pad_samples()
    first = int(samples[0])
    last = int(samples[-1])
    # Seam step must be well under full-scale; observed ≈ 500.
    assert abs(first - last) < 0.05 * 32767


def test_thinking_pulse_decays_without_another_attack():
    samples, rate = _generate_thinking_pad_samples()
    win = rate // 10  # 100ms windows
    peaks = [
        int(abs(samples[i : i + win]).max())
        for i in range(0, samples.size - win, win)
    ]
    assert max(peaks) > 0.10 * 32767
    assert peaks[-1] < peaks[0] * 0.05


# --- TunePlayer lifecycle --------------------------------------------------

class _FakeStream:
    """Minimal sounddevice.OutputStream stand-in."""

    def __init__(self, *args, **kwargs):
        self.started = False
        self.aborted = False
        self.closed = False
        self._callback = kwargs.get("callback")

    def start(self):
        self.started = True

    def abort(self):
        self.aborted = True

    def close(self):
        self.closed = True


def _install_fake_sounddevice(monkeypatch, stream_factory=None):
    """Inject a fake sounddevice module that records the created stream."""
    created = {}

    def _OutputStream(*args, **kwargs):
        stream = (stream_factory or _FakeStream)(*args, **kwargs)
        created["stream"] = stream
        return stream

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.OutputStream = _OutputStream
    fake_sd.CallbackStop = type("CallbackStop", (Exception,), {})
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    return created


def test_disabled_player_never_starts():
    tp = TunePlayer(enabled=False)
    tp.start_tune()
    try:
        assert not tp.is_playing()
        assert tp._thread is None
    finally:
        tp.stop_tune()

def test_stop_is_idempotent():
    tp = TunePlayer(enabled=False)
    tp.stop_tune()
    tp.stop_tune()


def test_double_start_is_ignored(monkeypatch):
    _install_fake_sounddevice(monkeypatch)
    tp = TunePlayer(enabled=True)
    tp.start_tune()
    first = tp._thread
    try:
        tp.start_tune()
        assert tp._thread is first
    finally:
        tp.stop_tune()


def test_stop_closes_the_stream_and_returns_quickly(monkeypatch):
    created = _install_fake_sounddevice(monkeypatch)
    tp = TunePlayer(enabled=True)
    tp.start_tune()

    # Wait until the stream is actually started.
    for _ in range(100):
        stream = created.get("stream")
        if stream is not None and stream.started:
            break
        time.sleep(0.01)
    stream = created.get("stream")
    assert stream is not None and stream.started

    t0 = time.time()
    tp.stop_tune()
    elapsed = time.time() - t0

    # Only the tune thread closes the stream; stop_tune must NOT abort
    # from the caller's thread — that races with close() on macOS.
    assert stream.closed
    assert not stream.aborted
    assert elapsed < 1.0
    assert not tp.is_playing()


def test_fallback_when_sounddevice_unavailable(monkeypatch):
    # Force the sounddevice import inside _play_tune to fail.
    fake_sd = types.ModuleType("sounddevice_broken")

    def _raise(*a, **kw):
        raise RuntimeError("no audio here")

    fake_sd.OutputStream = _raise
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    tp = TunePlayer(enabled=True)
    tp.start_tune()
    # Give the thread a moment to reach the fallback loop.
    for _ in range(50):
        if tp.is_playing():
            break
        time.sleep(0.01)
    assert tp.is_playing()

    t0 = time.time()
    tp.stop_tune()
    elapsed = time.time() - t0
    assert elapsed < 1.5
    assert not tp.is_playing()


def test_pulse_finishes_releases_output_and_stays_silent_until_next_request(monkeypatch):
    captured = {}
    finished = threading.Event()

    class _SpyStream(_FakeStream):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            captured["callback"] = kw.get("callback")
            self.finished_callback = kw.get("finished_callback")

        def close(self):
            super().close()
            finished.set()

    created = _install_fake_sounddevice(monkeypatch, stream_factory=_SpyStream)
    tp = TunePlayer(enabled=True)
    tp.start_tune()
    try:
        for _ in range(100):
            if captured.get("callback") is not None:
                break
            time.sleep(0.01)
        cb = captured["callback"]
        assert cb is not None

        samples, _ = _get_thinking_pad_samples()
        frames = 1024
        output = []
        for _ in range(samples.size // frames + 2):
            out = np.full((frames, 1), -1, dtype=np.int16)
            try:
                cb(out, frames, None, None)
            except sys.modules["sounddevice"].CallbackStop:
                output.extend(out[:, 0])
                break
            output.extend(out[:, 0])
        else:
            pytest.fail("The pulse must finish rather than loop")
        np.testing.assert_array_equal(output[:samples.size], samples)
        assert not any(output[samples.size:])
        created_stream = created["stream"]
        created_stream.finished_callback()
        assert finished.wait(1), "Output must be released without waiting for the response"
        assert not tp.is_playing()
        tp.start_tune()
        assert created["stream"] is created_stream, "Repeated start in one request must stay silent"
    finally:
        tp.stop_tune()

    tp.start_tune()
    try:
        deadline = time.monotonic() + 1
        while created["stream"] is created_stream and time.monotonic() < deadline:
            time.sleep(0.01)
        assert created["stream"] is not created_stream, "The next request can play its own pulse"
    finally:
        tp.stop_tune()
