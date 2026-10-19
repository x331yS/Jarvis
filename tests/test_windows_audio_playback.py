from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from jarvis.utils import windows_audio


def test_playback_resolves_fresh_windows_default_without_resetting_capture(monkeypatch):
    selected = SimpleNamespace(FriendlyName="Speakers (Focusrite USB Audio)")
    api = SimpleNamespace(GetSpeakers=lambda: selected)
    monkeypatch.setattr(windows_audio, "audio_session", lambda: nullcontext((api, [])))
    monkeypatch.setattr(windows_audio.sys, "platform", "win32")
    import sounddevice
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [
        {"name": "Speakers (SOULION R100)", "max_output_channels": 2, "hostapi": 0},
        {"name": selected.FriendlyName, "max_output_channels": 2, "hostapi": 0},
        {"name": selected.FriendlyName, "max_output_channels": 0, "hostapi": 0},
    ])
    monkeypatch.setattr(sounddevice, "query_hostapis", lambda index: {"name": "Windows DirectSound"})
    assert windows_audio.playback_device() == 1
    selected.FriendlyName = "Speakers (SOULION R100)"
    assert windows_audio.playback_device() == 0


def test_missing_playback_endpoint_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(windows_audio.sys, "platform", "win32")
    monkeypatch.setattr(windows_audio, "audio_session", lambda: nullcontext((
        SimpleNamespace(GetSpeakers=lambda: None), [],
    )))
    with pytest.raises(OSError, match="default playback"):
        windows_audio.playback_device()
