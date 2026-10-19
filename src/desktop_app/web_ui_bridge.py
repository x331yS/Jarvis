from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from jarvis.debug import debug_log


class JarvisWebBridge(QObject):
    """
    Python <-> JavaScript bridge for the Jarvis HUD.

    Python can push state/context to the browser.
    JavaScript can request simple UI actions.
    """

    state_changed = pyqtSignal(str)
    context_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self._context: dict[str, str] = {}

    @pyqtSlot(str)
    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        debug_log(f"HUD state: {self._state} -> {state}", "desktop")
        self._state = state
        self.state_changed.emit(state)

    @pyqtSlot(str, str)
    def set_context(self, key: str, value: str) -> None:
        if key in self._context and self._context[key] == value:
            return
        self._context[key] = value
        self.context_changed.emit(key, value)

    @pyqtSlot(result="QVariantMap")
    def snapshot(self) -> dict:
        return {"state": self._state, "context": dict(self._context)}

    @pyqtSlot(str)
    def notify(self, message: str) -> None:
        self.context_changed.emit("notification", message)

    def state(self) -> str:
        return self._state