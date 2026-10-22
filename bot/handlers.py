"""Сценарий бота.

Новый ученик: язык → согласие → имя → возраст → (родитель) → диалог с ИИ-консультантом →
тест уровня (кнопки + письмо для B1+) → дни и время суток пробного урока → группы (считает бэкенд) →
контакт → запись.

Вернувшийся ученик (анкета уже в базе): сразу диалог с ИИ, его записи и кнопка отмены.

Язык (аргумент lang) и мгновенный ответ на нажатие кнопки добавляют middlewares.py.
Кнопки никогда не ждут ИИ, а запоздавший ответ ИИ не перехватывает управление.
"""

import logging
import re
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from django.conf import settings

from apps.assessment.services import AssessmentError, NoQuestions, WritingTooShort
from apps.assistant.llm import LLMError
from apps.assistant.tools import ACTION_CONFIRM_CANCEL, ACTION_SELECT_GROUP, ACTION_START_TEST
from apps.booking.services import BookingError, GroupFull, GroupNotFound, InvalidTrialLesson
from apps.catalog.models import Level
from apps.core.models import Center
from apps.leads.models import ADULT_AGE, Lead

from . import db
from . import keyboards as kb
from .middlewares import MANUAL_ANSWER, AnswerCallbackFirst, LanguageMiddleware
from .states import Flow
from .texts import LANGUAGES, booking_card, error_text, format_trial, group_card, t

router = Router(name="main")
router.callback_query.middleware(AnswerCallbackFirst())
router.callback_query.middleware(LanguageMiddleware())
router.message.middleware(LanguageMiddleware())
logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
# Буквы любого алфавита; внутри имени допустимы пробел, дефис и апостроф (O'g'iloy, Анна-Мария).
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '’ʻ`\-][^\W\d_]+)*$")

# Ученики, чей запрос к ИИ сейчас выполняется: новые сообщения не ставим в очередь к модели.
_ai_busy: set[int] = set()


class AIBusy(Exception):
    pass


def normalize_name(raw: str) -> str | None:
    name = " ".join((raw or "").split())
    if not 2 <= len(name) <= 50 or not NAME_RE.match(name):
        return None
    return name[0].upper() + name[1:]


def normalize_phone(raw: str) -> str | None:
    phone = re.sub(r"[\s\-()]", "", raw or "")
    if not PHONE_RE.match(phone):
        return None
    return phone if phone.startswith("+") else f"+{phone}"


async def in_state(state: FSMContext, flow_state) -> bool:
    return await state.get_state() == flow_state.state


async def ask_ai(message: Message, lang: str, func, *args):
    """Один запрос к ИИ на ученика, с «печатает…» на всё время ожидания.
    Если предыдущий запрос ещё идёт — отвечает «секунду» и бросает AIBusy.
    Принимает функцию, а не корутину: запрос создаётся, только если он действительно нужен."""
    user_id = message.from_user.id
    if user_id in _ai_busy:
        await message.answer(t(lang, "ai_busy"))
        raise AIBusy
    _ai_busy.add(user_id)
    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            return await func(*args)
    finally:
        _ai_busy.discard(user_id)


async def show(message: Message, text: str, markup=None, *, edit: bool = False):
    """Новый экран: снимаем кнопки с сообщения, на котором нажали, и отправляем следующее."""
    if edit:
        await message.edit_reply_markup(reply_markup=None)
    await message.answer(text, reply_markup=markup)


# --- Начало, язык, вернувшийся ученик -----------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, center: Center):
    await db.ensure_user(center, message.from_user)
    profile = await db.profile(center, message.from_user.id)
    await state.clear()
    if profile.onboarded:
        await greet_returning(message, state, profile)
        return
    await state.set_state(Flow.language)
    await message.answer(t("ru", "choose_language"), reply_markup=kb.languages())


# Команды регистрируются до обработчиков шагов, чтобы работать в любом состоянии.
@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext, center: Center):
    await db.ensure_user(center, message.from_user)
    await state.set_state(Flow.language)
    await message.answer(t("ru", "choose_language"), reply_markup=kb.languages())


@router.message(Command("my"))
async def cmd_my(message: Message, center: Center, lang: str):
    await show_my_bookings(message, center, message.from_user.id, lang)


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str):
    await message.answer(t(lang, "help"))


