"""Белый список функций бэкенда, которые может вызывать ИИ-агент.

Агент не получает доступ к базе: он видит только описания этих функций и их ответы.
Каждая функция работает в рамках одного центра и одной заявки (ToolContext) и сама
проверяет аргументы. Расписание, свободные места и подбор групп агенту недоступны —
он может только передать управление в подбор, который выполняет бэкенд.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from apps.assessment.services import last_completed_session
from apps.booking.services import active_bookings
from apps.catalog.models import Level
from apps.leads.models import Lead

from .models import FaqItem

# Действия, которые бот выполняет после ответа агента.
ACTION_START_TEST = "start_test"
ACTION_SELECT_GROUP = "select_group"
ACTION_CONFIRM_CANCEL = "confirm_cancel"  # f"{ACTION_CONFIRM_CANCEL}:{booking_id}"


@dataclass
class ToolContext:
    lead: Lead
    language: str = "ru"
    actions: list[str] = field(default_factory=list)

    @property
    def center(self):
        return self.lead.center


class ToolError(Exception):
    """Ошибка аргументов: текст возвращается модели, чтобы она исправилась."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., dict]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict | None = None, required: tuple[str, ...] = ()):
    def register(func):
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters={"type": "object", "properties": properties or {}, "required": list(required)},
            func=func,
        )
        return func

    return register


def tool_schemas() -> list[dict]:
    return [t.schema() for t in REGISTRY.values()]


def execute(ctx: ToolContext, name: str, arguments: str) -> dict:
    """Выполнить вызов модели. Любая ошибка превращается в {"error": ...}, а не в исключение."""
    tool_ = REGISTRY.get(name)
    if tool_ is None:
        return {"error": f"Неизвестная функция {name!r}. Доступны: {', '.join(REGISTRY)}"}
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {"error": "Аргументы должны быть JSON-объектом"}
    if not isinstance(args, dict):
        return {"error": "Аргументы должны быть JSON-объектом"}
    allowed = set(tool_.parameters["properties"])
    unknown = set(args) - allowed
    if unknown:
        return {"error": f"Лишние аргументы: {', '.join(sorted(unknown))}"}
    missing = [p for p in tool_.parameters["required"] if p not in args]
    if missing:
        return {"error": f"Не хватает аргументов: {', '.join(missing)}"}
    try:
        return tool_.func(ctx, **args)
    except ToolError as exc:
        return {"error": str(exc)}


LEVEL_ENUM = [value for value, _ in Level.choices]


def _level(value) -> str:
    if value not in LEVEL_ENUM:
        raise ToolError(f"declared_level должен быть одним из {LEVEL_ENUM}")
    return value


@tool(
    "get_center_info",
    "Название центра, филиалы с адресами, курсы с описанием и ценой в месяц. "
    "Вызывай перед любым ответом о курсах, ценах или филиалах.",
)
def get_center_info(ctx: ToolContext) -> dict:
    center = ctx.center
    return {
        "name": center.name,
        "branches": [{"name": b.name, "address": b.address} for b in center.branches.filter(is_active=True)],
        "courses": [
            {"name": c.name, "description": c.description, "price_per_month_uzs": int(c.price_per_month)}
            for c in center.courses.filter(is_active=True)
        ],
    }


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


@tool(
    "search_faq",
    "Поиск в утверждённой базе знаний центра (оплата, пробный урок, длительность занятий и т.п.). "
    "Если ничего не найдено — не придумывай ответ, а предложи передать вопрос менеджеру.",
    {"query": {"type": "string", "description": "Вопрос ученика своими словами"}},
    required=("query",),
)
def search_faq(ctx: ToolContext, query: str) -> dict:
    items = list(
        FaqItem.objects.filter(center=ctx.center, is_active=True, language__in=["", ctx.language])
    )
    query_words = _words(str(query))
    # Простое совпадение слов (с учётом начала слова — «оплата»/«оплатить»).
    def score(item):
        item_words = _words(f"{item.question} {item.answer}")
        return sum(any(w.startswith(q[:5]) or q.startswith(w[:5]) for w in item_words) for q in query_words)

    ranked = sorted(((score(i), i) for i in items), key=lambda pair: pair[0], reverse=True)
    found = [{"question": i.question, "answer": i.answer} for s, i in ranked if s > 0][:3]
    if not found:
        return {"results": [], "note": "В базе знаний ответа нет. Не придумывай; предложи передать вопрос менеджеру."}
    return {"results": found}


