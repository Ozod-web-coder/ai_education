from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from apps.core.models import Center

from . import db
from .handlers import router


async def run(center_slug: str):
    try:
        center = await db.get_center(center_slug)
    except Center.DoesNotExist:
        raise SystemExit(f"Центр «{center_slug}» не найден. Создайте его в админке или командой seed_demo.")
    if not center.bot_token:
        raise SystemExit(
            f"У центра «{center_slug}» не задан bot_token. "
            "Укажите его в админке или: python manage.py seed_demo --bot-token <токен>"
        )

    bot = Bot(center.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # MemoryStorage теряет состояние диалогов при перезапуске; позже заменим на Redis.
    dp = Dispatcher(storage=MemoryStorage())
    dp["center"] = center
    dp.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Подобрать группу / Guruh tanlash"),
            BotCommand(command="my", description="Мои записи / Mening yozuvlarim"),
            BotCommand(command="language", description="Язык / Til"),
            BotCommand(command="help", description="Помощь / Yordam"),
        ]
    )
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
