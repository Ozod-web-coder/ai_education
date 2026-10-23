# AI Education — backend

Django + DRF API для Telegram Mini App: анкета ученика, подбор группы по уровню и расписанию, запись без двойного бронирования.

## Запуск

Нужен Python 3.12 или 3.13.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # если .env ещё нет, и задайте SECRET_KEY
python manage.py makemigrations core catalog leads booking
python manage.py migrate
python manage.py seed_demo      # демо-центр slug=demo
python manage.py createsuperuser
python manage.py runserver
pytest
```

- Админка: http://127.0.0.1:8000/admin/
- Документация API (Swagger): http://127.0.0.1:8000/api/docs/

## База данных

Пока `DATABASE_URL` не задан, используется SQLite. Для PostgreSQL добавьте в `.env`:

```
DATABASE_URL=postgres://postgres:ПАРОЛЬ@localhost:5432/ai_education
```

### Supabase

В Supabase откройте проект → **Connect** → вкладка **Session pooler** и скопируйте строку. Она выглядит так:

```
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<ПАРОЛЬ>@aws-0-<РЕГИОН>.pooler.supabase.com:5432/postgres?sslmode=require
```

- **Не берите «Direct connection»** (`db.<PROJECT_REF>.supabase.co`): он работает только по IPv6. Без IPv6 (домашний интернет, многие хостинги) будет ошибка вроде `could not translate host name` или `Network is unreachable`. Session pooler работает по IPv4.
- Логин у pooler с суффиксом: `postgres.<PROJECT_REF>`, а не просто `postgres`.
- Порт `5432` (Session pooler). Порт `6543` (Transaction pooler) для Django не подходит без доп. настроек.
- Спецсимволы в пароле кодируйте: `@` → `%40`, `&` → `%26`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`, `%` → `%25`. Или задайте в Supabase пароль только из букв и цифр.
- Строка с паролем лежит только в `.env`, он в `.gitignore`. В репозиторий и в чаты её не отправляйте.

После подключения создайте таблицы: `python manage.py migrate`, затем `python manage.py createsuperuser`.

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
