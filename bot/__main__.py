"""Запуск: python -m bot --center demo"""

import argparse
import asyncio
import logging
import os


def main():
    parser = argparse.ArgumentParser(description="Telegram-бот AI Education")
    parser.add_argument("--center", default="demo", help="slug учебного центра (токен бота берётся из него)")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from bot.app import run

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(args.center))


if __name__ == "__main__":
    main()
