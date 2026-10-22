from django.conf import settings
from django.db import models

from apps.catalog.models import Level
from apps.core.models import Branch, Center

ADULT_AGE = 18


class Lead(models.Model):
    """Заявка потенциального ученика в конкретный центр."""

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        TESTED = "tested", "Прошёл тест"
        BOOKED = "booked", "Записан"
        NEEDS_MANAGER = "needs_manager", "Нужен менеджер"
        LOST = "lost", "Потерян"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="leads")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    # Поля заполняются по ходу диалога, поэтому в начале могут быть пустыми.
    # Фамилию не собираем — только имя ученика.
    name = models.CharField("имя ученика", max_length=100, blank=True)
    phone = models.CharField("телефон", max_length=20, blank=True)
    age = models.PositiveSmallIntegerField("возраст", null=True, blank=True)
    goal = models.TextField("цель обучения", blank=True)
    preferred_branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    declared_level = models.CharField("уровень со слов ученика", max_length=2, choices=Level.choices, blank=True)
    assessed_level = models.CharField("уровень по тесту", max_length=2, choices=Level.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    source = models.CharField("источник", max_length=50, default="telegram")
    manager_note = models.TextField("заметка для менеджера", blank=True)

    parent_name = models.CharField("имя родителя", max_length=100, blank=True)
    parent_phone = models.CharField("телефон родителя", max_length=20, blank=True)
    personal_data_consent_at = models.DateTimeField("согласие на обработку ПД", null=True, blank=True)
    parent_consent_at = models.DateTimeField("согласие родителя", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        constraints = [
            models.UniqueConstraint(
                fields=["center", "user"],
                condition=models.Q(user__isnull=False),
                name="one_lead_per_user_per_center",
            ),
        ]

    def __str__(self):
        return self.name or f"Заявка #{self.pk}"

    @property
    def is_minor(self) -> bool:
        return self.age is not None and self.age < ADULT_AGE
