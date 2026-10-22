"""Общая обвязка обработчиков, чтобы не повторять её в каждом из них."""

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag

from . import db
from .texts import LANGUAGES

MANUAL_ANSWER = "manual_answer"


async def resolve_language(state, center, telegram_id: int) -> str:
    lang = (await state.get_data()).get("lang")
    if lang:
        return lang
    # Состояние теряется при перезапуске бота — берём язык из профиля.
    lang = await db.get_language(telegram_id)
    return lang if lang in LANGUAGES else center.default_language


class AnswerCallbackFirst(BaseMiddleware):
    """Отвечаем на нажатие сразу: Telegram убирает часики с кнопки, пока бот работает.

    Обработчик, которому нужен свой ответ (например, всплывающее окно), помечается
    флагом flags={"manual_answer": True} и отвечает сам.
    """

    async def __call__(self, handler, event, data):
        if not get_flag(data, MANUAL_ANSWER):
            await event.answer()
        return await handler(event, data)


class LanguageMiddleware(BaseMiddleware):
    """Передаёт обработчику язык ученика аргументом lang."""

    async def __call__(self, handler, event, data):
        data["lang"] = await resolve_language(data["state"], data["center"], event.from_user.id)
        return await handler(event, data)
