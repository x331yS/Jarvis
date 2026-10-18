"""Upgrades through the Windows installer must not keep stale bundle files."""

import re
from pathlib import Path

ISS = Path(__file__).resolve().parents[1] / "installer" / "windows" / "jarvis_setup.iss"


def _section(name: str) -> list[str]:
    text = ISS.read_text(encoding="utf-8")
    match = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not match:
        return []
    return [
        line.strip() for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith(";")
    ]


def test_upgrade_clears_previous_bundle_internals():
    entries = _section("InstallDelete")
    assert any(
        "filesandordirs" in e and re.search(r'Name:\s*"\{app\}\\_internal"', e)
        for e in entries
    ), "Stale DLLs left in _internal by an older install break the Qt WebEngine HUD"


def test_upgrade_keeps_downloaded_cuda_libraries():
    for entry in _section("InstallDelete"):
        assert not re.search(r'Name:\s*"\{app\}"\s*$', entry)
        assert "cuda" not in entry.lower()
