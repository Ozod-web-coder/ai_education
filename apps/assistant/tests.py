import json

import pytest

from apps.assessment import services as assessment
from apps.assistant import agent, tools
from apps.assistant.llm import ChatResult, LLMError, ToolCall
from apps.assistant.models import FaqItem, Message
from apps.assistant.testing import FakeLLM, call, text
from apps.catalog.models import Level
from apps.leads.models import Lead


def execute(lead, name, language="ru", **arguments):
    ctx = tools.ToolContext(lead=lead, language=language)
    return ctx, tools.execute(ctx, name, json.dumps(arguments))


class TestToolWhitelist:
    def test_only_whitelisted_functions(self):
        names = {schema["function"]["name"] for schema in tools.tool_schemas()}
        assert names == {
            "get_center_info", "search_faq", "save_student_info", "start_level_test",
            "get_test_result", "start_group_selection", "handoff_to_manager", "request_booking_cancellation",
        }

    def test_unknown_function(self, lead):
        _, output = execute(lead, "find_matching_groups")
        assert "error" in output

    def test_bad_arguments(self, lead):
        ctx = tools.ToolContext(lead=lead)
        assert "error" in tools.execute(ctx, "search_faq", "not json")
        assert "error" in tools.execute(ctx, "search_faq", "{}")
        assert "error" in tools.execute(ctx, "search_faq", '{"query": "x", "sql": "drop"}')


class TestTools:
    def test_center_info_comes_from_database(self, lead, course, branch):
        _, info = execute(lead, "get_center_info")
        assert info["courses"] == [
            {"name": "General English", "description": "", "price_per_month_uzs": 600000}
        ]
        assert info["branches"][0]["name"] == "Чиланзар"

    def test_faq_search_by_language(self, lead, center):
        FaqItem.objects.create(center=center, language="ru", question="Как оплатить обучение?", answer="Click или Payme")
        FaqItem.objects.create(center=center, language="uz", question="Qanday to'lanadi?", answer="Click yoki Payme")
        _, ru = execute(lead, "search_faq", query="Можно оплатить через Click?")
        assert ru["results"] == [{"question": "Как оплатить обучение?", "answer": "Click или Payme"}]
        _, uz = execute(lead, "search_faq", language="uz", query="qanday to'lanadi")
        assert uz["results"][0]["answer"] == "Click yoki Payme"

    def test_faq_not_found(self, lead, center):
        _, output = execute(lead, "search_faq", query="есть ли бассейн")
        assert output["results"] == [] and "менеджер" in output["note"]

    def test_save_student_info(self, lead):
        _, output = execute(lead, "save_student_info", goal="IELTS 7", declared_level="B2")
        lead.refresh_from_db()
        assert output["status"] == "saved" and lead.goal == "IELTS 7" and lead.declared_level == "B2"
        _, bad = execute(lead, "save_student_info", declared_level="Z1")
        assert "error" in bad

    def test_group_selection_needs_level(self, lead):
        ctx, output = execute(lead, "start_group_selection")
        assert "error" in output and ctx.actions == []
        lead.declared_level = Level.B1
        lead.save()
        ctx, output = execute(lead, "start_group_selection")
        assert ctx.actions == [tools.ACTION_SELECT_GROUP]

    def test_start_test_and_retake(self, lead, question_bank):
        ctx, output = execute(lead, "start_level_test", declared_level="A2")
        assert ctx.actions == [tools.ACTION_START_TEST] and output["status"] == "test_started"

        assessment.start_test(lead)
        assessment._finish(lead.test_sessions.first(), final_level=Level.A2, confidence="high", needs_review=False)
        ctx, output = execute(lead, "start_level_test")
        assert output == {"status": "already_tested", "level": "A2", "note": output["note"]} and ctx.actions == []
        ctx, _ = execute(lead, "start_level_test", retake=True)
        assert ctx.actions == [tools.ACTION_START_TEST]

    def test_cancellation_only_shows_confirmation(self, lead, make_group, make_lead):
        from apps.booking import services as booking_services
        from apps.booking.models import Booking

        own = booking_services.confirm_booking(booking_services.create_hold(lead=lead, group_id=make_group().id))
        foreign = booking_services.create_hold(lead=make_lead(), group_id=make_group().id)

        ctx, output = execute(lead, "request_booking_cancellation", booking_id=own.id)
        assert ctx.actions == [f"{tools.ACTION_CONFIRM_CANCEL}:{own.id}"]
        own.refresh_from_db()
        assert own.status == Booking.Status.CONFIRMED  # функция ничего не отменяет

        for bad_id in (foreign.id, 999999, "1"):
            ctx, output = execute(lead, "request_booking_cancellation", booking_id=bad_id)
            assert "error" in output and ctx.actions == []

    def test_handoff(self, lead):
        execute(lead, "handoff_to_manager", reason="Спрашивает про корпоративное обучение")
        lead.refresh_from_db()
        assert lead.status == Lead.Status.NEEDS_MANAGER and "корпоративное" in lead.manager_note


