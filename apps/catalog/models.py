from datetime import time

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import Branch, Center


class Level(models.TextChoices):
    A0 = "A0", "Beginner (A0)"
    A1 = "A1", "Elementary (A1)"
    A2 = "A2", "Pre-Intermediate (A2)"
    B1 = "B1", "Intermediate (B1)"
    B2 = "B2", "Upper-Intermediate (B2)"
    C1 = "C1", "Advanced (C1)"


LEVEL_ORDER = [Level.A0, Level.A1, Level.A2, Level.B1, Level.B2, Level.C1]


def level_index(level: str) -> int:
    return LEVEL_ORDER.index(level)


class DayPeriod(models.TextChoices):
    """Время суток занятия — по времени его начала. Ученик выбирает его вместо точных часов."""

    MORNING = "morning", "Утро"
    DAY = "day", "День"
    EVENING = "evening", "Вечер"


DAY_STARTS_AT = time(12, 0)
EVENING_STARTS_AT = time(17, 0)


def period_of(start: time) -> str:
    if start < DAY_STARTS_AT:
        return DayPeriod.MORNING
    if start < EVENING_STARTS_AT:
        return DayPeriod.DAY
    return DayPeriod.EVENING


class Weekday(models.IntegerChoices):
    MON = 0, "Пн"
    TUE = 1, "Вт"
    WED = 2, "Ср"
    THU = 3, "Чт"
    FRI = 4, "Пт"
    SAT = 5, "Сб"
    SUN = 6, "Вс"


class Course(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="courses")
    name = models.CharField("название", max_length=200)
    subject = models.CharField("предмет", max_length=50, default="english")
    description = models.TextField("описание", blank=True)
    price_per_month = models.DecimalField("цена в месяц, сум", max_digits=12, decimal_places=0)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "курс"
        verbose_name_plural = "курсы"

    def __str__(self):
        return self.name


class Group(models.Model):
    # center дублируется из course, чтобы все запросы фильтровались по центру одинаково.
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="groups", editable=False)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="groups")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="groups")
    name = models.CharField("название", max_length=200)
    level = models.CharField("уровень", max_length=2, choices=Level.choices)
    capacity = models.PositiveSmallIntegerField("мест")
    min_age = models.PositiveSmallIntegerField("мин. возраст", null=True, blank=True)
    max_age = models.PositiveSmallIntegerField("макс. возраст", null=True, blank=True)
    start_date = models.DateField("дата старта")
    teacher_name = models.CharField("преподаватель", max_length=200, blank=True)
    is_active = models.BooleanField("набор открыт", default=True)

    class Meta:
        verbose_name = "группа"
        verbose_name_plural = "группы"
        indexes = [models.Index(fields=["center", "level", "is_active"])]

    def __str__(self):
        return self.name

    def clean(self):
        if self.course_id and self.branch_id and self.branch.center_id != self.course.center_id:
            raise ValidationError("Филиал и курс должны принадлежать одному центру.")

    def save(self, *args, **kwargs):
        self.clean()
        self.center_id = self.course.center_id
        super().save(*args, **kwargs)

    def accepts_age(self, age: int) -> bool:
        if self.min_age is not None and age < self.min_age:
            return False
        if self.max_age is not None and age > self.max_age:
            return False
        return True


class GroupSlot(models.Model):
    """Одно занятие в неделю: группа Вт/Чт 18:30–20:00 — это два слота."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="slots")
    weekday = models.PositiveSmallIntegerField("день недели", choices=Weekday.choices)
    start_time = models.TimeField("начало")
    end_time = models.TimeField("конец")

    class Meta:
        verbose_name = "занятие в расписании"
        verbose_name_plural = "расписание"
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="group_slot_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    @property
    def period(self) -> str:
        return period_of(self.start_time)
