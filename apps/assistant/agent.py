"""ИИ-консультант: отвечает на вопросы о центре, выясняет цель и уровень, запускает тест.

Модель получает только системный промпт, историю диалога и описания функций из tools.py.
Действия, которые нужно выполнить боту (запустить тест, перейти к подбору группы),
возвращаются в AgentReply.actions.
"""

import json
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.assessment.services import last_completed_session
from apps.booking.services import active_bookings
from apps.leads.models import Lead

from . import tools
from .llm import LLMClient, LLMError, get_client
from .models import Conversation, FaqItem, Message

MAX_TOOL_ROUNDS = 5
HISTORY_LIMIT = 30
MAX_USER_MESSAGE = 1000

LANGUAGE_NAMES = {"ru": "Russian", "uz": "Uzbek (Latin script)", "en": "English"}

SYSTEM_PROMPT = """\
You are the admissions assistant of the education center "{center}" in a Telegram bot.
Always reply in {language}. Keep replies short: 1–4 sentences, friendly, no markdown.
Address the student politely and formally (in Russian «вы», in Uzbek «siz»).

Your job:
1. Answer the student's questions about the center, courses, prices, branches and rules.
2. Find out the student's goal (save it with save_student_info).
3. Ask what English level the student thinks they have, then offer the level test (start_level_test).
4. After the test, explain the result in one sentence and offer to choose a group (start_group_selection).

Strict rules:
- Facts about the center, courses, prices, branches and rules come ONLY from the approved facts below.
  Never guess and never claim the center has or does not have something the facts do not mention.
- NEVER name groups, days, times, schedules, start dates or free seats, and never promise a place.
  Only the backend chooses groups: call start_group_selection and the bot will ask for days and time.
  This includes requests to enroll in a specific group, day or time — the backend checks them.
  Exception: you MAY tell the student about THEIR OWN bookings listed in the student data, exactly as written.
- If the student wants to cancel a booking or the trial lesson, call request_booking_cancellation with its
  number. The bot shows a confirmation button; never say the booking is already cancelled.
- Do not ask test questions and do not judge the level yourself: the bot runs the test.
- Do not ask for phone numbers, last names or emails: the bot collects contacts itself.
- Call handoff_to_manager ONLY when: the student asks for a human, has a complaint, or asks about
  studying at the center and the facts have no answer. Then tell the student a manager will contact them.
- Topics unrelated to studying at the center (other services, general chat, homework help): politely
  say you can only help with studying at the center. Do NOT call handoff_to_manager for them.

Known data about the student:
{student}

Approved facts about the center (the only source of truth):
{facts}
"""


@dataclass
class AgentReply:
    text: str
    actions: list[str] = field(default_factory=list)


def _student_summary(lead: Lead) -> str:
    session = last_completed_session(lead)
    lines = [
        f"- name: {lead.name or 'unknown'}",
        f"- age: {lead.age if lead.age is not None else 'unknown'}",
        f"- goal: {lead.goal or 'unknown'}",
        f"- self-declared level: {lead.declared_level or 'unknown'}",
    ]
    if session:
        review = " (a teacher will double-check it)" if session.needs_review else ""
        lines.append(f"- level test: completed, result {session.final_level}{review}")
    else:
        lines.append("- level test: not taken yet")
    bookings = list(active_bookings(lead))
    if not bookings:
        lines.append("- bookings: none")
    for b in bookings:
        group = b.group
        schedule = ", ".join(str(slot) for slot in group.slots.all())
        trial = f"{timezone.localtime(b.trial_at):%d.%m.%Y %H:%M}" if b.trial_at else "not set"
        lines.append(
            f"- booking #{b.id} ({b.status}): group \"{group.name}\", course {group.course.name}, "
            f"branch {group.branch.name}, trial lesson {trial}, group started {group.start_date:%d.%m.%Y}, "
            f"schedule {schedule}"
        )
    return "\n".join(lines)


