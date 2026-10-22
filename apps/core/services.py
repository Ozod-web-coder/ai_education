from .models import Language, User


def get_or_create_telegram_user(
    *,
    telegram_id: int,
    first_name: str = "",
    telegram_username: str = "",
    language_code: str = "",
    default_language: str = Language.RU,
) -> User:
    """Найти или создать пользователя по telegram_id и обновить имя и @username из профиля."""
    first_name = (first_name or "")[:150]
    telegram_username = (telegram_username or "")[:32]
    language = (language_code or "")[:2]
    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "username": f"tg_{telegram_id}",
            "first_name": first_name,
            "telegram_username": telegram_username,
            "language": language if language in Language.values else default_language,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    elif (user.first_name, user.telegram_username) != (first_name, telegram_username):
        # Имя и @username в Telegram можно поменять в любой момент.
        user.first_name = first_name
        user.telegram_username = telegram_username
        user.save(update_fields=["first_name", "telegram_username"])
    return user