@tool(
    "save_student_info",
    "Сохранить цель обучения и/или уровень английского, который назвал сам ученик.",
    {
        "goal": {"type": "string", "description": "Цель обучения, кратко: IELTS, работа, учёба за рубежом…"},
        "declared_level": {"type": "string", "enum": LEVEL_ENUM, "description": "Уровень со слов ученика"},
    },
)
def save_student_info(ctx: ToolContext, goal: str | None = None, declared_level: str | None = None) -> dict:
    lead = ctx.lead
    fields = []
    if goal is not None:
        goal = str(goal).strip()[:500]
        if goal:
            lead.goal = goal
            fields.append("goal")
    if declared_level is not None:
        lead.declared_level = _level(declared_level)
        fields.append("declared_level")
    if not fields:
        raise ToolError("Передай goal и/или declared_level")
    lead.save(update_fields=[*fields, "updated_at"])
    return {"status": "saved", "saved": fields}


@tool(
    "start_level_test",
    "Запустить тест уровня английского. Бот сам покажет вопросы кнопками и проверит ответы; "
    "для уровня B1 и выше будет письменное задание. Не задавай тестовые вопросы сам.",
    {
        "declared_level": {"type": "string", "enum": LEVEL_ENUM, "description": "Уровень со слов ученика, если назвал"},
        "retake": {"type": "boolean", "description": "true — пройти заново, если тест уже пройден"},
    },
)
def start_level_test(ctx: ToolContext, declared_level: str | None = None, retake: bool = False) -> dict:
    lead = ctx.lead
    if declared_level is not None:
        lead.declared_level = _level(declared_level)
        lead.save(update_fields=["declared_level", "updated_at"])
    previous = last_completed_session(lead)
    if previous and not retake:
        return {
            "status": "already_tested",
            "level": previous.final_level,
            "note": "Тест уже пройден. Если ученик хочет пройти заново — вызови с retake=true.",
        }
    ctx.actions.append(ACTION_START_TEST)
    return {"status": "test_started", "note": "Бот сейчас покажет вопросы. Коротко пожелай удачи, без вопросов теста."}


@tool(
    "get_test_result",
    "Результат последнего пройденного теста уровня.",
)
def get_test_result(ctx: ToolContext) -> dict:
    session = last_completed_session(ctx.lead)
    if session is None:
        return {"status": "not_tested"}
    return {
        "status": "tested",
        "level": session.final_level,
        "confidence": session.confidence,
        "needs_teacher_review": session.needs_review,
    }


@tool(
    "start_group_selection",
    "Передать ученика в подбор группы. Дни, время, свободные места и группы подбирает только бэкенд — "
    "бот спросит удобные дни и время и покажет варианты. Сам группы и расписание не называй.",
)
def start_group_selection(ctx: ToolContext) -> dict:
    lead = ctx.lead
    if not (lead.assessed_level or lead.declared_level):
        raise ToolError("Уровень неизвестен. Сначала предложи тест уровня (start_level_test).")
    ctx.actions.append(ACTION_SELECT_GROUP)
    return {"status": "ok", "note": "Бот сейчас покажет выбор дней и времени."}


@tool(
    "request_booking_cancellation",
    "Ученик хочет отменить запись или пробное занятие. Бот покажет ему кнопку подтверждения — "
    "отменит только сам ученик нажатием. booking_id бери из списка записей в данных ученика. "
    "Не говори, что запись уже отменена.",
    {"booking_id": {"type": "integer", "description": "Номер записи (booking #...)"}},
    required=("booking_id",),
)
def request_booking_cancellation(ctx: ToolContext, booking_id: int) -> dict:
    if isinstance(booking_id, bool) or not isinstance(booking_id, int):
        raise ToolError("booking_id должен быть числом")
    if not active_bookings(ctx.lead).filter(pk=booking_id).exists():
        raise ToolError("У ученика нет действующей записи с таким номером")
    ctx.actions.append(f"{ACTION_CONFIRM_CANCEL}:{booking_id}")
    return {"status": "confirmation_shown", "note": "Бот показал кнопку подтверждения. Запись ещё НЕ отменена."}


@tool(
    "handoff_to_manager",
    "Передать вопрос менеджеру центра. Только если ученик просит человека, жалуется, "
    "или спрашивает об обучении в центре, а в фактах нет ответа. Не для вопросов не по теме "
    "и не для записи в группу (для неё — start_group_selection).",
    {"reason": {"type": "string", "description": "Кратко: что нужно менеджеру"}},
    required=("reason",),
)
def handoff_to_manager(ctx: ToolContext, reason: str) -> dict:
    lead = ctx.lead
    reason = str(reason).strip()[:500]
    if not reason:
        raise ToolError("reason не может быть пустым")
    lead.manager_note = f"{lead.manager_note}\n{reason}".strip()[:5000]
    lead.status = Lead.Status.NEEDS_MANAGER
    lead.save(update_fields=["manager_note", "status", "updated_at"])
    return {"status": "sent", "note": "Скажи ученику, что менеджер свяжется с ним."}
