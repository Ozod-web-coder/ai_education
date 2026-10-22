from django.utils import timezone
from rest_framework import serializers

from .models import ADULT_AGE, Lead


class LeadSerializer(serializers.ModelSerializer):
    consent_personal_data = serializers.BooleanField(write_only=True, required=False)
    consent_parent = serializers.BooleanField(write_only=True, required=False)
    is_minor = serializers.BooleanField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "phone",
            "age",
            "goal",
            "preferred_branch",
            "declared_level",
            "assessed_level",
            "status",
            "parent_name",
            "parent_phone",
            "is_minor",
            "consent_personal_data",
            "consent_parent",
            "personal_data_consent_at",
            "parent_consent_at",
            "created_at",
        ]
        read_only_fields = ["assessed_level", "status", "personal_data_consent_at", "parent_consent_at", "created_at"]

    def validate_preferred_branch(self, branch):
        if branch and branch.center_id != self.context["center"].id:
            raise serializers.ValidationError("Филиал не принадлежит этому центру.")
        return branch

    def validate(self, attrs):
        lead = self.instance

        def current(field):
            if field in attrs:
                return attrs[field]
            return getattr(lead, field) if lead else None

        errors = {}
        if not attrs.get("consent_personal_data") and not (lead and lead.personal_data_consent_at):
            errors["consent_personal_data"] = "Нужно согласие на обработку персональных данных."

        age = current("age")
        if age is not None and age < ADULT_AGE:
            if not current("parent_phone"):
                errors["parent_phone"] = "Для несовершеннолетних нужен телефон родителя."
            if not attrs.get("consent_parent") and not (lead and lead.parent_consent_at):
                errors["consent_parent"] = "Для несовершеннолетних нужно согласие родителя."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _apply_consents(self, validated_data):
        now = timezone.now()
        lead = self.instance
        if validated_data.pop("consent_personal_data", False) and not (lead and lead.personal_data_consent_at):
            validated_data["personal_data_consent_at"] = now
        if validated_data.pop("consent_parent", False) and not (lead and lead.parent_consent_at):
            validated_data["parent_consent_at"] = now
        return validated_data

    def create(self, validated_data):
        return super().create(self._apply_consents(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._apply_consents(validated_data))
