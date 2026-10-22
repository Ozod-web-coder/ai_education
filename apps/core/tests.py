import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from apps.core.models import User
from apps.core.telegram import InvalidInitData, validate_init_data
from conftest import BOT_TOKEN

TG_USER = {"id": 777, "first_name": "Ali", "username": "ali_tg", "language_code": "uz"}


def build_init_data(bot_token=BOT_TOKEN, user=TG_USER, auth_date=None):
    """Собрать initData так же, как это делает Telegram."""
    pairs = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


class TestValidateInitData:
    def test_valid(self):
        data = validate_init_data(build_init_data(), BOT_TOKEN, max_age_seconds=60)
        assert data["user"]["id"] == 777

    def test_wrong_bot_token(self):
        with pytest.raises(InvalidInitData):
            validate_init_data(build_init_data(), "other:token", max_age_seconds=60)

    def test_tampered_user(self):
        tampered = build_init_data().replace("Ali", "Bob")
        with pytest.raises(InvalidInitData):
            validate_init_data(tampered, BOT_TOKEN, max_age_seconds=60)

    def test_expired(self):
        old = build_init_data(auth_date=int(time.time()) - 3600)
        with pytest.raises(InvalidInitData, match="устарел"):
            validate_init_data(old, BOT_TOKEN, max_age_seconds=60)

    def test_missing_hash(self):
        with pytest.raises(InvalidInitData):
            validate_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN, max_age_seconds=60)


def test_user_has_no_email_or_last_name():
    field_names = {f.name for f in User._meta.get_fields()}
    assert "email" not in field_names and "last_name" not in field_names


class TestTelegramAuthAPI:
    url = "/api/auth/telegram/"

    def test_creates_user_and_returns_tokens(self, client, center):
        response = client.post(self.url, {"center": "demo", "init_data": build_init_data()}, content_type="application/json")
        assert response.status_code == 200
        body = response.json()
        assert body["access"] and body["refresh"]
        user = User.objects.get(telegram_id=777)
        assert user.language == "uz"
        assert user.telegram_username == "ali_tg"
        assert body["user"]["telegram_username"] == "ali_tg"
        assert not user.has_usable_password()

    def test_second_login_reuses_user(self, client, center):
        for _ in range(2):
            client.post(self.url, {"center": "demo", "init_data": build_init_data()}, content_type="application/json")
        assert User.objects.filter(telegram_id=777).count() == 1

    def test_bad_signature_rejected(self, client, center):
        response = client.post(
            self.url,
            {"center": "demo", "init_data": build_init_data(bot_token="other:token")},
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_token_works_for_api(self, client, center):
        access = client.post(
            self.url, {"center": "demo", "init_data": build_init_data()}, content_type="application/json"
        ).json()["access"]
        response = client.get("/api/c/demo/courses/", HTTP_AUTHORIZATION=f"Bearer {access}")
        assert response.status_code == 200
