import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from jarvis.tools.builtin import system_audio


class Volume:
    def __init__(self, level):
        self.level = level

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def SetMasterVolumeLevelScalar(self, level, event):
        self.level = level


@pytest.fixture
def audio(monkeypatch):
    devices = [
        SimpleNamespace(id="speaker", FriendlyName="Speakers (SOULION R100)", EndpointVolume=Volume(0.35)),
        SimpleNamespace(id="interface", FriendlyName="Speakers (Focusrite USB Audio)", EndpointVolume=Volume(0.6)),
    ]
    state = SimpleNamespace(devices=devices, current=devices[1], roles={})

    def set_default(device_id, roles):
        state.current = next(d for d in devices if d.id == device_id)
        state.roles = {role: device_id for role in roles}

    api = SimpleNamespace(
        GetAllDevices=lambda **kwargs: devices,
        GetSpeakers=lambda: state.current,
        SetDefaultDevice=set_default,
    )
    monkeypatch.setattr(system_audio, "_audio_session", lambda: nullcontext((api, ["console", "multimedia", "communications"])))
    monkeypatch.setattr(system_audio.sys, "platform", "win32")
    return state


def run(args):
    return system_audio.SystemAudioTool().run(args, None)


def test_lists_outputs_and_current_default(audio):
    result = run({"action": "list"})
    assert result.success
    data = json.loads(result.reply_text)
    assert {d["name"] for d in data["devices"]} == {d.FriendlyName for d in audio.devices}
    assert data["default_device"] == audio.current.FriendlyName


def test_switch_output_preserves_volumes(audio):
    before = [d.EndpointVolume.level for d in audio.devices]
    result = run({"action": "set_output", "device": "soulion"})
    assert result.success
    assert audio.current.id == "speaker"
    assert len(audio.roles) == 3
    assert [d.EndpointVolume.level for d in audio.devices] == before


@pytest.mark.parametrize("args,expected", [
    ({"volume": 42}, 0.42),
    ({"change": 10}, 0.7),
    ({"change": -20}, 0.4),
    ({"change": 80}, 1.0),
    ({"change": -80}, 0.0),
])
def test_volume_control(audio, args, expected):
    result = run({"action": "set_volume", **args})
    assert result.success
    assert audio.current.EndpointVolume.level == pytest.approx(expected)
    assert json.loads(result.reply_text)["volume"] == pytest.approx(expected * 100)


@pytest.mark.parametrize("args", [
    None, {}, {"action": "set_output"}, {"action": "set_output", "device": "missing"},
    {"action": "set_output", "device": "Speakers"},
    {"action": "set_volume"}, {"action": "set_volume", "volume": 101},
    {"action": "set_volume", "volume": -1}, {"action": "set_volume", "volume": True},
    {"action": "set_volume", "volume": "50"},
    {"action": "set_volume", "volume": float("nan")},
    {"action": "set_volume", "volume": 50, "change": 10},
])
def test_invalid_requests_do_not_change_audio(audio, args):
    before = [d.EndpointVolume.level for d in audio.devices]
    result = run(args)
    assert not result.success and result.error_message
    assert audio.current.id == "interface"
    assert [d.EndpointVolume.level for d in audio.devices] == before


def test_windows_errors_are_reported(audio, monkeypatch):
    def failed():
        raise OSError("Audio endpoint unavailable")
    monkeypatch.setattr(system_audio, "_audio_session", failed)
    result = run({"action": "list"})
    assert not result.success
    assert "Audio endpoint unavailable" in result.error_message


def test_registered_tool_is_discoverable():
    from jarvis.tools.registry import BUILTIN_TOOLS, generate_tools_json_schema
    assert "systemAudio" in BUILTIN_TOOLS
    schemas = generate_tools_json_schema(allowed_tools=["systemAudio"])
    assert any(s["function"]["name"] == "systemAudio" for s in schemas)