async def greet_returning(message: Message, state: FSMContext, profile: db.Profile):
    lang = profile.language if profile.language in LANGUAGES else "ru"
    await state.set_state(Flow.chat)
    await state.update_data(lang=lang, name=profile.name, level=profile.level)
    name = escape(profile.name)
    if profile.bookings:
        cards = "\n\n".join(booking_card(lang, b) for b in profile.bookings)
        await message.answer(
            f"{t(lang, 'welcome_back_bookings', name=name)}\n\n{cards}",
            reply_markup=kb.my_bookings(lang, profile.bookings),
        )
    else:
        await message.answer(
            t(lang, "welcome_back", name=name), reply_markup=kb.chat_actions(lang, test=not profile.tested)
        )


@router.callback_query(Flow.language, F.data.startswith("lang:"))
async def on_language(cb: CallbackQuery, state: FSMContext, center: Center):
    lang = cb.data.split(":", 1)[1]
    if lang not in LANGUAGES:
        lang = center.default_language
    await state.update_data(lang=lang)
    await db.set_language(cb.from_user.id, lang)
    await cb.message.edit_reply_markup(reply_markup=None)

    profile = await db.profile(center, cb.from_user.id)
    if profile.onboarded:
        await greet_returning(cb.message, state, profile)
        return
    await cb.message.answer(t(lang, "welcome", center=escape(center.name)), reply_markup=kb.mini_app(lang))
    if profile.consented:
        await ask_name(cb.message, state, lang)
    else:
        await state.set_state(Flow.consent)
        await cb.message.answer(t(lang, "consent_ask"), reply_markup=kb.consent(lang))


# --- Согласие, имя, возраст -----------------------------------------------------


