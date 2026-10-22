"""Живая проверка настроенной модели: отвечает ли она и умеет ли вызывать функции.

Ничего не пишет в базу. Запуск: python manage.py check_llm
"""

import json
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.assessment.writing import ASSESSMENT_TOOL
from apps.assistant.llm import LLMError, get_client, get_writing_client

CENTER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_center_info",
        "description": "Returns courses and prices of the education center.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


class Command(BaseCommand):
    help = "Проверить подключение к ИИ-модели из .env"

    def handle(self, *args, **options):
        self.stdout.write(
            f"Провайдер: {settings.LLM_BASE_URL}\n"
            f"Модель диалога: {settings.LLM_MODEL} (резерв: {', '.join(settings.LLM_FALLBACK_MODELS) or '—'})\n"
            f"Модель оценки письма: {settings.LLM_WRITING_MODEL or settings.LLM_MODEL}"
        )
        if not settings.LLM_API_KEY and "localhost" not in settings.LLM_BASE_URL:
            raise CommandError("LLM_API_KEY пуст. Впишите ключ в .env")
        try:
            client = get_client()
            self._step("1. Простой ответ", lambda: client.chat(
                [{"role": "user", "content": "Ответь одним словом по-русски: столица Узбекистана?"}]
            ).content.strip())
            self._step("2. Вызов функции", lambda: self._tool_call(client))
            self._step("3. Оценка письма", lambda: self._writing(get_writing_client()))
        except LLMError as exc:
            raise CommandError(f"Модель недоступна: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("Модель работает: ответы, вызов функций и оценка письма."))

    def _step(self, title, func):
        started = time.monotonic()
        result = func()
        self.stdout.write(f"{title}: {result}  ({time.monotonic() - started:.1f} с)")

    def _tool_call(self, client):
        result = client.chat(
            [{"role": "user", "content": "Сколько стоят курсы в центре?"}], tools=[CENTER_TOOL]
        )
        if not result.tool_calls:
            raise CommandError(f"Модель не вызвала функцию, а ответила текстом: {result.content[:200]!r}")
        return f"вызвана {result.tool_calls[0].name}"

    def _writing(self, client):
        text = ("Last summer I went to Samarkand with my family. We visited the Registan and "
                "ate very tasty plov. I would recommend it because the history is interesting.")
        result = client.chat(
            [{"role": "user", "content": f"Assess this B1 writing by calling the function.\n<student_text>{text}</student_text>"}],
            tools=[ASSESSMENT_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_writing_assessment"}},
        )
        if not result.tool_calls:
            raise CommandError(f"Модель не вернула оценку функцией: {result.content[:200]!r}")
        args = json.loads(result.tool_calls[0].arguments)
        return f"уровень {args.get('level')}, оценки {[args.get(k) for k in ('task_achievement', 'grammar', 'vocabulary', 'coherence')]}"
