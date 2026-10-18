"""Build-only Windows bootstrap for PyInstaller's isolated Qt analysis.

Conda ships an ICU build whose ``icuuc.dll`` shadows the Windows one, and
PyQt6's Qt6Core cannot load against it. The desktop app preloads the Windows
ICU at runtime; this file does the same for the subprocesses PyInstaller uses
to query Qt, so its Qt hooks (WebEngine included) can collect their files.
It is only placed on ``PYTHONPATH`` by ``jarvis_desktop.spec``.
"""

import ctypes
import os
import sys

if sys.platform == "win32":
    _system_icu = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icuuc.dll"
    )
    if os.path.isfile(_system_icu):
        _WINDOWS_ICU_HANDLE = ctypes.WinDLL(_system_icu, winmode=0x1100)
