"""HUD updates must be idempotent and use one bridge delivery path."""

import json
import colorsys
from io import BytesIO
from pathlib import Path
import os
import subprocess
import sys

import pytest

from desktop_app.web_ui_bridge import JarvisWebBridge


def test_repeated_state_does_not_publish_another_transition():
    bridge = JarvisWebBridge()
    observed = []
    bridge.state_changed.connect(observed.append)
    bridge.set_state("speaking")
    bridge.set_state("speaking")
    bridge.set_state("idle")
    assert observed == ["speaking", "idle"]


def test_context_only_publishes_changes_and_snapshot_preserves_current_state():
    bridge = JarvisWebBridge()
    observed = []
    bridge.context_changed.connect(lambda key, value: observed.append((key, value)))
    bridge.set_state("thinking")
    bridge.set_context("model", "local-model")
    bridge.set_context("model", "local-model")
    assert observed == [("model", "local-model")]
    assert bridge.snapshot() == {"state": "thinking", "context": {"model": "local-model"}}


@pytest.fixture
def hud():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(5000)
        page.add_init_script("""
            const realNow = performance.now.bind(performance);
            window.hudTimeOffset = 0;
            performance.now = () => realNow() + window.hudTimeOffset;
            window.qt = {webChannelTransport: {}};
            window.QWebChannel = function(transport, ready) {
                ready({objects: {jarvis: {
                    state_changed: {connect: callback => window.emitState = callback},
                    context_changed: {connect: callback => window.emitContext = callback},
                    snapshot: callback => callback({
                        state: "thinking", context: {model: "local-model"}
                    })
                }}});
            };
        """)
        page.goto((Path(__file__).parents[1] / "src" / "desktop_app" / "web" / "index.html").as_uri())
        page.wait_for_function("!!window.jarvisHUD && typeof window.emitState === 'function'")
        yield page
        browser.close()


def test_repeated_frontend_state_has_no_dom_churn(hud):
    result = hud.evaluate("""
        (() => {
            window.jarvisHUD.setState("speaking");
            const observer = new MutationObserver(() => {});
            observer.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
            const first = document.getElementById("activity").firstChild;
            for (let i = 0; i < 20; i++) window.jarvisHUD.setState("speaking");
            const count = observer.takeRecords().length;
            observer.disconnect();
            return JSON.stringify({
                mutations: count,
                sameRow: first === document.getElementById("activity").firstChild
            });
        })()
    """)
    assert json.loads(result) == {"mutations": 0, "sameRow": True}


def test_one_bridge_transition_creates_one_activity_entry(hud):
    hud.evaluate('document.getElementById("activity").replaceChildren();')
    hud.evaluate('window.emitState("speaking"); window.emitState("speaking");')
    assert hud.locator("#modeValue").inner_text() == "SPEAKING"
    assert hud.locator("#activity > div").count() == 1


def test_initial_snapshot_restores_state_and_context(hud):
    assert hud.locator("#modeValue").inner_text() == "THINKING"
    assert hud.locator("#modelValue").inner_text() == "local-model"


def test_repeated_context_does_not_replace_activity(hud):
    result = hud.evaluate("""() => {
        window.emitContext("model", "other-model");
        const first = document.getElementById("activity").firstChild;
        window.emitContext("model", "other-model");
        return first === document.getElementById("activity").firstChild;
    }""")
    assert result


def test_error_state_does_not_replace_the_full_page_compositing_surface(hud):
    hud.evaluate('window.emitState("error");')
    assert hud.evaluate('getComputedStyle(document.body).filter') == "none"
    assert hud.locator("#modeValue").inner_text() == "ERROR"

def test_three_dimensional_reactor_uses_an_opaque_live_surface(hud):
    assert hud.locator("body").evaluate("body => body.classList.contains('webgl-ready')")
    assert hud.locator(".reactor .core").evaluate("element => getComputedStyle(element).display") == "none"
    info = hud.evaluate("""() => {
        const canvas = document.getElementById("space");
        const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
        return {alpha: gl.getContextAttributes().alpha, lost: gl.isContextLost()};
    }""")
    assert info == {"alpha": False, "lost": False}


