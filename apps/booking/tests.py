from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking
from apps.catalog.models import DayPeriod, Level, period_of
from apps.leads.models import Lead

EVENING = {"weekdays": {1, 3}, "period": DayPeriod.EVENING}


def at(year, month, day, hour=12, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute))


@pytest.mark.parametrize(
    ("start", "period"),
    [(time(8, 0), "morning"), (time(11, 59), "morning"), (time(12, 0), "day"),
     (time(16, 59), "day"), (time(17, 0), "evening"), (time(20, 30), "evening")],
)
def test_period_by_start_time(start, period):
    assert period_of(start) == period


class TestFindMatchingGroups:
    def test_matches_level_day_and_period(self, center, make_group):
        fits = make_group()  # Вт/Чт 18:30
        make_group(level=Level.A1)  # другой уровень
        make_group(slots=((0, time(9, 0), time(10, 30)),))  # утро понедельника
        found = services.find_matching_groups(center, level=Level.B1, **EVENING)
        assert [g.id for g in found] == [fits.id]
        assert found[0].free_seats == 10

    @pytest.mark.parametrize("weekdays", [{1}, {3}, {1, 3}, {1, 5}])
    def test_one_matching_day_is_enough(self, center, make_group, weekdays):
        """Для пробного урока достаточно одного удобного дня, а не всего расписания группы."""
        group = make_group()
        found = services.find_matching_groups(center, level=Level.B1, weekdays=weekdays, period=DayPeriod.EVENING)
        assert [g.id for g in found] == [group.id]

    def test_wrong_day_or_period(self, center, make_group):
        make_group()
        assert services.find_matching_groups(center, level=Level.B1, weekdays={0, 2}, period="evening") == []
        assert services.find_matching_groups(center, level=Level.B1, weekdays={1}, period="morning") == []
        assert len(services.find_matching_groups(center, level=Level.B1, weekdays={1}, period="any")) == 1

    def test_trial_is_on_chosen_day(self, center, make_group):
        # Вт вечером и Сб утром. Ученик выбрал субботнее утро — пробный урок в субботу.
        make_group(slots=((1, time(18, 30), time(20, 0)), (5, time(10, 0), time(12, 0))),
                   start_date=date(2026, 11, 2))
        now = at(2026, 11, 2)  # понедельник
        [group] = services.find_matching_groups(center, level=Level.B1, weekdays={5}, period="morning", now=now)
        assert group.trial.date == date(2026, 11, 7) and group.trial.start_time == time(10, 0)

    def test_trial_for_running_group_and_started_lesson(self, center, make_group):
        make_group(start_date=date(2026, 10, 1))  # группа уже идёт
        # Вторник 19:00: вторничное занятие (18:30) уже началось — ближайшее в четверг.
        [group] = services.find_matching_groups(center, level=Level.B1, now=at(2026, 11, 3, 19), **EVENING)
        assert group.trial.date == date(2026, 11, 5)
        # Вторник утром — успевает на сегодняшнее.
        [group] = services.find_matching_groups(center, level=Level.B1, now=at(2026, 11, 3, 9), **EVENING)
        assert group.trial.date == date(2026, 11, 3)

    def test_trial_not_before_group_start(self, center, make_group):
        make_group(start_date=date(2026, 11, 12))  # старт в четверг 12.11
        [group] = services.find_matching_groups(center, level=Level.B1, now=at(2026, 11, 2), **EVENING)
        assert group.trial.date == date(2026, 11, 12)

    def test_sorted_by_nearest_trial(self, center, make_group):
        later = make_group(start_date=date(2026, 11, 17))
        sooner = make_group(start_date=date(2026, 11, 3))
        found = services.find_matching_groups(center, level=Level.B1, now=at(2026, 11, 2), **EVENING)
        assert [g.id for g in found] == [sooner.id, later.id]

    def test_full_group_excluded(self, center, make_group, make_lead):
        group = make_group(capacity=1)
        services.create_hold(lead=make_lead(), group_id=group.id)
        assert services.find_matching_groups(center, level=Level.B1, **EVENING) == []

    def test_expired_hold_frees_seat(self, center, make_group, make_lead):
        group = make_group(capacity=1)
        past = timezone.now() - timedelta(hours=1)
        services.create_hold(lead=make_lead(), group_id=group.id, now=past)
        assert len(services.find_matching_groups(center, level=Level.B1, **EVENING)) == 1

    def test_age_filter(self, center, make_group):
        make_group(min_age=16)
        assert services.find_matching_groups(center, level=Level.B1, age=14, **EVENING) == []
        assert len(services.find_matching_groups(center, level=Level.B1, age=16, **EVENING)) == 1

    def test_limit_three(self, center, make_group):
        for _ in range(5):
            make_group()
        assert len(services.find_matching_groups(center, level=Level.B1, **EVENING)) == 3


class TestTrialBooking:
    def test_hold_with_trial(self, center, make_group, lead):
        make_group(start_date=date(2026, 11, 3))
        now = at(2026, 11, 2)
        [group] = services.find_matching_groups(center, level=Level.B1, now=now, **EVENING)
        booking = services.create_hold(lead=lead, group_id=group.id, trial_at=group.trial.starts_at, now=now)
        assert timezone.localtime(booking.trial_at) == at(2026, 11, 3, 18, 30)

    @pytest.mark.parametrize(
        "trial", [at(2026, 11, 3, 10, 0), at(2026, 11, 2, 18, 30), at(2026, 10, 27, 18, 30)],
        ids=["нет занятия в это время", "понедельник — не день группы", "до старта группы"],
    )
    def test_invalid_trial_rejected(self, make_group, lead, trial):
        group = make_group(start_date=date(2026, 11, 3))
        with pytest.raises(services.InvalidTrialLesson):
            services.create_hold(lead=lead, group_id=group.id, trial_at=trial, now=at(2026, 10, 20))

    def test_past_trial_rejected(self, make_group, lead):
        group = make_group(start_date=date(2026, 11, 3))
        with pytest.raises(services.InvalidTrialLesson):
            services.create_hold(lead=lead, group_id=group.id, trial_at=at(2026, 11, 3, 18, 30), now=at(2026, 11, 4))


