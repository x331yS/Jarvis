"""Windows playback endpoints shared by audio tools and speech playback."""

from contextlib import contextmanager
import sys
from typing import Any, Iterator


@contextmanager
def audio_session() -> Iterator[tuple[Any, list[Any]]]:
    import comtypes
    from pycaw.constants import ERole
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()
    try:
        yield AudioUtilities, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]
    except comtypes.COMError as exc:
        raise OSError(f"Windows Core Audio: {exc}") from exc
    finally:
        comtypes.CoUninitialize()


def playback_device() -> int | None:
    """Resolve the current Windows output without restarting microphone capture."""
    if sys.platform != "win32":
        return None
    import sounddevice as sd

    with audio_session() as (audio, _):
        device = audio.GetSpeakers()
        if device is None or not device.FriendlyName:
            raise OSError("No Windows default playback device is available.")
        name = device.FriendlyName
    for index, candidate in enumerate(sd.query_devices()):
        host = sd.query_hostapis(candidate["hostapi"])["name"]
        # MME and DirectSound support Piper's synthesis rate without WASAPI resampling.
        if (
            candidate["max_output_channels"] > 0
            and host in {"MME", "Windows DirectSound"}
            and candidate["name"] in {name, name[:31]}
        ):
            return index
    raise OSError(f"Windows default playback device is not available to PortAudio: {name}")