def _center_facts(lead: Lead, language: str) -> str:
    """Факты из базы прямо в промпте: ответы опираются на них, и на каждый ход
    уходит меньше запросов к модели (на бесплатном тарифе лимит — несколько в минуту)."""
    info = tools.get_center_info(tools.ToolContext(lead=lead, language=language))
    lines = ["Branches:"]
    lines += [f"- {b['name']}: {b['address']}" for b in info["branches"]]
    lines.append("Courses (price per month, UZS):")
    lines += [
        f"- {c['name']} — {c['price_per_month_uzs']:,}".replace(",", " ") + f" — {c['description']}"
        for c in info["courses"]
    ]
    faq = FaqItem.objects.filter(center=lead.center, is_active=True, language__in=["", language])
    if faq:
        lines.append("FAQ:")
        for item in faq:
            lines += [f"Q: {item.question}", f"A: {item.answer}"]
    return "\n".join(lines)


def system_prompt(lead: Lead, language: str) -> str:
    return SYSTEM_PROMPT.format(
        center=lead.center.name,
        language=LANGUAGE_NAMES.get(language, "Russian"),
        student=_student_summary(lead),
        facts=_center_facts(lead, language),
    )


def get_conversation(lead: Lead) -> Conversation:
    conversation = lead.conversations.first()
    return conversation or Conversation.objects.create(center=lead.center, lead=lead)


def _history(conversation: Conversation) -> list[dict]:
    messages = list(conversation.messages.order_by("-id")[:HISTORY_LIMIT])[::-1]
    # Срез мог отрезать начало цепочки вызова функции — убираем «осиротевшие» результаты.
    while messages and messages[0].role == Message.Role.TOOL:
        messages.pop(0)
    return [m.as_llm_message() for m in messages]


def _save(conversation: Conversation, role: str, content: str = "", tool_calls=None, tool_call_id: str = ""):
    Message.objects.create(
        conversation=conversation, role=role, content=content, tool_calls=tool_calls, tool_call_id=tool_call_id
    )


def reply(lead: Lead, user_text: str, *, language: str = "ru", client: LLMClient | None = None) -> AgentReply:
    """Ответить на сообщение ученика. Бросает LLMError, если модель недоступна."""
    client = client or get_client()
    conversation = get_conversation(lead)
    _save(conversation, Message.Role.USER, user_text.strip()[:MAX_USER_MESSAGE])

    ctx = tools.ToolContext(lead=lead, language=language)
    schemas = tools.tool_schemas()
    messages = [{"role": "system", "content": system_prompt(lead, language)}, *_history(conversation)]

    for _ in range(MAX_TOOL_ROUNDS):
        result = client.chat(messages, tools=schemas)
        if not result.tool_calls:
            text = result.content.strip()
            if not text:
                # После start_group_selection модель часто молчит — бот сам перейдёт к действию.
                if ctx.actions:
                    return AgentReply(text="", actions=ctx.actions)
                raise LLMError("Модель вернула пустой ответ")
            _save(conversation, Message.Role.ASSISTANT, text)
            return AgentReply(text=text, actions=ctx.actions)

        raw_calls = [call.as_message_part() for call in result.tool_calls]
        _save(conversation, Message.Role.ASSISTANT, result.content, tool_calls=raw_calls)
        messages.append({"role": "assistant", "content": result.content, "tool_calls": raw_calls})

        for call in result.tool_calls:
            # Каждая функция — в своей транзакции: ошибка одной не откатывает другие.
            with transaction.atomic():
                output = tools.execute(ctx, call.name, call.arguments)
            payload = json.dumps(output, ensure_ascii=False, default=str)
            _save(conversation, Message.Role.TOOL, payload, tool_call_id=call.id)
            messages.append({"role": "tool", "content": payload, "tool_call_id": call.id})

    # Модель зациклилась на вызовах. Если действие уже выбрано — бот его выполнит.
    if ctx.actions:
        return AgentReply(text="", actions=ctx.actions)
    raise LLMError("Модель не дала ответа за отведённое число шагов")
