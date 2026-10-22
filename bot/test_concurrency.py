"""Нажатия кнопок не должны ждать ответа ИИ."""

import asyncio
import time
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync

from apps.assistant import agent
from apps.assistant.llm import ChatResult
from bot import db

TG = SimpleNamespace(id=901, first_name="Ali", username="ali", language_code="ru")
AI_THINKING = 3.0


class SlowLLM:
    def chat(self, messages, *, tools=None, tool_choice=None):
        time.sleep(AI_THINKING)
        return ChatResult(content="Ответ ИИ")


@pytest.mark.django_db(transaction=True)
def test_buttons_do_not_wait_for_ai(center, monkeypatch, question_bank):
    monkeypatch.setattr(agent, "get_client", lambda: SlowLLM())
    async_to_sync(db.ensure_user)(center, TG)

    async def scenario():
        ai = asyncio.create_task(db.agent_reply(center, TG.id, "Вопрос", "ru"))
        await asyncio.sleep(0.2)  # ИИ уже думает
        started = time.monotonic()
        await db.get_language(TG.id)
        await db.start_test(center, TG.id)
        await db.profile(center, TG.id)
        fast = time.monotonic() - started
        await ai
        return fast

    fast = asyncio.run(scenario())
    assert fast < 1.0, f"кнопки ждали ИИ {fast:.1f} с"
