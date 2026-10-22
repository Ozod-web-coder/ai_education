import io
from datetime import date, time

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Course, Group, GroupSlot, Level
from apps.core.models import Branch, Center, User
from apps.leads.models import Lead

BOT_TOKEN = "123456:TEST-TOKEN"
TUE_THU_EVENING = ((1, time(18, 30), time(20, 0)), (3, time(18, 30), time(20, 0)))


@pytest.fixture(autouse=True)
def no_real_llm(settings):
    """Тесты никогда не ходят в настоящую модель, даже если она задана в .env."""
    from apps.assistant.llm import get_client, get_writing_client

    settings.LLM_BASE_URL = ""
    settings.LLM_MODEL = ""
    settings.LLM_WRITING_MODEL = ""
    get_client.cache_clear()
    get_writing_client.cache_clear()
    yield
    get_client.cache_clear()
    get_writing_client.cache_clear()


@pytest.fixture
def question_bank(db):
    from django.core.management import call_command

    call_command("seed_assessment", stdout=io.StringIO())


@pytest.fixture
def center(db):
    return Center.objects.create(name="Demo", slug="demo", bot_token=BOT_TOKEN)


@pytest.fixture
def branch(center):
    return Branch.objects.create(center=center, name="Чиланзар")


@pytest.fixture
def course(center):
    return Course.objects.create(center=center, name="General English", price_per_month=600_000)


@pytest.fixture
def make_group(course, branch):
    def _make(level=Level.B1, capacity=10, slots=TUE_THU_EVENING, **kwargs):
        group = Group.objects.create(
            course=course,
            branch=branch,
            name=kwargs.pop("name", f"{level} группа"),
            level=level,
            capacity=capacity,
            start_date=kwargs.pop("start_date", date(2026, 11, 3)),
            **kwargs,
        )
        for weekday, start, end in slots:
            GroupSlot.objects.create(group=group, weekday=weekday, start_time=start, end_time=end)
        return group

    return _make


@pytest.fixture
def make_lead(center):
    counter = iter(range(1, 10_000))

    def _make(age=20, phone="+998901234567", **kwargs):
        n = next(counter)
        user = User.objects.create_user(username=f"tg_{n}", telegram_id=n)
        return Lead.objects.create(
            center=center,
            user=user,
            name=f"Ученик {n}",
            phone=phone,
            age=age,
            personal_data_consent_at=timezone.now(),
            **kwargs,
        )

    return _make


@pytest.fixture
def lead(make_lead):
    return make_lead()


@pytest.fixture
def api_for():
    def _client(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _client
