"""Local Windows playback endpoint and volume control."""

import json
import math
import re
import sys
from typing import Any

from ...debug import debug_log
from ...utils.windows_audio import audio_session as _audio_session
from ..base import Tool, ToolContext
from ..types import ToolExecutionResult


class SystemAudioTool(Tool):
    @property
    def name(self) -> str:
        return "systemAudio"

    @property
    def description(self) -> str:
        return (
            "Control local Windows audio: list playback outputs, switch the Windows "
            "default output by device name (for example SOULION R100 or Focusrite), "
            "or raise/lower/set speaker volume. "
            "Arguments: action='list' to enumerate outputs; "
            "action='set_output' with device='<name or unique part>' to switch output; "
            "action='set_volume' with volume=0..100 for an absolute percentage OR "
            "change=-100..100 for a relative percentage-point adjustment, never both. "
            "For an unspecified amount use change=10 to raise or change=-10 to lower. "
            "Switching outputs preserves each "
            "device's volume. Use set_volume only when the user requests a volume "
            "change; a number in a device model name is not a volume request. "
            "Return device names and volume as raw data. No administrator rights needed."
        )

    @property
    def inputSchema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "set_output", "set_volume"]},
                "device": {
                    "type": "string",
                    "description": "Playback device name or unique part. Required for set_output; otherwise defaults to current output.",
                },
                "volume": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "description": "Absolute volume percentage for set_volume. Do not combine with change.",
                },
                "change": {
                    "type": "number", "minimum": -100, "maximum": 100,
                    "description": "Relative volume change in percentage points, positive to raise, negative to lower. For an unspecified amount use 10 or -10. Do not combine with volume.",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def run(self, args: dict[str, Any] | None, context: ToolContext) -> ToolExecutionResult:
        def failure(message: str) -> ToolExecutionResult:
            debug_log(message, "system_audio")
            return ToolExecutionResult(success=False, reply_text=None, error_message=message)

        if sys.platform != "win32":
            return failure("System audio control is available on Windows only.")
        if not isinstance(args, dict) or args.get("action") not in {"list", "set_output", "set_volume"}:
            return failure("Specify a valid systemAudio action.")
        action = args["action"]
        device_name = args.get("device", "")
        if not isinstance(device_name, str):
            return failure("The playback device must be a name.")
        device_name = device_name.strip()
        if action == "set_output" and not device_name:
            return failure("Specify the playback device to select.")
        if action != "set_volume" and ("volume" in args or "change" in args):
            return failure("Volume changes require the set_volume action.")
        if action == "set_volume":
            if ("volume" in args) == ("change" in args):
                return failure("Specify either volume or change, not both.")
            value = args.get("volume", args.get("change"))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return failure("Volume must be a finite number.")
            minimum = 0 if "volume" in args else -100
            if not minimum <= value <= 100:
                return failure(f"Volume must be between {minimum} and 100.")

        try:
            with _audio_session() as (audio, roles):
                # eRender = 0, DEVICE_STATE_ACTIVE = 1: never select recording or disconnected endpoints.
                devices = audio.GetAllDevices(data_flow=0, device_state=1)
                current = audio.GetSpeakers()
                if action == "list":
                    data = {
                        "devices": [{"id": d.id, "name": d.FriendlyName} for d in devices],
                        "default_device": current.FriendlyName if current else None,
                    }
                else:
                    target = current
                    if device_name:
                        normalise = lambda text: re.sub(r"[\W_]+", "", text.casefold())
                        query = normalise(device_name)
                        exact = [d for d in devices if d.id == device_name or normalise(d.FriendlyName or "") == query]
                        matches = exact or [d for d in devices if query and query in normalise(d.FriendlyName or "")]
                        if len(matches) != 1:
                            return failure(
                                "Playback device not found or ambiguous. Available outputs: "
                                + ", ".join(d.FriendlyName or d.id for d in devices)
                            )
                        target = matches[0]
                    if target is None:
                        return failure("No default playback device is available.")
                    if action == "set_output":
                        audio.SetDefaultDevice(target.id, roles=roles)
                        selected = audio.GetSpeakers()
                        if selected is None or selected.id != target.id:
                            return failure("Windows did not select the requested playback device.")
                    else:
                        endpoint = target.EndpointVolume
                        level = args.get("volume")
                        if level is None:
                            level = endpoint.GetMasterVolumeLevelScalar() * 100 + args["change"]
                        endpoint.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
                    data = {
                        "device": target.FriendlyName,
                        "volume": round(target.EndpointVolume.GetMasterVolumeLevelScalar() * 100, 2),
                    }
                debug_log(f"{action}: {json.dumps(data, ensure_ascii=False)}", "system_audio")
                return ToolExecutionResult(success=True, reply_text=json.dumps(data, ensure_ascii=False))
        except (ImportError, OSError, RuntimeError) as exc:
            return failure(f"Windows audio control failed: {exc}")
