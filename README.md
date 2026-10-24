# AI Education

Платформа записи учеников на пробные уроки для учебных центров: Telegram-бот с ИИ-консультантом, Django API и Mini App администратора.

## Из чего состоит проект

| Часть | Папка | Что это |
|---|---|---|
| Backend | `config/`, `apps/` | Django + DRF: API, админка, вся логика записи |
| Telegram-бот | `bot/` | aiogram 3, long polling, работает с той же базой |
| Mini App администратора | `miniapp/` | React + Vite: заявки, статусы, поиск |

Бот и backend не общаются по сети: бот напрямую использует модели Django и ту же базу, поэтому запускайте их из одной папки проекта и с одним `.env`.

## Быстрый старт на своём компьютере

Нужны Python 3.12 или 3.13 и Node.js 20+ (для Mini App). Команды для Windows PowerShell.

### 1. Backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Если PowerShell ругается на запуск скриптов: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Откройте `.env` и впишите `SECRET_KEY` (любая длинная случайная строка; сгенерировать: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`). Остальное для локального запуска можно оставить: без `DATABASE_URL` используется SQLite.

```powershell
python manage.py migrate
python manage.py seed_demo          # демо-центр со slug=demo, курсы, группы, банк вопросов
python manage.py createsuperuser
python manage.py runserver
```

- Админка: http://127.0.0.1:8000/admin/
- Документация API (Swagger): http://127.0.0.1:8000/api/docs/

### 2. Telegram-бот

Токен бота выдаёт @BotFather. Он сохраняется в центре (в базе), а не в `.env`.

```powershell
pip install -r bot\requirements.txt
python manage.py seed_demo --bot-token 123456:ABC...   # записать токен в демо-центр
python -m bot --center demo
```

Напишите боту `/start`. Остановить: `Ctrl+C`.

> **Один токен, один процесс.** Если бот запущен на сервере, а вы запускаете его ещё и локально, Telegram вернёт ошибку `409 Conflict`. Остановите один из них.

### 3. Mini App администратора

```powershell
cd miniapp
copy .env.example .env      # укажите VITE_CENTER_SLUG=demo
npm install
npm run dev                 # http://localhost:5173
```

Подробности и вход без Telegram для разработки: [miniapp/README.md](miniapp/README.md).

### 4. Тесты

```powershell
pytest
```

## Переменные окружения

Лежат в файле `.env` в корне проекта (он в `.gitignore`). Образец: `.env.example`.