class TestBookingFlow:
    def test_hold_and_confirm(self, make_group, lead):
        group = make_group()
        booking = services.create_hold(lead=lead, group_id=group.id)
        assert booking.status == Booking.Status.HELD and booking.expires_at > timezone.now()

        services.confirm_booking(booking)
        booking.refresh_from_db()
        lead.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert lead.status == Lead.Status.BOOKED

    def test_capacity_enforced(self, make_group, make_lead):
        group = make_group(capacity=1)
        services.create_hold(lead=make_lead(), group_id=group.id)
        with pytest.raises(services.GroupFull):
            services.create_hold(lead=make_lead(), group_id=group.id)

    def test_hold_is_idempotent(self, make_group, lead):
        group = make_group(capacity=1)
        first = services.create_hold(lead=lead, group_id=group.id)
        assert services.create_hold(lead=lead, group_id=group.id).pk == first.pk

    def test_rehold_after_expiry(self, make_group, lead):
        group = make_group()
        old = services.create_hold(lead=lead, group_id=group.id, now=timezone.now() - timedelta(hours=1))
        new = services.create_hold(lead=lead, group_id=group.id)
        old.refresh_from_db()
        assert old.status == Booking.Status.EXPIRED and new.status == Booking.Status.HELD

    def test_confirm_expired_hold_fails(self, make_group, lead):
        group = make_group()
        booking = services.create_hold(lead=lead, group_id=group.id, now=timezone.now() - timedelta(hours=1))
        with pytest.raises(services.HoldExpired):
            services.confirm_booking(booking)
        booking.refresh_from_db()
        assert booking.status == Booking.Status.EXPIRED

    def test_phone_required(self, make_group, make_lead):
        with pytest.raises(services.MissingContact):
            services.create_hold(lead=make_lead(phone=""), group_id=make_group().id)

    def test_age_checked(self, make_group, make_lead):
        with pytest.raises(services.AgeMismatch):
            services.create_hold(lead=make_lead(age=12), group_id=make_group(min_age=16).id)

    def test_waitlist_then_hold(self, make_group, lead):
        group = make_group()
        waiting = services.join_waitlist(lead=lead, group_id=group.id)
        held = services.create_hold(lead=lead, group_id=group.id)
        assert held.pk == waiting.pk and held.status == Booking.Status.HELD

    def test_cancel_frees_seat(self, make_group, make_lead):
        group = make_group(capacity=1)
        booking = services.create_hold(lead=make_lead(), group_id=group.id)
        services.cancel_booking(booking)
        services.create_hold(lead=make_lead(), group_id=group.id)  # не падает

    def test_cancel_confirmed_notifies_manager(self, make_group, lead):
        booking = services.confirm_booking(services.create_hold(lead=lead, group_id=make_group(name="B1 вечер").id))
        services.cancel_booking(booking)
        lead.refresh_from_db()
        assert "отменил запись в «B1 вечер»" in lead.manager_note
        assert lead.status == Lead.Status.NEW
        assert list(services.active_bookings(lead)) == []

    def test_release_expired_holds(self, make_group, lead):
        group = make_group()
        services.create_hold(lead=lead, group_id=group.id, now=timezone.now() - timedelta(hours=1))
        assert services.release_expired_holds() == 1
        assert Booking.objects.get().status == Booking.Status.EXPIRED


class TestBookingAPI:
    search_params = {"level": "B1", "days": "1", "period": "evening"}

    def test_search_hold_confirm(self, make_group, lead, api_for):
        group = make_group(capacity=1)
        client = api_for(lead.user)

        found = client.get("/api/c/demo/groups/search/", self.search_params)
        assert found.status_code == 200
        assert found.json()[0]["id"] == group.id and found.json()[0]["free_seats"] == 1

        held = client.post("/api/c/demo/bookings/", {"group": group.id}, format="json")
        assert held.status_code == 201 and held.json()["status"] == "held"

        confirmed = client.post(f"/api/c/demo/bookings/{held.json()['id']}/confirm/")
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"

        assert client.get("/api/c/demo/groups/search/", self.search_params).json() == []

    def test_full_group_returns_409(self, make_group, make_lead, api_for):
        group = make_group(capacity=1)
        services.create_hold(lead=make_lead(), group_id=group.id)
        response = api_for(make_lead().user).post("/api/c/demo/bookings/", {"group": group.id}, format="json")
        assert response.status_code == 409

    def test_cannot_see_others_bookings(self, make_group, make_lead, api_for):
        booking = services.create_hold(lead=make_lead(), group_id=make_group().id)
        stranger = api_for(make_lead().user)
        assert stranger.get("/api/c/demo/bookings/").json() == []
        assert stranger.post(f"/api/c/demo/bookings/{booking.id}/confirm/").status_code == 404

    def test_bad_days_param(self, center, lead, api_for):
        response = api_for(lead.user).get("/api/c/demo/groups/search/", {"level": "B1", "days": "1,9"})
        assert response.status_code == 400

    def test_requires_auth(self, center, client):
        assert client.get("/api/c/demo/groups/search/", self.search_params).status_code == 401
