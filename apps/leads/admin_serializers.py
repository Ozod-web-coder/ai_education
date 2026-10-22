from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Course

from .models import Lead

# Статусы, из которых «Подтвердить» переводит заявку в «Подтверждена».
# Дальше по воронке (пришёл, записан, отказался…) статус не откатываем.
BEFORE_CONFIRMATION = {Lead.Status.NEW, Lead.Status.TESTED, Lead.Status.BOOKED, Lead.Status.NEEDS_MANAGER}


class AdminLeadSerializer(serializers.ModelSerializer):
    """Заявка для администратора. Меняются только имя, телефон, статус, заметка и курс."""

    telegram_username = serializers.CharField(source="user.telegram_username", read_only=True, default="")
    telegram_id = serializers.IntegerField(source="user.telegram_id", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    course = serializers.SerializerMethodField()
    desired_course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), allow_null=True, required=False)
    is_minor = serializers.BooleanField(read_only=True)
    duplicate_count = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "phone",
            "telegram_username",
            "telegram_id",
            "course",
            "desired_course",
            "status",
            "status_display",
            "contacted_at",
            "created_at",
            "age",
            "is_minor",
            "duplicate_count",
        ]
        read_only_fields = ["age", "contacted_at", "created_at"]

    def get_course(self, lead) -> str:
        if lead.desired_course_id:
            return lead.desired_course.name
        # bookings отсортированы по -created_at, первая — последняя запись
        bookings = list(lead.bookings.all())
        return bookings[0].group.course.name if bookings else ""

    def get_duplicate_count(self, lead) -> int:
        return len(self.context.get("duplicates", {}).get(lead.id, ()))

    def validate_desired_course(self, course):
        if course and course.center_id != self.context["center"].id:
            raise serializers.ValidationError("Курс не принадлежит этому центру.")
        return course

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Имя не может быть пустым.")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data.get("status")
        if new_status == Lead.Status.CONFIRMED and not instance.contacted_at:
            validated_data["contacted_at"] = timezone.now()
        return super().update(instance, validated_data)


class AdminBookingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    group = serializers.CharField(source="group.name")
    course = serializers.CharField(source="group.course.name")
    branch = serializers.CharField(source="group.branch.name")
    status = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display")
    trial_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class DuplicateSerializer(serializers.ModelSerializer):
    telegram_username = serializers.CharField(source="user.telegram_username", default="")
    status_display = serializers.CharField(source="get_status_display")

    class Meta:
        model = Lead
        fields = ["id", "name", "phone", "telegram_username", "status", "status_display", "created_at"]


class AdminLeadDetailSerializer(AdminLeadSerializer):
    declared_level = serializers.CharField(read_only=True)
    assessed_level = serializers.CharField(read_only=True)
    goal = serializers.CharField(read_only=True)
    parent_name = serializers.CharField(read_only=True)
    parent_phone = serializers.CharField(read_only=True)
    bookings = AdminBookingSerializer(many=True, read_only=True)
    duplicates = serializers.SerializerMethodField()

    class Meta(AdminLeadSerializer.Meta):
        fields = AdminLeadSerializer.Meta.fields + [
            "declared_level",
            "assessed_level",
            "goal",
            "manager_note",
            "parent_name",
            "parent_phone",
            "bookings",
            "duplicates",
        ]

    def get_duplicates(self, lead) -> list[dict]:
        ids = self.context.get("duplicates", {}).get(lead.id, ())
        others = Lead.objects.filter(id__in=ids).select_related("user").order_by("-created_at")
        return DuplicateSerializer(others, many=True).data