@router.callback_query(Flow.consent, F.data.startswith("consent:"))
async def on_consent(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    await cb.message.edit_reply_markup(reply_markup=None)
    if cb.data == "consent:yes":
        await db.accept_consent(center, cb.from_user.id)
        await ask_name(cb.message, state, lang)
    else:
        await state.clear()
        await cb.message.answer(t(lang, "consent_declined"))


async def ask_name(message: Message, state: FSMContext, lang: str):
    await state.set_state(Flow.name)
    await message.answer(t(lang, "ask_name"))


@router.message(Flow.name, F.text)
async def on_name(message: Message, state: FSMContext, center: Center, lang: str):
    name = normalize_name(message.text)
    if name is None:
        await message.answer(t(lang, "bad_name"))
        return
    await db.update_lead(center, message.from_user.id, name=name)
    await state.update_data(name=name)
    await state.set_state(Flow.age)
    await message.answer(t(lang, "ask_age"))


@router.message(Flow.age, F.text)
async def on_age(message: Message, state: FSMContext, center: Center, lang: str):
    text = message.text.strip()
    if not text.isdigit() or not 3 <= int(text) <= 100:
        await message.answer(t(lang, "bad_age"))
        return
    age = int(text)
    await state.update_data(age=age)
    await db.update_lead(center, message.from_user.id, age=age)

    if age < ADULT_AGE:
        await state.set_state(Flow.parent_phone)
        await message.answer(t(lang, "ask_parent_phone"))
    else:
        await enter_chat(message, state, lang)


@router.message(Flow.parent_phone, F.text)
async def on_parent_phone(message: Message, state: FSMContext, center: Center, lang: str):
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer(t(lang, "bad_phone"))
        return
    await db.update_lead(center, message.from_user.id, parent_phone=phone)
    await state.set_state(Flow.parent_consent)
    await message.answer(t(lang, "parent_consent_ask"), reply_markup=kb.parent_consent(lang))


@router.callback_query(Flow.parent_consent, F.data == "pconsent:yes")
async def on_parent_consent(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    await db.accept_consent(center, cb.from_user.id, parent=True)
    await cb.message.edit_reply_markup(reply_markup=None)
    await enter_chat(cb.message, state, lang)


# --- Диалог с ИИ-консультантом ------------------------------------------------


async def enter_chat(message: Message, state: FSMContext, lang: str):
    name = (await state.get_data()).get("name", "")
    await state.set_state(Flow.chat)
    await message.answer(t(lang, "chat_intro", name=escape(name)), reply_markup=kb.chat_actions(lang))


@router.message(Flow.chat, F.text)
async def on_chat_message(message: Message, state: FSMContext, center: Center, lang: str):
    await chat_with_ai(message, state, center, lang)


async def chat_with_ai(message: Message, state: FSMContext, center: Center, lang: str):
    user_id = message.from_user.id
    try:
        answer = await ask_ai(message, lang, db.agent_reply, center, user_id, message.text, lang)
    except AIBusy:
        return
    except LLMError:
        logger.exception("ИИ-консультант недоступен")
        if await in_state(state, Flow.chat):
            await message.answer(t(lang, "ai_unavailable"), reply_markup=kb.chat_actions(lang))
        return

    # Пока ИИ думал, ученик мог нажать кнопку (тест, подбор группы) — тогда ответ уже не к месту.
    if not await in_state(state, Flow.chat):
        logger.info("Ответ ИИ для %s пропущен: ученик уже перешёл к другому шагу", user_id)
        return

    profile = await db.profile(center, user_id)
    if answer.text:
        # Кнопки под каждым ответом: если модель не вызовет функцию, ученик не застрянет.
        await message.answer(
            escape(answer.text),
            reply_markup=kb.chat_actions(lang, test=not profile.tested, my=bool(profile.bookings)),
        )
    for action in answer.actions:
        if action == ACTION_START_TEST:
            await begin_test(message, state, center, lang)
        elif action == ACTION_SELECT_GROUP:
            await begin_group_selection(message, state, center, lang)
        elif action.startswith(f"{ACTION_CONFIRM_CANCEL}:"):
            await ask_cancel(message, center, user_id, lang, int(action.split(":", 1)[1]))
        else:
            continue
        break


@router.callback_query(F.data == "act:test")
async def on_test_button(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    await begin_test(cb.message, state, center, lang, telegram_id=cb.from_user.id)


@router.callback_query(F.data == "act:groups")
async def on_groups_button(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    await begin_group_selection(cb.message, state, center, lang, telegram_id=cb.from_user.id)


@router.callback_query(F.data == "act:my")
async def on_my_button(cb: CallbackQuery, center: Center, lang: str):
    await show_my_bookings(cb.message, center, cb.from_user.id, lang)


async def begin_group_selection(message: Message, state: FSMContext, center: Center, lang: str, *, telegram_id=None):
    profile = await db.profile(center, telegram_id or message.from_user.id)
    if profile.level is None:
        await ask_level(message, state, lang)
        return
    await state.update_data(level=profile.level)
    await ask_days(message, state, lang)


# --- Тест уровня ----------------------------------------------------------------


async def begin_test(message: Message, state: FSMContext, center: Center, lang: str, *, telegram_id=None):
    try:
        step = await db.start_test(center, telegram_id or message.from_user.id)
    except NoQuestions:
        logger.error("Банк вопросов теста пуст")
        await message.answer(t(lang, "test_unavailable"))
        await ask_level(message, state, lang)
        return
    if step.kind == "question":
        await message.answer(t(lang, "test_intro"))
    await show_test_step(message, state, lang, step)


async def show_test_step(message: Message, state: FSMContext, lang: str, step: db.TestStep):
    if step.kind == "question":
        await state.set_state(Flow.test)
        await message.answer(
            t(lang, "test_question", number=step.number, text=escape(step.text)),
            reply_markup=kb.test_options(step.question_id, step.options),
        )
    elif step.kind == "writing":
        await state.set_state(Flow.writing)
        await message.answer(t(lang, "writing_task", min_words=step.min_words, prompt=escape(step.text)))
    else:
        await show_test_result(message, state, lang, step)


async def show_test_result(message: Message, state: FSMContext, lang: str, step: db.TestStep, *, switch_state=True):
    await state.update_data(level=step.level)
    if switch_state:
        await state.set_state(Flow.chat)
    lines = [t(lang, "test_result", level=Level(step.level).label)]
    if step.needs_review:
        lines.append(t(lang, "test_review"))
    lines.append(t(lang, "test_next"))
    await message.answer("\n".join(lines), reply_markup=kb.chat_actions(lang, test=False))


@router.callback_query(Flow.test, F.data.startswith("ans:"))
async def on_test_answer(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    _, question_id, option = cb.data.split(":")
    try:
        step = await db.answer_test(center, cb.from_user.id, int(question_id), int(option))
    except AssessmentError:
        await show(cb.message, t(lang, "test_question_closed"), edit=True)
        return

    # Оставляем в чате вопрос с выбранным ответом, без кнопок и без подсказки, верен ли он.
    chosen = next(
        (b.text for row in cb.message.reply_markup.inline_keyboard for b in row if b.callback_data == cb.data),
        option,
    )
    await cb.message.edit_text(
        t(lang, "test_answered", text=cb.message.html_text, answer=escape(chosen)), reply_markup=None
    )
    await show_test_step(cb.message, state, lang, step)


@router.message(Flow.writing, F.text)
async def on_writing(message: Message, state: FSMContext, center: Center, lang: str):
    user_id = message.from_user.id
    if user_id in _ai_busy:  # текст уже проверяется — второй раз не отправляем
        await message.answer(t(lang, "ai_busy"))
        return
    try:
        await db.save_writing(center, user_id, message.text)
    except WritingTooShort as exc:
        await message.answer(t(lang, "writing_too_short", words=exc.words, min_words=exc.min_words))
        return
    except AssessmentError:
        await state.set_state(Flow.chat)
        await message.answer(t(lang, "err_unknown"))
        return

    await message.answer(t(lang, "writing_checking"))
    try:
        step = await ask_ai(message, lang, db.assess_writing, center, user_id)
    except AIBusy:
        return
    # Результат показываем всегда, но шаг меняем, только если ученик никуда не ушёл.
    await show_test_result(message, state, lang, step, switch_state=await in_state(state, Flow.writing))


# --- Уровень, дни, время суток ------------------------------------------------


async def ask_level(message: Message, state: FSMContext, lang: str):
    await state.set_state(Flow.level)
    await message.answer(t(lang, "ask_level"), reply_markup=kb.levels(lang))


@router.callback_query(Flow.level, F.data.startswith("lvl:"))
async def on_level(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    level = cb.data.split(":", 1)[1]
    if level not in Level.values:
        return
    await state.update_data(level=level)
    await db.update_lead(center, cb.from_user.id, declared_level=level)
    await cb.message.edit_reply_markup(reply_markup=None)
    await ask_days(cb.message, state, lang)


async def ask_days(message: Message, state: FSMContext, lang: str):
    await state.update_data(days=[])
    await state.set_state(Flow.days)
    await message.answer(t(lang, "ask_days"), reply_markup=kb.days(lang, set()))


@router.callback_query(Flow.days, F.data.startswith("day:"), flags={MANUAL_ANSWER: True})
async def on_day(cb: CallbackQuery, state: FSMContext, lang: str):
    value = cb.data.split(":", 1)[1]
    selected = set((await state.get_data()).get("days", []))
    if value == "done" and not selected:
        await cb.answer(t(lang, "days_empty"), show_alert=True)
        return
    await cb.answer()

    if value == "done":
        await state.set_state(Flow.time)
        await show(cb.message, t(lang, "ask_time"), kb.periods(lang), edit=True)
        return
    selected ^= {int(value)}
    await state.update_data(days=sorted(selected))
    await cb.message.edit_reply_markup(reply_markup=kb.days(lang, selected))


@router.callback_query(Flow.time, F.data.startswith("time:"))
async def on_period(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    period = cb.data.split(":", 1)[1]
    if period not in kb.PERIODS:
        return
    await cb.message.edit_reply_markup(reply_markup=None)

    data = await state.get_data()
    options = await db.search_groups(
        center, level=data["level"], weekdays=set(data["days"]), period=period, age=data.get("age")
    )
    await state.set_state(Flow.choose_group)
    if not options:
        await db.update_lead(center, cb.from_user.id, status=Lead.Status.NEEDS_MANAGER)
        await cb.message.answer(t(lang, "not_found"), reply_markup=kb.change_search(lang))
        return

    # Запоминаем пробный урок каждой показанной группы: его и забронируем.
    await state.update_data(trials={str(o.id): o.trial_at.isoformat() for o in options})
    cards = "\n\n".join(group_card(lang, option) for option in options)
    await cb.message.answer(f"{t(lang, 'found')}\n\n{cards}", reply_markup=kb.group_choices(lang, options))


@router.callback_query(Flow.choose_group, F.data == "search:again")
async def on_search_again(cb: CallbackQuery, state: FSMContext, lang: str):
    await cb.message.edit_reply_markup(reply_markup=None)
    await ask_days(cb.message, state, lang)


# --- Выбор группы, контакт, бронь -------------------------------------------


@router.callback_query(Flow.choose_group, F.data.startswith("grp:"))
async def on_group(cb: CallbackQuery, state: FSMContext, lang: str):
    group_id = cb.data.split(":", 1)[1]
    trial = (await state.get_data()).get("trials", {}).get(group_id)
    await state.update_data(group_id=int(group_id), trial_at=trial)
    await state.set_state(Flow.contact)
    await show(cb.message, t(lang, "ask_contact"), kb.share_contact(lang), edit=True)


@router.message(Flow.contact, F.contact)
async def on_contact(message: Message, state: FSMContext, center: Center, lang: str):
    contact = message.contact
    phone = normalize_phone(contact.phone_number)
    # Принимаем только собственный контакт, а не пересланный чужой.
    if contact.user_id != message.from_user.id or phone is None:
        await message.answer(t(lang, "not_own_contact"), reply_markup=kb.share_contact(lang))
        return

    await db.save_contact(center, message.from_user.id, phone)
    await message.answer(t(lang, "contact_saved"), reply_markup=ReplyKeyboardRemove())

    data = await state.get_data()
    trial_at = datetime.fromisoformat(data["trial_at"]) if data.get("trial_at") else None
    try:
        booking = await db.hold(center, message.from_user.id, data["group_id"], trial_at)
    except BookingError as exc:
        await state.set_state(Flow.choose_group)
        retry = isinstance(exc, (GroupFull, GroupNotFound, InvalidTrialLesson))
        await message.answer(error_text(lang, exc), reply_markup=kb.change_search(lang) if retry else None)
        return

    # Дальше вопросы ученика снова идут ИИ.
    await state.set_state(Flow.chat)
    await message.answer(
        t(lang, "held", name=escape(booking.group.name), minutes=settings.BOOKING_HOLD_MINUTES,
          trial=format_trial(lang, booking.trial_at, booking.group.start_date)),
        reply_markup=kb.booking_actions(lang, booking.id),
    )


@router.message(Flow.contact)
async def on_contact_text(message: Message, lang: str):
    await message.answer(t(lang, "not_own_contact"), reply_markup=kb.share_contact(lang))


# --- Мои записи и отмена ----------------------------------------------------------


async def show_my_bookings(message: Message, center: Center, telegram_id: int, lang: str):
    profile = await db.profile(center, telegram_id)
    if not profile.bookings:
        await message.answer(t(lang, "my_empty"), reply_markup=kb.chat_actions(lang, test=not profile.tested))
        return
    cards = "\n\n".join(booking_card(lang, b) for b in profile.bookings)
    await message.answer(f"{t(lang, 'my_title')}\n\n{cards}", reply_markup=kb.my_bookings(lang, profile.bookings))


async def ask_cancel(message: Message, center: Center, telegram_id: int, lang: str, booking_id: int):
    """Отмена всегда через кнопку подтверждения: ни ИИ, ни случайное нажатие не отменят запись сами."""
    try:
        booking = await db.active_booking(center, telegram_id, booking_id)
    except BookingError as exc:
        await message.answer(error_text(lang, exc))
        return
    await message.answer(
        t(lang, "cancel_confirm", name=escape(booking.group.name),
          start=format_trial(lang, booking.trial_at, booking.group.start_date)),
        reply_markup=kb.cancel_confirm(lang, booking.id),
    )


@router.callback_query(F.data.startswith("bk:"))
async def on_booking_action(cb: CallbackQuery, state: FSMContext, center: Center, lang: str):
    _, action, raw_id = cb.data.split(":")
    booking_id = int(raw_id)

    if action == "ask":
        await ask_cancel(cb.message, center, cb.from_user.id, lang, booking_id)
        return
    if action == "keep":
        await cb.message.edit_text(t(lang, "kept"), reply_markup=None)
        return

    try:
        if action == "confirm":
            booking = await db.confirm(center, cb.from_user.id, booking_id)
            text = t(lang, "confirmed", name=escape(booking.group.name),
                     trial=format_trial(lang, booking.trial_at, booking.group.start_date))
        else:
            await db.cancel(center, cb.from_user.id, booking_id)
            text = t(lang, "cancelled")
    except BookingError as exc:
        await show(cb.message, error_text(lang, exc), edit=True)
        return

    await state.set_state(Flow.chat)
    await cb.message.edit_text(text, reply_markup=kb.chat_actions(lang, test=False, my=True))


# --- Прочее -------------------------------------------------------------------


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext, center: Center, lang: str):
    """Текст вне сценария. Знакомому ученику отвечает ИИ — в том числе после перезапуска бота."""
    profile = await db.profile(center, message.from_user.id)
    if not profile.onboarded:
        await message.answer(t(lang, "unknown"))
        return
    await state.set_state(Flow.chat)
    await state.update_data(lang=lang, name=profile.name, level=profile.level)
    await chat_with_ai(message, state, center, lang)


@router.message()
async def fallback(message: Message, lang: str):
    await message.answer(t(lang, "unknown"))
