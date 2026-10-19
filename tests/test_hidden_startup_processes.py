import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from desktop_app.background_process import hidden_console_options
from jarvis.utils.vram import _detect_via_nvidia_smi


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console inheritance")
def test_background_server_and_its_children_share_an_invisible_console():
    probe = (
        "import ctypes,json;"
        "h=ctypes.windll.kernel32.GetConsoleWindow();"
        "print(json.dumps(dict(console=h,visible=bool(ctypes.windll.user32.IsWindowVisible(h)))))"
    )
    parent = (
        "import subprocess,sys;"
        f"exec({probe!r});"
        f"p=subprocess.run([sys.executable,'-c',{probe!r}],capture_output=True,text=True,check=True);"
        "print(p.stdout.strip())"
    )
    process = subprocess.run(
        [sys.executable, "-c", parent],
        capture_output=True, text=True, check=True, timeout=15,
        **hidden_console_options(),
    )
    root, child = [json.loads(line) for line in process.stdout.splitlines()]
    assert root["console"] != 0
    assert child["console"] == root["console"]
    assert not root["visible"] and not child["visible"]


def test_other_platforms_keep_their_default_process_options(monkeypatch):
    monkeypatch.setattr("desktop_app.background_process.sys.platform", "linux")
    assert hidden_console_options() == {}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows startup probe")
def test_nvidia_probe_disables_console_allocation():
    options = {}

    def run(command, **kwargs):
        options.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="8192\n", stderr="")

    with patch("jarvis.utils.vram.subprocess.run", side_effect=run):
        assert _detect_via_nvidia_smi() == 8192
    assert options["creationflags"] & subprocess.CREATE_NO_WINDOW
