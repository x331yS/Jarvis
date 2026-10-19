"""Checks against a built Windows HUD bundle."""

import os
from pathlib import Path

import pytest


BUNDLE = os.environ.get("JARVIS_TEST_BUNDLE_DIR")
pytestmark = pytest.mark.skipif(not BUNDLE, reason="Set JARVIS_TEST_BUNDLE_DIR to a built bundle")


@pytest.fixture
def bundle_dir():
    assert BUNDLE
    return Path(BUNDLE) / "_internal"


@pytest.mark.parametrize("relative_path", [
    "PyQt6/Qt6/bin/QtWebEngineProcess.exe",
    "PyQt6/Qt6/resources/qtwebengine_resources.pak",
    "PyQt6/Qt6/resources/icudtl.dat",
    "PyQt6/Qt6/translations/qtwebengine_locales/en-US.pak",
    "desktop_app/web/index.html",
    "desktop_app/js/main.js",
    "desktop_app/js/three_scene.js",
    "desktop_app/js/vendor/three.min.js",
    "desktop_app/js/vendor/three.LICENSE",
    "desktop_app/css/jarvis.css",
])
def test_hud_runtime_asset_is_bundled(bundle_dir, relative_path):
    assert (bundle_dir / relative_path).is_file(), relative_path


def test_qt_process_uses_windows_system_icu(bundle_dir):
    assert not list(bundle_dir.rglob("icuuc.dll"))
