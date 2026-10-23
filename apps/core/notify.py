"""Отправка сообщений ученикам в Telegram от имени бота центра.

Бот (bot/) работает через polling, а админ-API живёт в Django, поэтому уведомления шлём напрямую
через Bot API тем же токеном: это не мешает polling. Без новых зависимостей, с коротким таймаутом.
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

SENT = "sent"
NO_BOT = "no_bot"  # у центра не задан токен бота
BLOCKED = "blocked"  # ученик заблокировал бота или удалил чат
ERROR = "error"  # сеть или другая ошибка Telegram

TIMEOUT_SECONDS = 5


def send_message(bot_token: str, chat_id: int, text: str) -> str:
    """Отправить HTML-сообщение. Возвращает SENT, NO_BOT, BLOCKED или ERROR; исключений не бросает."""
    if not bot_token:
        return NO_BOT
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            return SENT
    except urllib.error.HTTPError as error:
        # 403: пользователь заблокировал бота; 400 «chat not found»: чата с ботом нет.
        logger.warning("Telegram sendMessage → HTTP %s", error.code)
        return BLOCKED if error.code in (400, 403) else ERROR
    except (urllib.error.URLError, TimeoutError, OSError):
        logger.warning("Telegram sendMessage: нет связи с api.telegram.org")
        return ERROR
