"""Проверка initData из Telegram Mini App.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InvalidInitData(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int, now: float | None = None) -> dict:
    """Возвращает распарсенные поля initData или бросает InvalidInitData."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise InvalidInitData("initData не разобрать") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("В initData нет hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InvalidInitData("Подпись initData неверна")

    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InvalidInitData("В initData нет auth_date") from exc
    if (now if now is not None else time.time()) - auth_date > max_age_seconds:
        raise InvalidInitData("initData устарел")

    try:
        user = json.loads(pairs["user"])
        user["id"] = int(user["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInitData("В initData нет пользователя") from exc

    return {**pairs, "auth_date": auth_date, "user": user}
