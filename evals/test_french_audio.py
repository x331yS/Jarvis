"""Local live evaluations for French replies and Windows audio commands."""

import json
from unittest.mock import patch

import pytest

from conftest import requires_judge_llm
from helpers import JUDGE_BASE_URL, JUDGE_MODEL


def local_chat(messages, **extra):
    import requests

    response = requests.post(
        f"{JUDGE_BASE_URL.rstrip('/')}/api/chat",
        json={
            "model": JUDGE_MODEL, "stream": False, "think": False,
            "messages": messages,
            "options": {"temperature": 0, "num_ctx": 8192},
            **extra,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]


def system_prompt():
    from jarvis.reply.prompts import detect_model_size, get_system_prompts
    from jarvis.system_prompt import build_system_prompt

    return "\n".join([
        build_system_prompt(reply_language="French"),
        *get_system_prompts(detect_model_size(JUDGE_MODEL)).to_list(),
    ])


@pytest.mark.eval
@requires_judge_llm
@pytest.mark.parametrize("query", ["Salut Jarvis", "Comment vas-tu ?", "Hello Jarvis"])
def test_replies_exclusively_in_french(query):
    response = local_chat([
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": query},
    ])["content"]
    assert response, "The local model must produce a reply."
    verdict = local_chat([
        {"role": "system", "content": "Evaluate the supplied reply. Set french_only to true "
         "if all prose is in French (proper names are allowed), otherwise false."},
        {"role": "user", "content": response},
    ], format={
        "type": "object", "properties": {"french_only": {"type": "boolean"}},
        "required": ["french_only"],
    })
    assert json.loads(verdict["content"])["french_only"], response


@pytest.mark.eval
@requires_judge_llm
@pytest.mark.parametrize("query,action,device,change", [
    ("Mets la sortie audio sur le Soulion R100", "set_output", "soulion", None),
    ("Passe le son sur la Focusrite", "set_output", "focusrite", None),
    ("Monte le volume de 10 points", "set_volume", None, 10),
    ("Baisse le volume de 20 points", "set_volume", None, -20),
])
def test_french_audio_tool_arguments(query, action, device, change):
    from jarvis.tools.registry import generate_tools_json_schema

    message = local_chat([
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": query},
    ], tools=generate_tools_json_schema(allowed_tools=["systemAudio"]))
    calls = message.get("tool_calls", [])
    assert calls, message
    function = calls[0]["function"]
    assert function["name"] == "systemAudio"
    args = function["arguments"]
    if isinstance(args, str):
        args = json.loads(args)
    assert args["action"] == action
    if device:
        assert device in args["device"].casefold()
        assert "volume" not in args and "change" not in args
    if change is not None:
        assert args["change"] == change


@pytest.mark.eval
@requires_judge_llm
def test_french_audio_request_routes_through_the_reply_engine(
    mock_config, eval_db, eval_dialogue_memory,
):
    from jarvis.reply.engine import run_reply_engine
    from jarvis.tools.types import ToolExecutionResult

    mock_config.llm_chat_model = JUDGE_MODEL
    mock_config.fast_model = JUDGE_MODEL
    mock_config.reply_language = "French"
    invoked = []

    def execute(db, cfg, tool_name, tool_args, **kwargs):
        invoked.append((tool_name, tool_args))
        return ToolExecutionResult(
            success=True, reply_text=json.dumps({"device": "Focusrite USB Audio", "volume": 60}),
        )

    with patch("jarvis.reply.engine.run_tool_with_retries", side_effect=execute):
        response = run_reply_engine(
            db=eval_db, cfg=mock_config, tts=None,
            text="Passe la sortie audio sur la Focusrite",
            dialogue_memory=eval_dialogue_memory,
        )
    assert any(
        name == "systemAudio" and args.get("action") == "set_output"
        and "focusrite" in args.get("device", "").casefold()
        for name, args in invoked
    ), (invoked, response)
    assert response
