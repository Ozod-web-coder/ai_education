from rest_framework import serializers

from apps.catalog.models import DayPeriod, Level
from apps.catalog.serializers import GroupCardSerializer

from .models import Booking
from .services import ANY_PERIOD


class WeekdaysField(serializers.CharField):
    """Дни недели строкой "1,3" (0 = понедельник) → {1, 3}."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            days = {int(part) for part in value.split(",") if part.strip()}
        except ValueError:
            days = set()
        if not days or not days <= set(range(7)):
            raise serializers.ValidationError("Укажите дни недели числами 0–6 через запятую (0 = понедельник).")
        return days


class GroupSearchQuerySerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=Level.choices)
    days = WeekdaysField(help_text="Дни, когда ученику удобно прийти на пробный урок: 0–6 через запятую, 0 = Пн")
    period = serializers.ChoiceField(
        choices=[*DayPeriod.choices, (ANY_PERIOD, "Любое")], default=ANY_PERIOD, help_text="Время суток"
    )
    branch = serializers.IntegerField(required=False)
    age = serializers.IntegerField(required=False, min_value=3, max_value=100)


class BookingSerializer(serializers.ModelSerializer):
    group = GroupCardSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "group", "status", "trial_at", "expires_at", "confirmed_at", "created_at"]


class BookingCreateSerializer(serializers.Serializer):
    group = serializers.IntegerField()
    trial_at = serializers.DateTimeField(required=False, help_text="Пробный урок из результата поиска (trial.starts_at)")
    waitlist = serializers.BooleanField(default=False, help_text="true — встать в лист ожидания вместо брони")
