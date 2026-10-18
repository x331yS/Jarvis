from __future__ import annotations

import re
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow

from jarvis.debug import debug_log

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
except ImportError:
    QWebEngineView = None
    QWebChannel = None

from desktop_app.web_ui_bridge import JarvisWebBridge


def _select_hud_screen(screens, primary_screen):
    """Use the third display for the HUD, falling back when it is unavailable."""
    for screen in screens:
        name = getattr(screen, "name", None)
        if callable(name) and name().upper().endswith("DISPLAY3"):
            return screen
    if len(screens) >= 3:
        return screens[2]
    return primary_screen


def show_composited_fullscreen(window, geometry) -> None:
    """Show ``window`` full-screen over ``geometry``.

    On Windows a borderless GPU window covering a monitor is promoted out of
    DWM composition; any overlay or notification appearing over it forces a
    switch back that shows as a brief black frame. Keeping ``WS_BORDER`` (the
    fix Qt documents for full-screen OpenGL windows) keeps the HUD composited.
    """
    window.setGeometry(geometry)
    window.showFullScreen()
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = int(window.winId())
        gwl_style = -16
        ws_border = 0x00800000
        style = user32.GetWindowLongW(hwnd, gwl_style)
        if not style & ws_border:
            user32.SetWindowLongW(hwnd, gwl_style, style | ws_border)
            # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        debug_log("JARVIS HUD kept composited with WS_BORDER", "desktop")
    except Exception as exc:
        debug_log(f"JARVIS HUD border style failed: {exc!r}", "desktop")


class JarvisHudWindow(QMainWindow):
    """
    Full-screen Iron-Man/JARVIS style HUD.

    The UI itself lives in HTML/CSS/JS.
    Python only owns the window and the bridge.
    """

    @staticmethod
    def is_available() -> bool:
        return QWebEngineView is not None and QWebChannel is not None

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("JARVIS")

        self.bridge = JarvisWebBridge(self)

        if QWebEngineView is None or QWebChannel is None:
            raise RuntimeError(
                "PyQt6-WebEngine and PyQt6-WebChannel are required for the Jarvis HUD."
            )

        self.web_view = QWebEngineView(self)
        self.setCentralWidget(self.web_view)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            False,
        )

        channel = QWebChannel(self.web_view.page())
        channel.registerObject("jarvis", self.bridge)

        self.web_view.page().setWebChannel(channel)

        html_path = Path(__file__).resolve().parent / "web" / "index.html"

        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

        self.bridge.state_changed.connect(self._push_state)
        self.bridge.context_changed.connect(self._push_context)

    def show_fullscreen(self) -> None:
        screens = QApplication.screens()
        primary_screen = QApplication.primaryScreen()
        screen = _select_hud_screen(screens, primary_screen)
        if screen is not None:
            display_description = (
                "third display"
                if len(screens) >= 3
                else "primary display (third display unavailable)"
            )
            debug_log(
                f"Opening JARVIS HUD on the {display_description}",
                "desktop",
            )
            show_composited_fullscreen(self, screen.geometry())
        else:
            debug_log("No display is available for the JARVIS HUD", "desktop")
            self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _push_state(self, state: str) -> None:
        script = (
            "window.jarvisHUD && "
            f"window.jarvisHUD.setState({state!r});"
        )
        self.web_view.page().runJavaScript(script)

    def _push_context(self, key: str, value: str) -> None:
        script = (
            "window.jarvisHUD && "
            f"window.jarvisHUD.setContext({key!r}, {value!r});"
        )
        self.web_view.page().runJavaScript(script)

    def on_log(self, message: str) -> None:
        """
        Lightweight bridge from Jarvis logs to the visual state.

        This intentionally does not modify daemon internals.
        """

        text = re.sub(r"\x1b\[[0-9;]*m", "", message).lower()

        if any(
            token in text
            for token in (
                "listening",
                "waiting for wake",
                "ready for wake",
            )
        ):
            self.bridge.set_state("idle")
            return

        if any(
            token in text
            for token in (
                "wake word",
                "hearing",
                "listening for",
                "dictating",
            )
        ):
            self.bridge.set_state("listening")
            return

        if any(
            token in text
            for token in (
                "thinking",
                "generating",
                "processing",
                "llm",
            )
        ):
            self.bridge.set_state("thinking")
            return

        if any(
            token in text
            for token in (
                "tool",
                "executing",
                "running",
                "mcp",
            )
        ):
            self.bridge.set_state("executing")
            return

        if any(
            token in text
            for token in (
                "speaking",
                "tts",
                "playing response",
            )
        ):
            self.bridge.set_state("speaking")
            return

        if "error" in text or "failed" in text:
            self.bridge.set_state("error")