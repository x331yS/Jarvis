from types import SimpleNamespace
from unittest.mock import Mock

from jarvis.tools.builtin import system_apps
from jarvis.tools.builtin.system_apps import SystemAppsTool


def test_opening_a_known_app_starts_its_local_executable(monkeypatch):
    monkeypatch.setattr(system_apps, "_resolve_executable", lambda app: r"C:\Apps\Code.exe")
    process_start = Mock()
    monkeypatch.setattr(system_apps.subprocess, "Popen", process_start)

    result = SystemAppsTool().run(
        {"action": "open", "app": "VS Code"},
        context=SimpleNamespace(),
    )

    assert result.success
    assert result.reply_text == "vscode est ouvert."
    process_start.assert_called_once()
    assert process_start.call_args.args[0] == [r"C:\Apps\Code.exe"]


def test_opening_an_uninstalled_app_reports_the_missing_application(monkeypatch):
    monkeypatch.setattr(system_apps, "_resolve_executable", lambda _app: None)

    result = SystemAppsTool().run(
        {"action": "open", "app": "brave"},
        context=SimpleNamespace(),
    )

    assert not result.success
    assert result.error_message == "Application introuvable: brave"


def test_invalid_action_is_rejected_without_starting_a_process(monkeypatch):
    process_start = Mock()
    monkeypatch.setattr(system_apps.subprocess, "Popen", process_start)

    result = SystemAppsTool().run(
        {"action": "play", "app": "chrome"},
        context=SimpleNamespace(),
    )

    assert not result.success
    assert result.error_message == "Unsupported action: play"
    process_start.assert_not_called()


def test_opening_spotify_uses_its_local_windows_uri(monkeypatch):
    open_uri = Mock()
    monkeypatch.setattr(system_apps.os, "startfile", open_uri, raising=False)

    result = SystemAppsTool().run(
        {"action": "open", "app": "spotify"},
        context=SimpleNamespace(),
    )

    assert result.success
    assert result.reply_text == "Spotify est ouvert."
    open_uri.assert_called_once_with("spotify:")
