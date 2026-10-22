"""Подбор групп и запись. Единственное место, где меняются места в группах.

ИИ-консультант и API вызывают только эти функции — сами они цифры не придумывают.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.models import Group
from apps.core.models import Center, Branch
from apps.leads.models import Lead

from .models import Booking


class BookingError(Exception):
    pass


class GroupNotFound(BookingError):
    pass


class GroupFull(BookingError):
    pass


class AgeMismatch(BookingError):
    pass


class MissingContact(BookingError):
    pass


class HoldExpired(BookingError):
    pass


class InvalidTransition(BookingError):
    pass


class InvalidTrialLesson(BookingError):
    pass


def occupying_q(now: datetime, prefix: str = "") -> Q:
    """Брони, которые занимают место: подтверждённые и ещё не истёкшие удержания."""
    return Q(**{f"{prefix}status": Booking.Status.CONFIRMED}) | Q(
        **{f"{prefix}status": Booking.Status.HELD, f"{prefix}expires_at__gt": now}
    )


def taken_seats(group: Group, now: datetime | None = None) -> int:
    return group.bookings.filter(occupying_q(now or timezone.now())).count()


ANY_PERIOD = "any"


@dataclass(frozen=True)
class TrialLesson:
    """Ближайшее занятие группы, на которое можно прийти пробно."""

    date: date
    start_time: time
    end_time: time

    @property
    def starts_at(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.date, self.start_time))


def nearest_trial(group: Group, weekdays: set[int], period: str, now: datetime) -> TrialLesson | None:
    """Ближайшее будущее занятие группы в выбранные дни и время суток (группа может уже идти)."""
    local_now = timezone.localtime(now)
    first_day = max(local_now.date(), group.start_date)
    candidates = []
    for slot in group.slots.all():
        if slot.weekday not in weekdays or (period != ANY_PERIOD and slot.period != period):
            continue
        day = first_day + timedelta(days=(slot.weekday - first_day.weekday()) % 7)
        if day == local_now.date() and slot.start_time <= local_now.time():
            day += timedelta(days=7)  # сегодняшнее занятие уже началось
        candidates.append(TrialLesson(day, slot.start_time, slot.end_time))
    return min(candidates, key=lambda trial: trial.starts_at, default=None)


def find_matching_groups(
    center: Center,
    *,
    level: str,
    weekdays: set[int],
    period: str = ANY_PERIOD,
    branch: Branch | int | None = None,
    age: int | None = None,
    limit: int = 3,
    now: datetime | None = None,
) -> list[Group]:
    """Группы со свободными местами, у которых ХОТЯ БЫ ОДНО занятие выпадает на выбранный день
    и время суток: ученику нужен один удобный пробный урок, а не всё расписание.

    Сортировка — по ближайшему пробному уроку. У групп выставлены free_seats и trial.
    """
    now = now or timezone.now()
    groups = (
        Group.objects.filter(center=center, level=level, is_active=True)
        .select_related("course", "branch")
        .prefetch_related("slots")
        .annotate(taken=Count("bookings", filter=occupying_q(now, prefix="bookings__")))
    )
    if branch is not None:
        groups = groups.filter(branch=branch)
    if age is not None:
        groups = groups.filter(Q(min_age__isnull=True) | Q(min_age__lte=age)).filter(
            Q(max_age__isnull=True) | Q(max_age__gte=age)
        )

    matches = []
    for group in groups:
        free = group.capacity - group.taken
        trial = nearest_trial(group, weekdays, period, now) if free > 0 else None
        if trial:
            group.free_seats, group.trial = free, trial
            matches.append(group)
    matches.sort(key=lambda g: (g.trial.starts_at, g.id))
    return matches[:limit]


def _lock_group(lead: Lead, group_id: int) -> Group:
    try:
        return Group.objects.select_for_update().get(pk=group_id, center=lead.center, is_active=True)
    except Group.DoesNotExist as exc:
        raise GroupNotFound("Группа не найдена или набор закрыт.") from exc


def _require_phone(lead: Lead):
    if not lead.phone:
        raise MissingContact("Укажите телефон, чтобы записаться.")


def _check_trial(group: Group, trial_at: datetime, now: datetime) -> datetime:
    """Пробный урок должен быть настоящим будущим занятием этой группы."""
    local = timezone.localtime(trial_at)
    is_lesson = group.slots.filter(weekday=local.weekday(), start_time=local.time().replace(microsecond=0)).exists()
    if not is_lesson or local.date() < group.start_date or trial_at <= now:
        raise InvalidTrialLesson("В это время у группы нет занятия.")
    return trial_at


@transaction.atomic
def create_hold(*, lead: Lead, group_id: int, trial_at: datetime | None = None, now: datetime | None = None) -> Booking:
    """Удержать место в группе на BOOKING_HOLD_MINUTES минут (и, если указан, пробный урок)."""
    now = now or timezone.now()
    _require_phone(lead)

    # Блокировка строки группы: параллельные брони в ту же группу ждут друг друга.
    group = _lock_group(lead, group_id)
    if lead.age is not None and not group.accepts_age(lead.age):
        raise AgeMismatch("Группа не подходит по возрасту.")
    if trial_at is not None:
        _check_trial(group, trial_at, now)

    existing = Booking.objects.filter(
        lead=lead, group=group, status__in=[Booking.Status.HELD, Booking.Status.CONFIRMED]
    ).first()
    if existing:
        if existing.status == Booking.Status.CONFIRMED or existing.expires_at > now:
            if trial_at and existing.trial_at != trial_at:
                existing.trial_at = trial_at
                existing.save(update_fields=["trial_at", "updated_at"])
            return existing
        existing.status = Booking.Status.EXPIRED
        existing.save(update_fields=["status", "updated_at"])

    if taken_seats(group, now) >= group.capacity:
        raise GroupFull("В группе не осталось мест. Можно встать в лист ожидания.")

    # Если человек был в листе ожидания этой группы — переводим запись в бронь.
    booking = Booking.objects.filter(lead=lead, group=group, status=Booking.Status.WAITLIST).first()
    booking = booking or Booking(center=lead.center, lead=lead, group=group)
    booking.status = Booking.Status.HELD
    booking.expires_at = now + timedelta(minutes=settings.BOOKING_HOLD_MINUTES)
    booking.trial_at = trial_at
    booking.save()
    return booking


@transaction.atomic
def join_waitlist(*, lead: Lead, group_id: int) -> Booking:
    _require_phone(lead)
    group = _lock_group(lead, group_id)
    existing = Booking.objects.filter(
        lead=lead,
        group=group,
        status__in=[Booking.Status.HELD, Booking.Status.CONFIRMED, Booking.Status.WAITLIST],
    ).first()
    if existing:
        return existing
    return Booking.objects.create(center=lead.center, lead=lead, group=group, status=Booking.Status.WAITLIST)


def confirm_booking(booking: Booking, now: datetime | None = None) -> Booking:
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("lead").get(pk=booking.pk)
        if booking.status == Booking.Status.CONFIRMED:
            return booking
        if booking.status != Booking.Status.HELD:
            raise InvalidTransition("Подтвердить можно только удерживаемую бронь.")

        expired = booking.expires_at <= now
        if expired:
            booking.status = Booking.Status.EXPIRED
            booking.save(update_fields=["status", "updated_at"])
        else:
            booking.status = Booking.Status.CONFIRMED
            booking.confirmed_at = now
            booking.expires_at = None
            booking.save(update_fields=["status", "confirmed_at", "expires_at", "updated_at"])

            lead = booking.lead
            lead.status = Lead.Status.BOOKED
            lead.save(update_fields=["status", "updated_at"])

    # Бросаем после выхода из транзакции, иначе откатится и статус EXPIRED.
    if expired:
        raise HoldExpired("Время брони истекло. Забронируйте место заново.")
    return booking


@transaction.atomic
def cancel_booking(booking: Booking) -> Booking:
    booking = Booking.objects.select_for_update(of=("self",)).select_related("lead", "group").get(pk=booking.pk)
    if booking.status in (Booking.Status.CANCELLED, Booking.Status.EXPIRED):
        return booking
    was_confirmed = booking.status == Booking.Status.CONFIRMED
    booking.status = Booking.Status.CANCELLED
    booking.expires_at = None
    booking.save(update_fields=["status", "expires_at", "updated_at"])

    if was_confirmed:
        # Менеджер должен узнать об отмене подтверждённой записи (пробного занятия).
        lead = booking.lead
        note = f"{timezone.localdate():%d.%m.%Y}: ученик отменил запись в «{booking.group.name}»"
        lead.manager_note = f"{lead.manager_note}\n{note}".strip()[:5000]
        fields = ["manager_note", "updated_at"]
        if lead.status == Lead.Status.BOOKED and not lead.bookings.filter(status=Booking.Status.CONFIRMED).exists():
            lead.status = Lead.Status.TESTED if lead.assessed_level else Lead.Status.NEW
            fields.append("status")
        lead.save(update_fields=fields)
    return booking


def active_bookings(lead: Lead, now: datetime | None = None):
    """Записи, которые сейчас действуют: подтверждённые и неистёкшие брони."""
    return (
        Booking.objects.filter(occupying_q(now or timezone.now()), lead=lead)
        .select_related("group__course", "group__branch")
        .prefetch_related("group__slots")
        .order_by("group__start_date", "id")
    )


def release_expired_holds(now: datetime | None = None) -> int:
    """Перевести истёкшие удержания в EXPIRED. Запускать периодически (потом — Celery beat)."""
    return Booking.objects.filter(
        status=Booking.Status.HELD, expires_at__lte=now or timezone.now()
    ).update(status=Booking.Status.EXPIRED, updated_at=timezone.now())
