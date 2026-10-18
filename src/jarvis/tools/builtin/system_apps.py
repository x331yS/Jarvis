from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolContext
from ..types import ToolExecutionResult


_APP_ALIASES = {
    "spotify": "spotify",
    "brave": "brave",
    "chrome": "chrome",
    "firefox": "firefox",
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "notepad": "notepad",
    "bloc-notes": "notepad",
    "explorer": "explorer",
    "explorateur": "explorer",
}


def _windows_executable_candidates(app: str) -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
    program_files_x86 = Path(
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
    )

    if app == "brave":
        return [
            local / "BraveSoftware/Brave-Browser/Application/brave.exe",
            program_files / "BraveSoftware/Brave-Browser/Application/brave.exe",
            program_files_x86 / "BraveSoftware/Brave-Browser/Application/brave.exe",
        ]

    if app == "chrome":
        return [
            local / "Google/Chrome/Application/chrome.exe",
            program_files / "Google/Chrome/Application/chrome.exe",
            program_files_x86 / "Google/Chrome/Application/chrome.exe",
        ]

    if app == "firefox":
        return [
            program_files / "Mozilla Firefox/firefox.exe",
            program_files_x86 / "Mozilla Firefox/firefox.exe",
        ]

    if app == "vscode":
        return [
            local / "Programs/Microsoft VS Code/Code.exe",
            program_files / "Microsoft VS Code/Code.exe",
        ]

    return []


def _resolve_executable(app: str) -> Optional[str]:
    candidates = _windows_executable_candidates(app)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    aliases = {
        "brave": ["brave.exe", "brave"],
        "chrome": ["chrome.exe", "chrome"],
        "firefox": ["firefox.exe", "firefox"],
        "vscode": ["code.exe", "code"],
        "notepad": ["notepad.exe"],
        "explorer": ["explorer.exe"],
    }

    for executable in aliases.get(app, []):
        resolved = shutil.which(executable)
        if resolved:
            return resolved

    return None


class SystemAppsTool(Tool):
    @property
    def name(self) -> str:
        return "systemApps"

    @property
    def description(self) -> str:
        return (
            "Launch or close common Windows desktop applications. "
            "Use this for commands such as 'open Spotify', 'launch Brave', "
            "'start VS Code', or 'open Explorer'. "
            "This tool controls the local computer and does not search the web."
        )

    @property
    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open", "close"],
                    "description": "Whether to open or close the application.",
                },
                "app": {
                    "type": "string",
                    "enum": [
                        "spotify",
                        "brave",
                        "chrome",
                        "firefox",
                        "vscode",
                        "notepad",
                        "explorer",
                    ],
                    "description": "Application to control.",
                },
            },
            "required": ["action", "app"],
        }

    def run(
        self,
        args: Optional[Dict[str, Any]],
        context: ToolContext,
    ) -> ToolExecutionResult:
        if not isinstance(args, dict):
            return ToolExecutionResult(
                success=False,
                reply_text=None,
                error_message="Invalid systemApps arguments.",
            )

        action = str(args.get("action", "")).strip().lower()
        requested_app = str(args.get("app", "")).strip().lower()

        app = _APP_ALIASES.get(requested_app, requested_app)

        if action not in {"open", "close"}:
            return ToolExecutionResult(
                success=False,
                reply_text=None,
                error_message=f"Unsupported action: {action}",
            )

        if app == "spotify":
            if action == "open":
                try:
                    os.startfile("spotify:")
                    return ToolExecutionResult(
                        success=True,
                        reply_text="Spotify est ouvert.",
                    )
                except Exception as exc:
                    return ToolExecutionResult(
                        success=False,
                        reply_text=None,
                        error_message=f"Impossible d'ouvrir Spotify: {exc}",
                    )

            result = subprocess.run(
                ["taskkill", "/IM", "Spotify.exe", "/F"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            if result.returncode == 0:
                return ToolExecutionResult(
                    success=True,
                    reply_text="Spotify est fermé.",
                )

            return ToolExecutionResult(
                success=False,
                reply_text=None,
                error_message="Spotify ne semble pas être ouvert.",
            )

        if app == "explorer":
            if action == "open":
                subprocess.Popen(
                    ["explorer.exe"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return ToolExecutionResult(
                    success=True,
                    reply_text="L'explorateur est ouvert.",
                )

            return ToolExecutionResult(
                success=False,
                reply_text=None,
                error_message="La fermeture automatique de l'Explorateur est désactivée.",
            )

        executable = _resolve_executable(app)

        if action == "open":
            if not executable:
                return ToolExecutionResult(
                    success=False,
                    reply_text=None,
                    error_message=f"Application introuvable: {app}",
                )

            try:
                subprocess.Popen(
                    [executable],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

                return ToolExecutionResult(
                    success=True,
                    reply_text=f"{app} est ouvert.",
                )

            except Exception as exc:
                return ToolExecutionResult(
                    success=False,
                    reply_text=None,
                    error_message=f"Impossible d'ouvrir {app}: {exc}",
                )

        process_names = {
            "brave": "brave.exe",
            "chrome": "chrome.exe",
            "firefox": "firefox.exe",
            "vscode": "Code.exe",
            "notepad": "notepad.exe",
        }

        process_name = process_names.get(app)

        if not process_name:
            return ToolExecutionResult(
                success=False,
                reply_text=None,
                error_message=f"Impossible de fermer {app}.",
            )

        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode == 0:
            return ToolExecutionResult(
                success=True,
                reply_text=f"{app} est fermé.",
            )

        return ToolExecutionResult(
            success=False,
            reply_text=None,
            error_message=f"{app} ne semble pas être ouvert.",
        )