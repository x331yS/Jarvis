"""Windows full-screen HUD stays composited by DWM (no black overlay flashes)."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(sys.platform != "win32", reason="Native Windows HUD test")]

_PROBE = r"""
import ctypes, os, sys
ctypes.WinDLL(os.path.join(os.environ["SystemRoot"], "System32", "icuuc.dll"), winmode=0x1100)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow
from desktop_app.jarvis_hud import show_composited_fullscreen

app = QApplication(sys.argv)
window = QMainWindow()
window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
screen = app.primaryScreen().geometry()
show_composited_fullscreen(window, screen)
app.processEvents()
style = ctypes.windll.user32.GetWindowLongW(int(window.winId()), -16)
print("BORDER", bool(style & 0x00800000))
print("FULLSCREEN", window.isFullScreen())
print("COVERS", window.geometry() == screen)
"""


def test_fullscreen_hud_keeps_a_border_so_overlays_do_not_flash_black():
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    environment["QT_QPA_PLATFORM"] = "windows"
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BORDER True" in result.stdout
    assert "FULLSCREEN True" in result.stdout
    assert "COVERS True" in result.stdout
