from __future__ import annotations

import re
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QColor, QPalette
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
        background = QColor("#02060b")
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, background)
        palette.setColor(QPalette.ColorRole.Base, background)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.bridge = JarvisWebBridge(self)

        if QWebEngineView is None or QWebChannel is None:
            raise RuntimeError(
                "PyQt6-WebEngine and PyQt6-WebChannel are required for the Jarvis HUD."
            )

        self.web_view = QWebEngineView(self)
        self.web_view.setPalette(palette)
        self.web_view.setAutoFillBackground(True)
        self.web_view.page().setBackgroundColor(background)
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
            self.setGeometry(screen.geometry())
        else:
            debug_log("No display is available for the JARVIS HUD", "desktop")
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def on_log(self, message: str) -> None:
        """
        Lightweight bridge from Jarvis logs to the visual state.

        This intentionally does not modify daemon internals.
        """

        text = re.sub(r"\x1b\[[0-9;]*m", "", message).lower()

        if "error" in text or "failed" in text:
            self.bridge.set_state("error")
            return

        if any(
            token in text
            for token in (
                "waiting for wake",
                "ready for wake",
                "returning to wake word mode",
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
                "listening",
                "dictating",
            )
        ):
            self.bridge.set_state("listening")
            return

        if any(
            token in text
            for token in (
                "thinking",
                "working on it",
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
