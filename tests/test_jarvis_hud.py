from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class _LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []
        self.remote: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        path = attributes.get("src") if tag == "script" else attributes.get("href")
        if tag == "script" and path:
            self.scripts.append(path)
        if path and path.startswith(("http:", "https:", "//")):
            self.remote.append(path)
        if path and not path.startswith(("qrc:", "http:", "https:", "//")):
            self.paths.append(path)


def _parse_hud_page() -> tuple[Path, _LocalAssetParser]:
    page = ROOT / "src" / "desktop_app" / "web" / "index.html"
    parser = _LocalAssetParser()
    parser.feed(page.read_text(encoding="utf-8"))
    return page, parser


def test_hud_local_assets_are_resolvable_from_embedded_page() -> None:
    page, parser = _parse_hud_page()

    missing = [
        asset
        for asset in parser.paths
        if not (page.parent / asset).resolve().is_file()
    ]

    assert not missing, f"HUD page references missing local assets: {missing}"


def test_hud_loads_bundled_threejs_before_the_scene_offline() -> None:
    page, parser = _parse_hud_page()

    assert not parser.remote, f"HUD must work offline, found remote assets: {parser.remote}"
    three = [s for s in parser.scripts if Path(s).name.startswith("three.") and "min" in s]
    assert three, "HUD page does not load a bundled Three.js build"
    assert parser.scripts.index(three[0]) < parser.scripts.index("../js/three_scene.js")
    assert "REVISION" in (page.parent / three[0]).resolve().read_text(encoding="utf-8")


def test_hud_scene_renders_with_threejs_webgl() -> None:
    scene = (ROOT / "src" / "desktop_app" / "js" / "three_scene.js").read_text(encoding="utf-8")

    assert "THREE.WebGLRenderer" in scene


def test_hud_uses_third_display_when_available() -> None:
    from desktop_app.jarvis_hud import _select_hud_screen

    screens = [object(), object(), object(), object()]

    assert _select_hud_screen(screens, primary_screen=screens[0]) is screens[2]


def test_hud_prefers_windows_display_three_name_when_available() -> None:
    from desktop_app.jarvis_hud import _select_hud_screen

    screens = [
        SimpleNamespace(name=lambda: r"\\.\DISPLAY1"),
        SimpleNamespace(name=lambda: r"\\.\DISPLAY2"),
        SimpleNamespace(name=lambda: r"\\.\DISPLAY4"),
        SimpleNamespace(name=lambda: r"\\.\DISPLAY3"),
    ]

    assert _select_hud_screen(screens, primary_screen=screens[0]) is screens[3]


def test_hud_falls_back_to_primary_display_when_third_is_unavailable() -> None:
    from desktop_app.jarvis_hud import _select_hud_screen

    primary_screen = object()

    assert _select_hud_screen([object(), object()], primary_screen) is primary_screen
