from unittest.mock import patch

import pytest

from jarvis.config import get_default_config, load_settings
from jarvis.system_prompt import build_system_prompt


def test_language_setting_round_trip(monkeypatch):
    monkeypatch.setattr("jarvis.config._load_json", lambda path: {"reply_language": "French"})
    assert load_settings().reply_language == "French"
    assert get_default_config()["reply_language"] == "English"


@pytest.mark.parametrize("language", ["French", "Turkish", "Japanese"])
def test_persona_respects_configured_language(language):
    prompt = build_system_prompt("Jarvis", reply_language=language)
    assert f"Reply exclusively in {language}" in prompt
    assert "British describes your manner, not the language" in prompt


def test_language_reaches_reply_model(mock_config, db, dialogue_memory):
    from jarvis.reply.engine import run_reply_engine

    mock_config.reply_language = "French"
    prompts = []

    def chat(*args, **kwargs):
        messages = kwargs.get("messages") or args[2]
        prompts.append(messages[0]["content"])
        return {"message": {"role": "assistant", "content": "Bonjour !"}}

    with patch("jarvis.reply.engine.plan_query", return_value=["Reply to the user."]), \
         patch("jarvis.reply.engine.chat_with_messages", side_effect=chat):
        response = run_reply_engine(
            db, mock_config, None, "Salut Jarvis", dialogue_memory=dialogue_memory,
        )
    assert response == "Bonjour !"
    assert prompts and all("Reply exclusively in French" in prompt for prompt in prompts)
