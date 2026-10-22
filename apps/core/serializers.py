from rest_framework import serializers

from .models import Branch, User


class TelegramAuthSerializer(serializers.Serializer):
    center = serializers.SlugField()
    init_data = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "telegram_id", "telegram_username", "first_name", "phone", "language"]
        read_only_fields = fields


class TelegramAuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address"]
