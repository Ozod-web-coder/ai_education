from rest_framework import serializers

from .models import Course, Group, GroupSlot


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "name", "subject", "description", "price_per_month"]


class GroupSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupSlot
        fields = ["weekday", "start_time", "end_time"]


class GroupCardSerializer(serializers.ModelSerializer):
    course = serializers.CharField(source="course.name")
    branch = serializers.CharField(source="branch.name")
    slots = GroupSlotSerializer(many=True)
    free_seats = serializers.SerializerMethodField()
    trial = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "level", "course", "branch", "start_date", "slots", "free_seats", "trial"]

    # free_seats и trial заполняются только в результатах поиска (booking.services.find_matching_groups).
    def get_free_seats(self, obj) -> int | None:
        return getattr(obj, "free_seats", None)

    def get_trial(self, obj) -> dict | None:
        trial = getattr(obj, "trial", None)
        if trial is None:
            return None
        return {"starts_at": trial.starts_at.isoformat(), "end_time": trial.end_time.strftime("%H:%M")}
