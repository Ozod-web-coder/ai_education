"""Поиск повторных заявок: один человек мог записаться с другого Telegram-аккаунта.

Совпадением считаем одинаковый телефон (последние 9 цифр, без кода страны и форматирования)
или одинаковый @username в Telegram. Проверяем только внутри одного центра.
Для центра на тысячи заявок это один быстрый проход по двум полям; если вырастет — вынести в индексируемое поле.
"""

import re
from collections import defaultdict

from .models import Lead

PHONE_KEY_LENGTH = 9


def phone_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-PHONE_KEY_LENGTH:] if len(digits) >= PHONE_KEY_LENGTH else ""


def _username_key(username: str) -> str:
    return (username or "").lstrip("@").strip().lower()


def duplicate_map(center) -> dict[int, set[int]]:
    """{id заявки: ids других заявок того же человека} — только для заявок, у которых есть дубликаты."""
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for lead_id, phone, username in Lead.objects.filter(center=center).values_list(
        "id", "phone", "user__telegram_username"
    ):
        if key := phone_key(phone):
            by_key[("phone", key)].append(lead_id)
        if key := _username_key(username):
            by_key[("tg", key)].append(lead_id)

    result: dict[int, set[int]] = defaultdict(set)
    for ids in by_key.values():
        if len(ids) < 2:
            continue
        for lead_id in ids:
            result[lead_id].update(i for i in ids if i != lead_id)
    return dict(result)
