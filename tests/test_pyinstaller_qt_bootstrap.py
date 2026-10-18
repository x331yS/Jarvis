"""Build-time Qt detection used by the Windows PyInstaller bundle."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_DIR = PROJECT_ROOT / "installer" / "windows" / "pyinstaller_bootstrap"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ICU conflict only")


def test_pyinstaller_can_read_qt_library_info_with_bootstrap():
    pytest.importorskip("PyInstaller")
    pytest.importorskip("PyQt6")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(BOOTSTRAP_DIR), env.get("PYTHONPATH")])
    )
    script = (
        "from PyInstaller.utils.hooks.qt import pyqt6_library_info as info\n"
        "print(info.version is not None)\n"
        "print(info.location['LibraryExecutablesPath'])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=120,
    )

    lines = result.stdout.strip().splitlines()
    assert result.returncode == 0, result.stderr
    assert lines[0] == "True", result.stderr
    assert (Path(lines[1]) / "QtWebEngineProcess.exe").is_file()