| Переменная | Для чего |
|---|---|
| `SECRET_KEY` | секретный ключ Django. **Обязательна**, без неё ничего не запустится |
| `DEBUG` | `True` для локальной разработки. По умолчанию `False` |
| `ALLOWED_HOSTS` | допустимые адреса (`localhost,127.0.0.1` по умолчанию) |
| `DATABASE_URL` | адрес базы. Пусто = SQLite (`db.sqlite3`), для локальной работы этого достаточно |
| `CORS_ALLOWED_ORIGINS` | адреса Mini App через запятую, например `http://localhost:5173` |
| `MINI_APP_URL` | адрес Mini App для кнопки «Открыть приложение» в боте |
| `CENTER_SLUG` | slug центра для бота (по умолчанию `demo`) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODELS`, `LLM_WRITING_MODEL` | ИИ-консультант, примеры в `.env.example` |
| `TELEGRAM_INIT_DATA_MAX_AGE`, `BOOKING_HOLD_MINUTES` | сроки жизни входа и брони (есть значения по умолчанию) |

Для Mini App отдельный файл `miniapp/.env`: `VITE_CENTER_SLUG` и `VITE_API_URL` (см. `miniapp/.env.example`).

## База данных

По умолчанию используется SQLite, ничего настраивать не нужно. Чтобы работать с PostgreSQL, добавьте в `.env`:

```
DATABASE_URL=postgres://postgres:ПАРОЛЬ@localhost:5432/ai_education
```

и выполните `python manage.py migrate`.

## Частые ошибки

| Ошибка | Что делать |
|---|---|
| «Не задана переменная SECRET_KEY» | создайте `.env` (`copy .env.example .env`) и впишите `SECRET_KEY` |
| Бот: `409 Conflict: terminated by other getUpdates request` | этот токен уже запущен в другом месте. Оставьте один процесс |
| Бот: «У центра не задан bot_token» | `python manage.py seed_demo --bot-token <токен>` или поле «Токен Telegram-бота» в админке центра |
| В Mini App «Откройте из Telegram» | страница открыта в обычном браузере. Для проверки без Telegram см. [miniapp/README.md](miniapp/README.md) |
| В Mini App «Нет доступа» | аккаунт не сотрудник: админка → пользователь → «Сотрудник», центр и Telegram id |
| В Mini App «Нет связи с …» или ошибка CORS | запущен ли backend; адрес Mini App должен быть в `CORS_ALLOWED_ORIGINS` в `.env` (затем перезапустите backend) |
| В Mini App «Не удалось войти» | `VITE_CENTER_SLUG` должен совпадать со slug центра |

## Приложения

| Приложение | Что внутри |
|---|---|
| `apps/core` | Center (клиент SaaS), Branch, User с `telegram_id`, вход через Telegram |
| `apps/catalog` | Course, Group, GroupSlot (расписание), уровни CEFR |
| `apps/leads` | Lead — анкета ученика, согласие на ПД и согласие родителя |
| `apps/booking` | Booking и `services.py` — подбор групп и вся логика мест |

Всё, что меняет места в группах, находится в `apps/booking/services.py`. ИИ-консультант (следующий этап) будет вызывать эти функции как инструменты, а не придумывать расписание сам.

## API

| Метод | URL | Что делает |
|---|---|---|
| POST | `/api/auth/telegram/` | `{center, init_data}` → JWT |
| POST | `/api/auth/token/refresh/` | обновить access-токен |
| GET | `/api/c/<center>/branches/` | филиалы |
| GET | `/api/c/<center>/courses/` | курсы и цены |
| GET/PUT/PATCH | `/api/c/<center>/lead/` | моя анкета |
| GET | `/api/c/<center>/groups/search/?level=B1&days=1,3&period=evening` | до 3 групп со свободными местами и ближайшим пробным уроком |
| GET/POST | `/api/c/<center>/bookings/` | мои записи / забронировать `{group, trial_at, waitlist}` |
| POST | `/api/c/<center>/bookings/<id>/confirm/` | подтвердить бронь |
| POST | `/api/c/<center>/bookings/<id>/cancel/` | отменить |
| GET/PATCH/DELETE, POST `confirm/` | `/api/c/<center>/admin/leads/` | заявки для администратора (только сотрудники центра), см. [miniapp/README.md](miniapp/README.md) |

## Mini App администратора (`miniapp/`)

React + Vite. Сотрудники центра смотрят заявки, меняют статусы (новая, подтверждена, пришёл, не пришёл, записан на курс, отказался), ищут и фильтруют, подтверждают связь с учеником и удаляют ошибочные заявки. Повторные заявки (тот же телефон или @username) помечаются предупреждением. При статусе «Отказался» записи ученика отменяются, а ему в бот приходит уведомление с телефоном администрации (поле «Телефон администрации» у центра в админке). Запуск и подключение к Telegram: [miniapp/README.md](miniapp/README.md).

Доступ получают пользователи с галочкой «Сотрудник», заполненными «Центр» и «Telegram id» (админка Django). Адрес приложения нужно добавить в `CORS_ALLOWED_ORIGINS` в `.env`.

## ИИ-консультант и тест уровня

| Где | Что |
|---|---|
| `apps/assistant/tools.py` | **белый список** функций бэкенда, которые может вызвать агент |
| `apps/assistant/agent.py` | системный промпт и цикл «модель → функция → модель» |
| `apps/assistant/llm.py` | клиент OpenAI-совместимого API (Ollama, Gemini, Groq, OpenRouter) |
| `apps/assessment/services.py` | адаптивный тест: проверку ответов и итоговый уровень считает бэкенд |
| `apps/assessment/writing.py` | оценка письма (B1+) ИИ через функцию `submit_writing_assessment` |

Правила, которые обеспечивает код, а не промпт:
- агент не видит расписание, места и группы: такой функции у него нет, а `start_group_selection` передаёт ученика в подбор бэкенда;
- правильных ответов теста агент не получает — вопросы показывает бот кнопками;
- письменная работа может только понизить уровень по тесту, а не поднять его; расхождение на 2 уровня и больше уходит методисту;
- если ИИ недоступен, бот продолжает работать кнопками, а письмо проверяет методист.

Модель настраивается в `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), примеры в `.env.example`.
Банк вопросов и база знаний: `python manage.py seed_demo` (вызывает `seed_assessment`), дальше правятся в админке.

## Telegram-бот (`bot/`)

Бот на aiogram 3 работает на тех же моделях Django и вызывает те же сервисы записи.

```powershell
pip install -r bot\requirements.txt
python manage.py seed_demo --bot-token <токен от @BotFather>
python -m bot --center demo
```

Сценарий: язык (RU/UZ) → согласие на ПД → имя → возраст → для несовершеннолетних телефон и согласие родителя → диалог с ИИ-консультантом → тест уровня (+ письмо для B1+) → дни → время → до 3 групп → контакт → бронь → подтверждение. Если групп нет, заявка получает статус «Нужен менеджер». Команды: `/start`, `/my`, `/language`, `/help`.

Вернувшийся ученик (анкета уже в базе) не проходит её заново: `/start` приветствует по имени и показывает записи, любой текст отвечает ИИ — в том числе после перезапуска бота. Отменить запись можно кнопкой в «Мои записи» или попросив ИИ; в обоих случаях отменяет только нажатие «Да, отменить», а менеджер видит отмену в заметке к заявке.

Нажатия кнопок обрабатываются сразу и не ждут ИИ; если ученик ушёл из чата, пока ИИ думал, запоздавший ответ не показывается. Это проверяют `bot/test_handlers.py` и `bot/test_concurrency.py`.

Подбор под пробный урок: группа подходит, если **хотя бы одно** её занятие выпадает на выбранный день и время суток (`period`: `morning` — начало до 12:00, `day` — 12:00–17:00, `evening` — с 17:00, `any`). Бэкенд считает ближайший пробный урок (группа может уже идти) и сортирует по нему; `trial_at` проверяется при брони — это должно быть настоящее будущее занятие группы.

Демо-данные: `python manage.py seed_demo --reset` — 3 филиала, 5 курсов, 106 групп (взрослым — на каждом уровне в любой день и время суток), FAQ, банк вопросов теста.

Дни недели: 0 = понедельник … 6 = воскресенье. Бронь держится `BOOKING_HOLD_MINUTES` минут (по умолчанию 15). Истёкшие брони снимает `python manage.py release_expired_holds` (позже — Celery beat).
