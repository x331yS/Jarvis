"""Build-time checks run by ``jarvis_desktop.spec`` before bundling."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from packaging.requirements import InvalidRequirement, Requirement


def pinned_version_mismatches(
    requirements_path: Path,
    installed_version: Callable[[str], Optional[str]],
) -> list[tuple[str, str, str]]:
    """Return ``(name, pinned, installed)`` for installed packages off their pin.

    Only exact pins for the current platform are checked: a bundle built from a
    stale environment ships old library bugs while tests pass from source.
    Packages absent from the build environment are skipped, since the build
    deliberately leaves some pinned extras out of the bundle.
    """
    mismatches = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            continue
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        pins = [spec.version for spec in requirement.specifier if spec.operator == "=="]
        if not pins:
            continue
        installed = installed_version(requirement.name)
        if installed is not None and installed != pins[0]:
            mismatches.append((requirement.name, pins[0], installed))
    return mismatches
