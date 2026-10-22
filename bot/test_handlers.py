"""Сценарии бота через настоящий Dispatcher. Вместо Telegram — сеанс, который записывает запросы."""

import asyncio
import itertools
import time
from datetime import datetime
from datetime import time as dtime

import pytest
from django.utils import timezone
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Chat, Message, Update

from apps.assistant import agent
from apps.assistant.llm import ChatResult
from apps.assistant.testing import FakeLLM, call, text
from apps.booking import services
from apps.booking.models import Booking
from apps.catalog.models import Level
from apps.leads.models import Lead
from bot.handlers import router
from bot.states import Flow

pytestmark = pytest.mark.django_db(transaction=True)
BOT_ID = 4242
_ids = itertools.count(1)


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if method.__returning__ is bool:
            return True
        chat_id = getattr(method, "chat_id", None) or 1
        return Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=chat_id, type="private"))

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    def texts(self):
        return [r.text for r in self.requests if isinstance(r, (SendMessage, EditMessageText))]


_dp = None


def dispatcher(center):
    global _dp
    if _dp is None:
        _dp = Dispatcher(storage=MemoryStorage())
        _dp.include_router(router)
    _dp.storage.storage.clear()
    _dp["center"] = center
    return _dp


class Harness:
    def __init__(self, center, user_id):
        self.dp = dispatcher(center)
        self.session = RecordingSession()
        self.bot = Bot(f"{BOT_ID}:TEST", session=self.session)
        self.user_id = user_id

    def _user(self):
        return {"id": self.user_id, "is_bot": False, "first_name": "Ali", "language_code": "ru"}

    async def send(self, message_text):
        payload = {
            "message_id": next(_ids), "date": int(time.time()), "text": message_text,
            "chat": {"id": self.user_id, "type": "private"}, "from": self._user(),
        }
        if message_text.startswith("/"):
            payload["entities"] = [{"type": "bot_command", "offset": 0, "length": len(message_text.split()[0])}]
        await self._feed({"message": payload})

    async def send_contact(self, phone):
        await self._feed({"message": {
            "message_id": next(_ids), "date": int(time.time()),
            "chat": {"id": self.user_id, "type": "private"}, "from": self._user(),
            "contact": {"phone_number": phone, "first_name": "Ali", "user_id": self.user_id},
        }})

    async def press(self, data):
        await self._feed({"callback_query": {
            "id": str(next(_ids)), "from": self._user(), "chat_instance": "ci", "data": data,
            "message": {
                "message_id": next(_ids), "date": int(time.time()), "text": "…",
                "chat": {"id": self.user_id, "type": "private"},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "bot"},
            },
        }})

    async def _feed(self, body):
        update = Update.model_validate({"update_id": next(_ids), **body}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    async def state(self):
        key = StorageKey(bot_id=BOT_ID, chat_id=self.user_id, user_id=self.user_id)
        return await self.dp.storage.get_state(key)


@pytest.fixture
def student(make_lead):
    lead = make_lead(declared_level=Level.B1)
    return lead


@pytest.fixture
def confirmed_booking(student, make_group):
    booking = services.create_hold(lead=student, group_id=make_group(name="B1 вечер Вт/Чт").id)
    return services.confirm_booking(booking)


class SlowLLM:
    def __init__(self, seconds, reply="Ответ ИИ"):
        self.seconds, self.reply, self.calls = seconds, reply, 0

    def chat(self, messages, *, tools=None, tool_choice=None):
        self.calls += 1
        time.sleep(self.seconds)
        return ChatResult(content=self.reply)


def run(coro):
    return asyncio.run(coro)


def test_new_user_is_asked_language(center):
    h = Harness(center, user_id=777001)
    run(h.send("/start"))
    assert "Выберите язык" in h.session.texts()[0]


def test_returning_user_skips_onboarding(student, confirmed_booking):
    h = Harness(student.center, student.user.telegram_id)
    run(h.send("/start"))
    first = h.session.texts()[0]
    assert "С возвращением" in first and "B1 вечер Вт/Чт" in first and "подтверждена" in first
    assert not any("Выберите язык" in t for t in h.session.texts())
    assert run(h.state()) == Flow.chat.state


@pytest.mark.parametrize("data", ["act:groups", "act:my", "act:test"])
def test_buttons_answered_before_anything_else(student, question_bank, data):
    h = Harness(student.center, student.user.telegram_id)
    run(h.press(data))
    assert isinstance(h.session.requests[0], AnswerCallbackQuery)
    assert len(h.session.requests) > 1  # и действие выполнено


def test_text_after_restart_goes_to_ai(student, monkeypatch):
    monkeypatch.setattr(agent, "get_client", lambda: FakeLLM(text("Пробный урок бесплатный.")))
    h = Harness(student.center, student.user.telegram_id)  # пустое состояние, как после перезапуска
    run(h.send("Есть пробный урок?"))
    assert "Пробный урок бесплатный." in h.session.texts()
    assert run(h.state()) == Flow.chat.state


def test_unknown_user_text_is_not_sent_to_ai(center, monkeypatch):
    monkeypatch.setattr(agent, "get_client", lambda: pytest.fail("ИИ не должен вызываться"))
    h = Harness(center, user_id=777002)
    run(h.send("Привет"))
    assert "/start" in h.session.texts()[0]


def test_button_during_ai_thinking_is_instant_and_wins(student, monkeypatch):
    monkeypatch.setattr(agent, "get_client", lambda: SlowLLM(2.0))
    h = Harness(student.center, student.user.telegram_id)

    async def scenario():
        ai = asyncio.create_task(h.send("Расскажите о курсах"))
        await asyncio.sleep(0.3)
        started = time.monotonic()
        await h.press("act:groups")
        button_time = time.monotonic() - started
        await ai
        return button_time

    button_time = run(scenario())
    assert button_time < 1.0, f"кнопка ждала ИИ {button_time:.1f} с"
    texts = h.session.texts()
    assert any("В какой день вам удобно прийти на пробный урок" in t for t in texts)
    assert "Ответ ИИ" not in texts  # запоздавший ответ не вклинился в выбор дней
    assert run(h.state()) == Flow.days.state


def test_second_message_while_ai_busy(student, monkeypatch):
    llm = SlowLLM(1.5)
    monkeypatch.setattr(agent, "get_client", lambda: llm)
    h = Harness(student.center, student.user.telegram_id)

    async def scenario():
        first = asyncio.create_task(h.send("Вопрос 1"))
        await asyncio.sleep(0.3)
        await h.send("Вопрос 2")
        await first

    run(scenario())
    assert llm.calls == 1
    assert any("Секунду" in t for t in h.session.texts())


def test_trial_lesson_booking_by_one_day_and_period(student, make_group):
    """Ученик отмечает один день и «вечером» — группа Вт/Чт находится, бронь на ближайший вторник."""
    group = make_group(name="B1 вечер Вт/Чт")
    make_group(name="B1 утро", slots=((1, dtime(9, 0), dtime(10, 30)),))
    h = Harness(student.center, student.user.telegram_id)

    async def scenario():
        await h.press("act:groups")
        await h.press("day:1")  # только вторник
        await h.press("day:done")
        await h.press("time:evening")
        await h.press(f"grp:{group.id}")
        await h.send_contact("+998901234567")

    run(scenario())
    texts = h.session.texts()
    found = next(t for t in texts if t.startswith("Подходящие группы"))
    assert "B1 вечер Вт/Чт" in found and "B1 утро" not in found
    assert "Пробный урок: <b>Вт, " in found and "18:30" in found
    assert any("забронировано" in t and "Пробный урок" in t for t in texts)

    booking = Booking.objects.get(lead=student)
    trial = timezone.localtime(booking.trial_at)
    assert booking.group_id == group.id and trial.weekday() == 1 and f"{trial:%H:%M}" == "18:30"


def test_cancel_via_ai_needs_button(student, confirmed_booking, monkeypatch):
    llm = FakeLLM(call("request_booking_cancellation", booking_id=confirmed_booking.id), text("Подтвердите отмену."))
    monkeypatch.setattr(agent, "get_client", lambda: llm)
    h = Harness(student.center, student.user.telegram_id)

    run(h.send("Хочу отменить пробное занятие"))
    assert any("Отменить запись в группу «B1 вечер Вт/Чт»" in t for t in h.session.texts())
    confirmed_booking.refresh_from_db()
    assert confirmed_booking.status == Booking.Status.CONFIRMED  # ИИ сам не отменил

    run(h.press(f"bk:cancel:{confirmed_booking.id}"))
    confirmed_booking.refresh_from_db()
    student.refresh_from_db()
    assert confirmed_booking.status == Booking.Status.CANCELLED
    assert "отменил запись в «B1 вечер Вт/Чт»" in student.manager_note
    assert student.status != Lead.Status.BOOKED


def test_cancel_from_my_bookings_and_keep(student, confirmed_booking):
    h = Harness(student.center, student.user.telegram_id)
    run(h.press(f"bk:ask:{confirmed_booking.id}"))
    assert any("Отменить запись" in t for t in h.session.texts())
    run(h.press(f"bk:keep:{confirmed_booking.id}"))
    confirmed_booking.refresh_from_db()
    assert confirmed_booking.status == Booking.Status.CONFIRMED
    assert "Хорошо, запись сохранена." in h.session.texts()


def test_cannot_cancel_someone_elses_booking(student, confirmed_booking, make_lead):
    stranger = make_lead()
    h = Harness(student.center, stranger.user.telegram_id)
    run(h.press(f"bk:cancel:{confirmed_booking.id}"))
    confirmed_booking.refresh_from_db()
    assert confirmed_booking.status == Booking.Status.CONFIRMED
