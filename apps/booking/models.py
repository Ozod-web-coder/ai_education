from django.db import models

from apps.catalog.models import Group
from apps.core.models import Center
from apps.leads.models import Lead


class Booking(models.Model):
    class Status(models.TextChoices):
        HELD = "held", "Место удерживается"
        CONFIRMED = "confirmed", "Подтверждена"
        WAITLIST = "waitlist", "Лист ожидания"
        CANCELLED = "cancelled", "Отменена"
        EXPIRED = "expired", "Бронь истекла"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="bookings")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="bookings")
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=20, choices=Status.choices)
    expires_at = models.DateTimeField("бронь до", null=True, blank=True)
    trial_at = models.DateTimeField("пробный урок", null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "запись"
        verbose_name_plural = "записи"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "group"],
                condition=models.Q(status__in=["held", "confirmed", "waitlist"]),
                name="one_open_booking_per_lead_group",
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"{self.lead} → {self.group} ({self.get_status_display()})"
