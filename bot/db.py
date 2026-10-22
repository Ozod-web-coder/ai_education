"""Доступ к Django из асинхронного бота.

ORM синхронный, поэтому каждая функция обёрнута в sync_to_async и возвращает
простые dataclass-ы: в async-коде нельзя трогать ленивые связи моделей.
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from asgiref.sync import sync_to_async
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from apps.assessment import services as assessment
from apps.assessment import writing
from apps.assistant import agent
from apps.assistant.llm import LLMError
from apps.booking import services as booking_services
from apps.booking.models import Booking
from apps.catalog.models import Group
from apps.core.models import Center, User
from apps.core.services import get_or_create_telegram_user
from apps.leads.models import Lead


class BookingNotFound(booking_services.BookingError):
    pass


@dataclass(frozen=True)
class GroupOption:
    id: int
    name: str
    course: str
    branch: str
    start_date: date
    slots: tuple[tuple[int, time, time], ...]
    price: int
    free_seats: int | None = None
    trial_at: datetime | None = None  # ближайший пробный урок (только в результатах поиска)


@dataclass(frozen=True)
class BookingInfo:
    id: int
    status: str
    trial_at: datetime | None
    group: GroupOption


@dataclass(frozen=True)
class Profile:
    """Что бот знает об ученике из базы — переживает перезапуск бота."""

    onboarded: bool
    consented: bool
    name: str
    language: str
    level: str | None
    tested: bool
    bookings: tuple[BookingInfo, ...]


@dataclass(frozen=True)
class AgentAnswer:
    text: str
    actions: tuple[str, ...]


@dataclass(frozen=True)
class TestStep:
    kind: str  # "question" | "writing" | "done"
    question_id: int | None = None
    number: int | None = None
    text: str = ""
    options: tuple[str, ...] = ()
    min_words: int | None = None
    level: str = ""
    needs_review: bool = False


# --- Преобразование моделей в dataclass-ы --------------------------------------


def _group_option(group: Group) -> GroupOption:
    trial = getattr(group, "trial", None)
    return GroupOption(
        id=group.id,
        name=group.name,
        course=group.course.name,
        branch=group.branch.name,
        start_date=group.start_date,
        slots=tuple((s.weekday, s.start_time, s.end_time) for s in group.slots.all()),
        price=int(group.course.price_per_month),
        free_seats=getattr(group, "free_seats", None),
        trial_at=trial.starts_at if trial else None,
    )


def _booking_info(booking: Booking) -> BookingInfo:
    return BookingInfo(id=booking.id, status=booking.status, trial_at=booking.trial_at, group=_group_option(booking.group))


def _step_view(step) -> TestStep:
    if isinstance(step, assessment.NextQuestion):
        q = step.question
        return TestStep(kind="question", question_id=q.id, number=step.number, text=q.text, options=tuple(q.options))
    if isinstance(step, assessment.NeedWriting):
        return TestStep(kind="writing", text=step.task.prompt, min_words=step.task.min_words)
    return _done_view(step.session)


def _done_view(session) -> TestStep:
    return TestStep(kind="done", level=session.final_level, needs_review=session.needs_review)


# --- Поиск объектов ученика ---------------------------------------------------


def _lead(center: Center, telegram_id: int) -> Lead:
    lead, _ = Lead.objects.get_or_create(
        center=center, user=User.objects.get(telegram_id=telegram_id), defaults={"source": "telegram_bot"}
    )
    return lead


def _booking(center: Center, telegram_id: int, booking_id: int) -> Booking:
    """Только запись самого ученика: чужой номер записи даёт BookingNotFound."""
    try:
        return (
            Booking.objects.select_related("group__course", "group__branch")
            .prefetch_related("group__slots")
            .get(pk=booking_id, center=center, lead__user__telegram_id=telegram_id)
        )
    except Booking.DoesNotExist as exc:
        raise BookingNotFound from exc


def _active_session(center: Center, telegram_id: int):
    session = assessment.active_session(_lead(center, telegram_id))
    if session is None:
        raise assessment.InvalidState("Нет активного теста")
    return session


def _llm_call(func):
    """Запросы к ИИ идут секундами: выполняем их не в общем потоке ORM,
    чтобы бот не ждал одного ученика, отвечая другим."""

    def wrapper(*args, **kwargs):
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            # Поток из пула может долго не использоваться — не держим его соединение с базой.
            connections.close_all()

    return sync_to_async(wrapper, thread_sensitive=False)


# --- Пользователь и анкета ----------------------------------------------------


@sync_to_async
def get_center(slug: str) -> Center:
    return Center.objects.get(slug=slug, is_active=True)


@sync_to_async
def ensure_user(center: Center, tg_user) -> None:
    get_or_create_telegram_user(
        telegram_id=tg_user.id,
        first_name=tg_user.first_name or "",
        telegram_username=tg_user.username or "",
        language_code=tg_user.language_code or "",
        default_language=center.default_language,
    )


@sync_to_async
def get_language(telegram_id: int) -> str | None:
    return User.objects.filter(telegram_id=telegram_id).values_list("language", flat=True).first()


@sync_to_async
def set_language(telegram_id: int, language: str) -> None:
    User.objects.filter(telegram_id=telegram_id).update(language=language)


@sync_to_async
def profile(center: Center, telegram_id: int) -> Profile:
    user = User.objects.filter(telegram_id=telegram_id).first()
    lead = Lead.objects.filter(center=center, user=user).first() if user else None
    if lead is None:
        return Profile(False, False, "", user.language if user else center.default_language, None, False, ())
    # Анкета заполнена, если пройдены все обязательные шаги, включая согласие родителя.
    onboarded = bool(
        lead.personal_data_consent_at
        and lead.name
        and lead.age is not None
        and (not lead.is_minor or (lead.parent_phone and lead.parent_consent_at))
    )
    return Profile(
        onboarded=onboarded,
        consented=lead.personal_data_consent_at is not None,
        name=lead.name,
        language=user.language,
        level=lead.assessed_level or lead.declared_level or None,
        tested=assessment.last_completed_session(lead) is not None,
        bookings=tuple(_booking_info(b) for b in booking_services.active_bookings(lead)),
    )


@sync_to_async
def accept_consent(center: Center, telegram_id: int, *, parent: bool = False) -> None:
    lead = _lead(center, telegram_id)
    field = "parent_consent_at" if parent else "personal_data_consent_at"
    if getattr(lead, field) is None:
        setattr(lead, field, timezone.now())
        lead.save(update_fields=[field, "updated_at"])


@sync_to_async
def update_lead(center: Center, telegram_id: int, **fields) -> None:
    lead = _lead(center, telegram_id)
    for name, value in fields.items():
        setattr(lead, name, value)
    lead.save(update_fields=[*fields, "updated_at"])


@sync_to_async
@transaction.atomic
def save_contact(center: Center, telegram_id: int, phone: str) -> None:
    """Телефон из кнопки «Отправить номер»: принадлежит аккаунту и становится контактом заявки."""
    User.objects.filter(telegram_id=telegram_id).update(phone=phone)
    lead = _lead(center, telegram_id)
    lead.phone = phone
    lead.save(update_fields=["phone", "updated_at"])


# --- Подбор группы и записи ---------------------------------------------------


@sync_to_async
def search_groups(center: Center, *, level: str, weekdays: set[int], period: str, age: int | None) -> list[GroupOption]:
    groups = booking_services.find_matching_groups(center, level=level, weekdays=weekdays, period=period, age=age)
    return [_group_option(g) for g in groups]


@sync_to_async
def hold(center: Center, telegram_id: int, group_id: int, trial_at: datetime | None) -> BookingInfo:
    booking = booking_services.create_hold(lead=_lead(center, telegram_id), group_id=group_id, trial_at=trial_at)
    return _booking_info(_booking(center, telegram_id, booking.id))


def _change_booking(action):
    @sync_to_async
    def run(center: Center, telegram_id: int, booking_id: int) -> BookingInfo:
        action(_booking(center, telegram_id, booking_id))
        return _booking_info(_booking(center, telegram_id, booking_id))

    return run


confirm = _change_booking(booking_services.confirm_booking)
cancel = _change_booking(booking_services.cancel_booking)


@sync_to_async
def active_booking(center: Center, telegram_id: int, booking_id: int) -> BookingInfo:
    booking = booking_services.active_bookings(_lead(center, telegram_id)).filter(pk=booking_id).first()
    if booking is None:
        raise BookingNotFound
    return _booking_info(booking)


# --- ИИ-консультант и тест уровня -------------------------------------------


@_llm_call
def agent_reply(center: Center, telegram_id: int, text: str, language: str) -> AgentAnswer:
    reply = agent.reply(_lead(center, telegram_id), text, language=language)
    return AgentAnswer(text=reply.text, actions=tuple(reply.actions))


@sync_to_async
def start_test(center: Center, telegram_id: int) -> TestStep:
    return _step_view(assessment.start_test(_lead(center, telegram_id)))


@sync_to_async
def answer_test(center: Center, telegram_id: int, question_id: int, option: int) -> TestStep:
    session = _active_session(center, telegram_id)
    return _step_view(assessment.submit_answer(session, question_id=question_id, option=option))


@sync_to_async
def save_writing(center: Center, telegram_id: int, text: str) -> None:
    assessment.save_writing(_active_session(center, telegram_id), text)


@_llm_call
def assess_writing(center: Center, telegram_id: int) -> TestStep:
    """Оценка письма ИИ. Если ИИ недоступен — уровень по тесту, письмо проверит методист."""
    session = _active_session(center, telegram_id)
    try:
        session = writing.assess(session)
    except LLMError:
        session = assessment.finish_without_writing_assessment(session)
    return _done_view(session)
