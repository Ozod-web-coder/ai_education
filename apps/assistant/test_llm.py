import httpx
import openai
import pytest

from apps.assistant.llm import ChatResult, LLMError, OpenAICompatibleClient


def api_error(cls, status, message="error"):
    request = httpx.Request("POST", "https://llm.test/v1/chat/completions")
    return cls(message, response=httpx.Response(status, request=request), body=None)


def make_client(script, models=("main", "backup")):
    """script: model -> список результатов (исключение или ChatResult) по порядку."""
    sleeps, calls = [], []
    client = OpenAICompatibleClient(
        base_url="https://llm.test/v1", api_key="k", models=list(models), timeout=5, sleep=sleeps.append
    )

    def fake_create(model, messages, tools, tool_choice):
        calls.append(model)
        result = script[model].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    client._create = fake_create
    return client, calls, sleeps


OK = ChatResult(content="ok")


def test_waits_on_rate_limit_and_retries():
    limit = api_error(openai.RateLimitError, 429, "Quota exceeded. Please retry in 10.7s.")
    client, calls, sleeps = make_client({"main": [limit, OK]})
    assert client.chat([]) == OK
    assert calls == ["main", "main"] and sleeps == [pytest.approx(11.2)]


def test_long_rate_limit_switches_model():
    limit = api_error(openai.RateLimitError, 429, "Please retry in 45s.")
    client, calls, sleeps = make_client({"main": [limit], "backup": [OK]})
    assert client.chat([]) == OK
    assert calls == ["main", "backup"] and sleeps == []


def test_overloaded_model_switches():
    client, calls, _ = make_client({"main": [api_error(openai.InternalServerError, 503)], "backup": [OK]})
    assert client.chat([]) == OK and calls == ["main", "backup"]


def test_bad_request_does_not_switch():
    client, calls, _ = make_client({"main": [api_error(openai.BadRequestError, 400)], "backup": [OK]})
    with pytest.raises(LLMError):
        client.chat([])
    assert calls == ["main"]


def test_all_models_down():
    down = {m: [api_error(openai.InternalServerError, 503)] for m in ("main", "backup")}
    client, _, _ = make_client(down)
    with pytest.raises(LLMError, match="Все модели недоступны"):
        client.chat([])