class TestAgent:
    def test_plain_answer(self, lead):
        llm = FakeLLM(text("Здравствуйте! Чем помочь?"))
        reply = agent.reply(lead, "Привет", client=llm)
        assert reply.text == "Здравствуйте! Чем помочь?" and reply.actions == []
        system = llm.calls[0]["messages"][0]
        assert system["role"] == "system" and "Russian" in system["content"] and "Ученик" in system["content"]

    def test_own_bookings_in_prompt(self, lead, make_group):
        from apps.booking import services as booking_services

        booking = booking_services.confirm_booking(
            booking_services.create_hold(lead=lead, group_id=make_group(name="B1 вечер").id)
        )
        prompt = agent.system_prompt(lead, "ru")
        assert f'booking #{booking.id} (confirmed): group "B1 вечер"' in prompt
        assert "Вт 18:30–20:00, Чт 18:30–20:00" in prompt

    def test_center_facts_in_prompt(self, lead, center, course, branch):
        course.description = "Грамматика, лексика, разговор"
        course.save()
        FaqItem.objects.create(center=center, language="ru", question="Есть пробный урок?", answer="Да, бесплатный")
        FaqItem.objects.create(center=center, language="uz", question="Sinov darsi?", answer="Ha")
        prompt = agent.system_prompt(lead, "ru")
        assert "General English — 600 000 — Грамматика, лексика, разговор" in prompt
        assert "Чиланзар" in prompt and "Да, бесплатный" in prompt and "Sinov" not in prompt

    def test_tool_call_then_answer(self, lead, question_bank):
        llm = FakeLLM(call("start_level_test", declared_level="B1"), text("Удачи на тесте!"))
        reply = agent.reply(lead, "Хочу проверить уровень, думаю B1", language="uz", client=llm)
        assert reply.text == "Удачи на тесте!" and reply.actions == [tools.ACTION_START_TEST]
        # Второй запрос содержит результат функции.
        tool_message = llm.calls[1]["messages"][-1]
        assert tool_message["role"] == "tool" and json.loads(tool_message["content"])["status"] == "test_started"
        assert "Uzbek" in llm.calls[0]["messages"][0]["content"]
        roles = list(lead.conversations.get().messages.values_list("role", flat=True))
        assert roles == ["user", "assistant", "tool", "assistant"]

    def test_provider_fields_sent_back(self, lead):
        """Gemini 3 требует вернуть thought_signature вместе с вызовом функции."""
        raw = {
            "id": "c1", "type": "function", "function": {"name": "get_center_info", "arguments": "{}"},
            "extra_content": {"google": {"thought_signature": "SIG"}},
        }
        first = ChatResult(content="", tool_calls=[ToolCall(id="c1", name="get_center_info", arguments="{}", raw=raw)])
        llm = FakeLLM(first, text("Цены такие…"))
        agent.reply(lead, "Цены?", client=llm)
        assistant_message = llm.calls[1]["messages"][-2]
        assert assistant_message["tool_calls"] == [raw]
        # И в истории из базы тоже: следующий запрос пойдёт с подписью.
        llm = FakeLLM(text("ok"))
        agent.reply(lead, "Ещё вопрос", client=llm)
        stored = [m for m in llm.calls[0]["messages"] if m.get("tool_calls")]
        assert stored[0]["tool_calls"] == [raw]

    def test_history_is_kept(self, lead):
        agent.reply(lead, "Первый вопрос", client=FakeLLM(text("Первый ответ")))
        llm = FakeLLM(text("Второй ответ"))
        agent.reply(lead, "Второй вопрос", client=llm)
        contents = [m["content"] for m in llm.calls[0]["messages"][1:]]
        assert contents == ["Первый вопрос", "Первый ответ", "Второй вопрос"]

    def test_tool_error_returned_to_model(self, lead):
        llm = FakeLLM(call("start_group_selection"), text("Сначала пройдём тест."))
        reply = agent.reply(lead, "Запишите меня", client=llm)
        assert reply.actions == []
        assert "error" in json.loads(llm.calls[1]["messages"][-1]["content"])

    def test_llm_failure(self, lead):
        with pytest.raises(LLMError):
            agent.reply(lead, "Привет", client=FakeLLM(LLMError("timeout")))
        with pytest.raises(LLMError):
            agent.reply(lead, "Привет", client=FakeLLM(text("   ")))

    def test_silent_after_action_is_ok(self, lead):
        lead.declared_level = Level.B1
        lead.save()
        reply = agent.reply(lead, "Во сколько занятия?", client=FakeLLM(call("start_group_selection"), text("")))
        assert reply.text == "" and reply.actions == [tools.ACTION_SELECT_GROUP]

    def test_endless_tool_loop(self, lead):
        loop = [call("get_center_info", call_id=f"c{i}") for i in range(agent.MAX_TOOL_ROUNDS)]
        with pytest.raises(LLMError):
            agent.reply(lead, "Привет", client=FakeLLM(*loop))

    def test_not_configured(self, lead):
        with pytest.raises(LLMError, match="не настроен"):
            agent.reply(lead, "Привет")

    def test_long_message_truncated(self, lead):
        agent.reply(lead, "a" * 5000, client=FakeLLM(text("ok")))
        assert len(Message.objects.filter(role="user").get().content) == agent.MAX_USER_MESSAGE