def test_lost_webgl_context_keeps_the_css_reactor_visible_until_restored(hud):
    supported = hud.evaluate("""() => {
        const canvas = document.getElementById("space");
        const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
        const extension = gl && gl.getExtension("WEBGL_lose_context");
        if (!extension) return false;
        window.restoreHudContext = () => extension.restoreContext();
        extension.loseContext();
        return true;
    }""")
    assert supported, "The test renderer must support context loss simulation"
    hud.wait_for_function("!document.body.classList.contains('webgl-ready')")
    assert hud.locator(".reactor .core").evaluate("element => getComputedStyle(element).display") != "none"
    hud.evaluate("window.restoreHudContext()")
    hud.wait_for_function("document.body.classList.contains('webgl-ready')")


def _reactor_hue(hud):
    from PIL import Image

    hud.wait_for_timeout(1400)
    image = Image.open(BytesIO(hud.locator(".reactor").screenshot())).convert("RGB")
    coloured = [
        pixel for pixel in image.getdata()
        if max(pixel) > 80 and max(pixel) - min(pixel) > 40
    ]
    assert coloured, "The reactor must render visible coloured pixels"
    channels = [sum(pixel[index] for pixel in coloured) / len(coloured) / 255 for index in range(3)]
    return colorsys.rgb_to_hsv(*channels)[0]


@pytest.mark.parametrize("state,hue_range", [
    ("listening", (0.45, 0.70)),
    ("thinking", (0.04, 0.20)),
    ("executing", (0.04, 0.20)),
    ("speaking", (0.27, 0.48)),
    ("error", (0.0, 0.04)),
])
def test_reactor_colour_communicates_assistant_activity(hud, state, hue_range):
    hud.evaluate("(state) => window.jarvisHUD.setState(state)", state)
    hue = _reactor_hue(hud)
    assert hue_range[0] <= hue <= hue_range[1], (state, hue)


def test_idle_reactor_gradually_varies_between_cool_colours(hud):
    hud.evaluate("window.jarvisHUD.setState('idle')")
    initial = _reactor_hue(hud)
    hud.evaluate("window.hudTimeOffset += 24000")
    later = _reactor_hue(hud)
    assert 0.45 <= initial <= 0.80
    assert 0.65 <= later <= 0.85
    assert abs(later - initial) > 0.10


def test_processing_colour_progresses_from_yellow_towards_orange(hud):
    hud.evaluate("window.jarvisHUD.setState('thinking')")
    yellow = _reactor_hue(hud)
    hud.evaluate("window.hudTimeOffset += 4000")
    orange = _reactor_hue(hud)
    assert 0.04 <= orange < yellow <= 0.20
    assert yellow - orange > 0.01


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows rendering contract")
def test_native_window_and_web_surface_share_an_opaque_background():
    script = """
import json
import desktop_app.app
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette
from PyQt6.QtCore import Qt
from desktop_app.jarvis_hud import JarvisHudWindow
app = QApplication(["hud-background-test"])
window = JarvisHudWindow()
print(json.dumps({
    "window": window.palette().color(QPalette.ColorRole.Window).name(),
    "web": window.web_view.palette().color(QPalette.ColorRole.Window).name(),
    "page": window.web_view.page().backgroundColor().name(),
    "translucent": window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
}))
window.close()
"""
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root, capture_output=True, text=True, timeout=20,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )
    assert result.returncode == 0, result.stderr
    colours = json.loads(result.stdout)
    assert colours["window"] == colours["web"] == colours["page"]
    assert not colours["translucent"]


@pytest.mark.parametrize("message,expected", [
    ("Listening for follow-up (3s)...", "listening"),
    ("Returning to wake word mode", "idle"),
    ("Generating response...", "thinking"),
    ("TTS playing response", "speaking"),
    ("Working on it: Bonjour", "thinking"),
    ("TTS error: playback failed", "error"),
])
def test_log_events_have_consistent_states(message, expected):
    from desktop_app.jarvis_hud import JarvisHudWindow

    bridge = JarvisWebBridge()
    window = type("Window", (), {"bridge": bridge})()
    JarvisHudWindow.on_log(window, message)
    assert bridge.state() == expected
