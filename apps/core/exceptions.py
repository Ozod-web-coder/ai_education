from rest_framework.exceptions import APIException


class InvalidTelegramAuth(APIException):
    # Не наследуется от AuthenticationFailed: у вью без authentication_classes
    # DRF превратил бы такую ошибку в 403.
    status_code = 401
    default_detail = "Не удалось проверить вход через Telegram."
    default_code = "invalid_telegram_auth"


class Conflict(APIException):
    status_code = 409
    default_detail = "Конфликт состояния."
    default_code = "conflict"
