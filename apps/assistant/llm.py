"""Клиент бесплатной LLM через OpenAI-совместимый API.

Подходит любой провайдер с этим API — задаётся в .env:
  Ollama (локально):  LLM_BASE_URL=http://localhost:11434/v1   LLM_MODEL=qwen2.5:3b
  Google Gemini:      LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
  Groq:               LLM_BASE_URL=https://api.groq.com/openai/v1
  OpenRouter:         LLM_BASE_URL=https://openrouter.ai/api/v1
"""

import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON-строка, как её вернула модель
    # Вызов целиком, как его прислал провайдер. Отправляется обратно без изменений:
    # Gemini 3 кладёт сюда extra_content.google.thought_signature и без неё отвечает 400.
    raw: dict | None = None

    def as_message_part(self) -> dict:
        return self.raw or {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True)
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, tools: list[dict] | None = None, tool_choice=None) -> ChatResult: ...


RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)
MAX_RATE_LIMIT_WAIT = 20.0


def _retry_delay(exc) -> float | None:
    match = RETRY_DELAY_RE.search(str(exc))
    return float(match.group(1)) if match else None


class OpenAICompatibleClient:
    """Бесплатные тарифы часто отвечают 429 (лимит в минуту) и 503 (перегрузка).

    При 429 ждём, сколько просит провайдер (не дольше MAX_RATE_LIMIT_WAIT), и повторяем.
    Если модель всё ещё недоступна — пробуем следующую из списка: лимиты у моделей раздельные.
    """

    def __init__(self, *, base_url: str, api_key: str, models: list[str], timeout: float, sleep=time.sleep):
        from openai import OpenAI

        # Локальной Ollama ключ не нужен, но клиент требует непустую строку.
        # Повторы делаем сами, поэтому встроенные отключены.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=timeout, max_retries=0)
        self._models = models
        self._sleep = sleep

    def chat(self, messages, *, tools=None, tool_choice=None) -> ChatResult:
        import openai

        errors = []
        for model in self._models:
            for attempt in range(2):
                try:
                    return self._create(model, messages, tools, tool_choice)
                except openai.RateLimitError as exc:
                    delay = _retry_delay(exc)
                    if attempt == 0 and delay is not None and delay <= MAX_RATE_LIMIT_WAIT:
                        logger.warning("%s: лимит запросов, ждём %.0f с", model, delay)
                        self._sleep(delay + 0.5)
                        continue
                    errors.append(f"{model}: лимит запросов")
                except (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as exc:
                    errors.append(f"{model}: {type(exc).__name__}")
                except openai.OpenAIError as exc:
                    # 400/401/404 — ошибка запроса или настроек, другая модель не поможет.
                    raise LLMError(f"{model}: {type(exc).__name__}: {exc}") from exc
                break
            logger.warning("Модель %s недоступна, пробуем следующую", model)
        raise LLMError("Все модели недоступны: " + "; ".join(errors))

    def _create(self, model, messages, tools, tool_choice) -> ChatResult:
        kwargs = {"model": model, "messages": messages, "temperature": settings.LLM_TEMPERATURE}
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        response = self._client.chat.completions.create(**kwargs)
        if not response.choices:
            raise LLMError("Модель вернула пустой ответ")
        message = response.choices[0].message
        return ChatResult(
            content=message.content or "",
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=call.function.arguments or "{}",
                    raw=call.model_dump(exclude_none=True),
                )
                for call in message.tool_calls or []
            ],
        )


def _build_client(models: list[str]) -> LLMClient:
    if not settings.LLM_MODEL or not settings.LLM_BASE_URL:
        raise LLMError("ИИ не настроен: задайте LLM_BASE_URL и LLM_MODEL в .env")
    return OpenAICompatibleClient(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        models=list(dict.fromkeys(m for m in models if m)),
        timeout=settings.LLM_TIMEOUT,
    )


@lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """Модель для диалога: много запросов, нужна скорость и высокий лимит."""
    return _build_client([settings.LLM_MODEL, *settings.LLM_FALLBACK_MODELS])


@lru_cache(maxsize=1)
def get_writing_client() -> LLMClient:
    """Модель для оценки письма: один запрос на ученика, нужна точность.
    Если её лимит исчерпан — оценивает модель диалога."""
    return _build_client([settings.LLM_WRITING_MODEL, settings.LLM_MODEL, *settings.LLM_FALLBACK_MODELS])
