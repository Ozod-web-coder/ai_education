# Telegram-бот (long polling): работает постоянно, поэтому нужен хостинг для постоянных процессов
# (Railway, Render Background Worker, Fly.io, VPS), а не serverless вроде Vercel.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY bot/requirements.txt ./bot/requirements.txt
RUN pip install --no-cache-dir -r bot/requirements.txt

COPY . .

# Нужны переменные окружения: SECRET_KEY, DATABASE_URL, CENTER_SLUG (по умолчанию demo), LLM_*.
CMD ["python", "-m", "bot"]
