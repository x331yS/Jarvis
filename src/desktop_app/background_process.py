"""Console inheritance for Windows background process trees."""

import subprocess
import sys
from typing import Any

from jarvis.debug import debug_log


def hidden_console_options() -> dict[str, Any]:
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    # Runners inherit this hidden console instead of allocating visible consoles.
    debug_log("Starting background process tree with an inherited hidden console", "desktop")
    return {
        "creationflags": subprocess.CREATE_NEW_CONSOLE,
        "startupinfo": startupinfo,
    }
