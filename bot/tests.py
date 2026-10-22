from datetime import date, time
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.booking.models import Booking
from apps.booking.services import GroupFull
from apps.catalog.models import Level
from apps.leads.models import Lead
from bot import db
from bot.handlers import normalize_name, normalize_phone
from bot.texts import TEXTS, error_text, format_price, format_schedule, group_card

TG = SimpleNamespace(id=555, first_name="Ali", username="ali_tg", language_code="uz")
EVENING = {"weekdays": {1}, "period": "evening"}


def run(coro_fn, *args, **kwargs):
    return async_to_sync(coro_fn)(*args, **kwargs)


class TestTexts:
    def test_languages_have_same_keys(self):
        assert TEXTS["ru"].keys() == TEXTS["uz"].keys()

    def test_schedule_same_time(self):
        slots = ((1, time(18, 30), time(20, 0)), (3, time(18, 30), time(20, 0)))
        assert format_schedule("ru", slots) == "Вт, Чт 18:30–20:00"
        assert format_schedule("uz", slots) == "Se, Pa 18:30–20:00"

    def test_schedule_different_times(self):
        slots = ((1, time(18, 30), time(20, 0)), (5, time(10, 0), time(12, 0)))
        assert format_schedule("ru", slots) == "Вт 18:30–20:00; Сб 10:00–12:00"

    def test_price(self):
        assert format_price(600000) == "600 000"

    def test_group_card_escapes_html(self):
        option = db.GroupOption(
            id=1, name="<b>X</b>", course="GE", branch="Ч", start_date=date(2026, 11, 3),
            slots=((1, time(18, 0), time(19, 0)),), free_seats=2, price=600000,
        )
        assert "&lt;b&gt;X&lt;/b&gt;" in group_card("ru", option)

    def test_error_text_by_exception_class(self):
        assert error_text("ru", GroupFull()) == TEXTS["ru"]["err_GroupFull"]
        assert error_text("ru", ValueError()) == TEXTS["ru"]["err_unknown"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("+998 90 123-45-67", "+998901234567"), ("998901234567", "+998901234567"), ("abc", None), ("123", None)],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("азиз", "Азиз"),
        ("  Anna-Maria ", "Anna-Maria"),
        ("O'g'iloy", "O'g'iloy"),
        ("Ali123", None),
        ("A", None),
        ("/start", None),
        ("x" * 51, None),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.django_db(transaction=True)
class TestDb:
    def test_full_flow(self, center, make_group):
        group = make_group(capacity=2)
        run(db.ensure_user, center, TG)
        assert not run(db.profile, center, TG.id).consented

        run(db.accept_consent, center, TG.id)
        run(db.update_lead, center, TG.id, age=20, declared_level=Level.B1)
        assert run(db.profile, center, TG.id).consented

        options = run(db.search_groups, center, level=Level.B1, age=20, **EVENING)
        assert [o.id for o in options] == [group.id]
        assert options[0].free_seats == 2 and options[0].price == 600000
        trial_at = options[0].trial_at
        assert timezone.localtime(trial_at).weekday() == 1 and f"{timezone.localtime(trial_at):%H:%M}" == "18:30"

        run(db.update_lead, center, TG.id, name="Азиз")
        run(db.save_contact, center, TG.id, "+998901234567")
        lead = Lead.objects.select_related("user").get(user__telegram_id=TG.id)
        assert lead.name == "Азиз" and lead.phone == "+998901234567"
        assert lead.user.phone == "+998901234567" and lead.user.telegram_username == "ali_tg"

        held = run(db.hold, center, TG.id, group.id, trial_at)
        assert held.status == Booking.Status.HELD and held.trial_at == trial_at

        confirmed = run(db.confirm, center, TG.id, held.id)
        assert confirmed.status == Booking.Status.CONFIRMED
        assert Lead.objects.get(user__telegram_id=TG.id).status == Lead.Status.BOOKED
        assert [b.id for b in run(db.profile, center, TG.id).bookings] == [held.id]

    def test_cannot_touch_someone_elses_booking(self, center, make_group, make_lead):
        from apps.booking import services

        other = services.create_hold(lead=make_lead(), group_id=make_group().id)
        run(db.ensure_user, center, TG)
        with pytest.raises(db.BookingNotFound):
            run(db.confirm, center, TG.id, other.id)

    def test_level_test_with_writing_fallback(self, center, question_bank):
        from apps.assessment.models import Question

        run(db.ensure_user, center, TG)
        step = run(db.start_test, center, TG.id)
        while step.kind == "question":
            question = Question.objects.get(pk=step.question_id)
            step = run(db.answer_test, center, TG.id, question.id, question.correct_option)
        assert step.kind == "writing" and step.min_words == 150

        run(db.save_writing, center, TG.id, "word " * 200)
        # ИИ в тестах не настроен: уровень берётся по тесту, письмо уходит методисту.
        done = run(db.assess_writing, center, TG.id)
        assert done.kind == "done" and done.level == Level.C1 and done.needs_review
        assert run(db.profile, center, TG.id).level == Level.C1

    def test_agent_reply(self, center, monkeypatch):
        from apps.assistant import agent
        from apps.assistant.testing import FakeLLM, call, text

        run(db.ensure_user, center, TG)
        run(db.update_lead, center, TG.id, declared_level=Level.B1)
        llm = FakeLLM(call("start_group_selection"), text("Подберём группу!"))
        monkeypatch.setattr(agent, "get_client", lambda: llm)
        answer = run(db.agent_reply, center, TG.id, "Хочу записаться", "ru")
        assert answer.text == "Подберём группу!" and answer.actions == ("select_group",)

    def test_username_updated_on_next_start(self, center):
        from apps.core.models import User

        run(db.ensure_user, center, TG)
        run(db.ensure_user, center, SimpleNamespace(id=TG.id, first_name="Ali", username="new_nick", language_code="uz"))
        assert User.objects.get(telegram_id=TG.id).telegram_username == "new_nick"

    def test_language_saved(self, center):
        run(db.ensure_user, center, TG)
        assert run(db.get_language, TG.id) == "uz"
        run(db.set_language, TG.id, "ru")
        assert run(db.get_language, TG.id) == "ru"
