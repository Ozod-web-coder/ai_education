from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .exceptions import InvalidTelegramAuth
from .models import Center
from .serializers import TelegramAuthResponseSerializer, TelegramAuthSerializer, UserSerializer
from .services import get_or_create_telegram_user
from .telegram import InvalidInitData, validate_init_data


class TelegramAuthView(APIView):
    """Вход из Mini App: проверяем initData и выдаём JWT."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=TelegramAuthSerializer, responses=TelegramAuthResponseSerializer)
    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        center = get_object_or_404(Center, slug=serializer.validated_data["center"], is_active=True)
        if not center.bot_token:
            raise InvalidTelegramAuth("Для центра не настроен Telegram-бот")

        try:
            data = validate_init_data(
                serializer.validated_data["init_data"],
                center.bot_token,
                settings.TELEGRAM_INIT_DATA_MAX_AGE,
            )
        except InvalidInitData as exc:
            raise InvalidTelegramAuth(str(exc)) from exc

        tg_user = data["user"]
        user = get_or_create_telegram_user(
            telegram_id=tg_user["id"],
            first_name=tg_user.get("first_name", ""),
            telegram_username=tg_user.get("username", ""),
            language_code=tg_user.get("language_code", ""),
            default_language=center.default_language,
        )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )
