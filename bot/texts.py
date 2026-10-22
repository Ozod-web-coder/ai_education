from datetime import date, datetime
from html import escape

from django.utils import timezone

LANGUAGES = ("ru", "uz")

WEEKDAYS = {
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
    "uz": ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"),
}

TEXTS = {
    "ru": {
        "choose_language": "Выберите язык / Tilni tanlang",
        "welcome": "Здравствуйте! Я помощник учебного центра «{center}». Помогу подобрать группу по уровню и удобному времени и записать вас на занятия.",
        "open_app": "Открыть приложение",
        "consent_ask": "Чтобы подобрать группу, мне нужно сохранить ваши ответы: имя ученика, возраст, уровень, телефон и ваш username в Telegram. Вы согласны на обработку персональных данных?",
        "consent_yes": "Согласен(на)",
        "consent_no": "Нет",
        "consent_declined": "Без согласия я не могу сохранить заявку. Если передумаете — нажмите /start.",
        "ask_name": "Как зовут ученика? Напишите только имя.",
        "bad_name": "Напишите имя буквами, например: Азиз.",
        "ask_age": "Сколько лет ученику? Напишите число.",
        "bad_age": "Напишите возраст числом, например 17.",
        "ask_parent_phone": "Ученику меньше 18 лет, поэтому нужен телефон родителя или законного представителя. Напишите номер, например +998901234567.",
        "bad_phone": "Не похоже на номер телефона. Пример: +998901234567.",
        "parent_consent_ask": "Подтвердите, что родитель согласен на обработку данных ребёнка и на запись на занятия.",
        "parent_consent_yes": "Родитель согласен",
        "ask_level": "Какой у вас сейчас уровень английского?",
        "level_A0": "С нуля / не знаю",
        "ask_days": "В какой день вам удобно прийти на пробный урок? Отметьте один или несколько дней и нажмите «Готово».",
        "days_done": "Готово",
        "days_empty": "Отметьте хотя бы один день.",
        "ask_time": "В какое время суток вам удобно?",
        "time_morning": "🌅 Утром",
        "time_day": "☀️ Днём",
        "time_evening": "🌙 Вечером",
        "time_any": "Любое время",
        "found": "Подходящие группы:",
        "group_card": "<b>{name}</b>\n{course} · {branch}\n🎯 Пробный урок: <b>{trial}</b>\n🗓 Расписание группы: {schedule}\n💺 Свободных мест: {free}\n💰 {price} сум/мес",
        "book_button": "Записаться: {name}",
        "not_found": "В выбранные дни и время суток нет групп со свободными местами. Я передал заявку менеджеру — он свяжется с вами. Можно выбрать другие дни или время.",
        "change_search": "Изменить дни и время",
        "ask_contact": "Отправьте ваш номер телефона кнопкой ниже — по нему центр свяжется с вами.",
        "share_contact": "📱 Отправить номер",
        "not_own_contact": "Пожалуйста, отправьте свой номер кнопкой ниже.",
        "contact_saved": "Спасибо, номер сохранён.",
        "held": "Место в группе «{name}» забронировано на {minutes} мин.\nПробный урок: <b>{trial}</b>.\nПодтвердите запись.",
        "confirm": "Подтвердить запись",
        "cancel": "Отменить",
        "confirmed": "Готово! Вы записаны на пробный урок в группе «{name}»: <b>{trial}</b>. Ждём вас!",
        "cancelled": "Запись отменена.",
        "my_empty": "У вас пока нет записей. Нажмите /start, чтобы подобрать группу.",
        "my_title": "Ваши записи:",
        "my_item": "• {name} — {status}",
        "status_held": "ждёт подтверждения",
        "status_confirmed": "подтверждена",
        "status_waitlist": "лист ожидания",
        "status_cancelled": "отменена",
        "status_expired": "бронь истекла",
        "help": "/start — подобрать группу\n/my — мои записи\n/language — сменить язык",
        "unknown": "Не понял вас. Нажмите /start, чтобы подобрать группу, или /help.",
        "err_GroupFull": "В этой группе только что закончились места. Выберите другую группу.",
        "err_HoldExpired": "Время брони истекло. Подберите группу заново: /start",
        "err_GroupNotFound": "Группа больше не принимает учеников. Выберите другую.",
        "err_AgeMismatch": "Эта группа не подходит по возрасту.",
        "err_MissingContact": "Нужен номер телефона.",
        "err_InvalidTransition": "Эту запись уже нельзя изменить.",
        "err_BookingNotFound": "Запись не найдена.",
        "err_unknown": "Что-то пошло не так. Попробуйте ещё раз: /start",
        "chat_intro": "Спасибо, {name}! Я ИИ-помощник центра. Спросите меня о курсах, ценах, филиалах и условиях обучения — или сразу пройдите тест уровня.",
        "ai_unavailable": "ИИ-помощник сейчас недоступен. Вы можете пройти тест уровня или подобрать группу кнопками ниже.",
        "btn_test": "📝 Тест уровня",
        "btn_groups": "📅 Подобрать группу",
        "test_intro": "Начинаем тест уровня английского. Выберите правильный вариант в каждом вопросе.",
        "test_question": "<b>Вопрос {number}</b>\n\n{text}",
        "test_answered": "{text}\n\nВаш ответ: <b>{answer}</b>",
        "test_question_closed": "Этот вопрос уже закрыт.",
        "test_unavailable": "Тест сейчас недоступен. Подберём группу по уровню, который вы назовёте.",
        "writing_task": "Последнее задание — напишите текст на английском (не меньше {min_words} слов):\n\n<i>{prompt}</i>",
        "writing_too_short": "Получилось {words} слов, нужно не меньше {min_words}. Допишите текст и отправьте его целиком.",
        "writing_checking": "Проверяю текст, это займёт до минуты…",
        "test_result": "Ваш уровень английского: <b>{level}</b>.",
        "test_review": "Методист центра дополнительно проверит результат.",
        "test_next": "Теперь можно подобрать группу по уровню и удобному времени.",
        "welcome_back": "С возвращением, {name}! Задайте вопрос — я отвечу.",
        "welcome_back_bookings": "С возвращением, {name}! Ваши записи:",
        "booking_card": "<b>{name}</b> — {status}\n{course} · {branch}\n🎯 Пробный урок: {trial}\n🗓 Расписание группы: {schedule}",
        "btn_my": "📋 Мои записи",
        "btn_cancel_booking": "❌ Отменить: {name}",
        "cancel_confirm": "Отменить запись в группу «{name}» (пробный урок {start})?",
        "err_InvalidTrialLesson": "Расписание группы изменилось. Подберите время пробного урока заново.",
        "cancel_yes": "Да, отменить",
        "cancel_no": "Нет, оставить",
        "kept": "Хорошо, запись сохранена.",
        "ai_busy": "Секунду, отвечаю на предыдущее сообщение…",
    },
    "uz": {
        "choose_language": "Выберите язык / Tilni tanlang",
        "welcome": "Assalomu alaykum! Men «{center}» o'quv markazining yordamchisiman. Darajangiz va qulay vaqtingizga mos guruhni tanlab, darsga yozib qo'yaman.",
        "open_app": "Ilovani ochish",
        "consent_ask": "Guruh tanlash uchun javoblaringizni saqlashim kerak: o'quvchining ismi, yoshi, darajasi, telefon raqami va Telegram username. Shaxsiy ma'lumotlaringizni qayta ishlashga rozimisiz?",
        "consent_yes": "Roziman",
        "consent_no": "Yo'q",
        "consent_declined": "Roziliksiz arizani saqlay olmayman. Fikringiz o'zgarsa, /start ni bosing.",
        "ask_name": "O'quvchining ismi nima? Faqat ismni yozing.",
        "bad_name": "Ismni harflar bilan yozing, masalan: Aziz.",
        "ask_age": "O'quvchi necha yoshda? Raqam bilan yozing.",
        "bad_age": "Yoshni raqam bilan yozing, masalan 17.",
        "ask_parent_phone": "O'quvchi 18 yoshga to'lmagan, shuning uchun ota-ona yoki qonuniy vakilning telefon raqami kerak. Raqamni yozing, masalan +998901234567.",
        "bad_phone": "Bu telefon raqamiga o'xshamaydi. Misol: +998901234567.",
        "parent_consent_ask": "Ota-ona bolaning ma'lumotlarini qayta ishlashga va darsga yozilishga rozi ekanini tasdiqlang.",
        "parent_consent_yes": "Ota-ona rozi",
        "ask_level": "Hozir ingliz tilini qaysi darajada bilasiz?",
        "level_A0": "Noldan / bilmayman",
        "ask_days": "Sinov darsiga qaysi kuni kelish qulay? Bir yoki bir nechta kunni belgilang va «Tayyor» ni bosing.",
        "days_done": "Tayyor",
        "days_empty": "Kamida bitta kunni belgilang.",
        "ask_time": "Kunning qaysi vaqti sizga qulay?",
        "time_morning": "🌅 Ertalab",
        "time_day": "☀️ Kunduzi",
        "time_evening": "🌙 Kechqurun",
        "time_any": "Istalgan vaqt",
        "found": "Mos guruhlar:",
        "group_card": "<b>{name}</b>\n{course} · {branch}\n🎯 Sinov darsi: <b>{trial}</b>\n🗓 Guruh jadvali: {schedule}\n💺 Bo'sh joylar: {free}\n💰 {price} so'm/oy",
        "book_button": "Yozilish: {name}",
        "not_found": "Tanlangan kunlar va vaqtda bo'sh joyli guruh yo'q. Arizangizni menejerga yubordim — u siz bilan bog'lanadi. Boshqa kun yoki vaqtni tanlashingiz mumkin.",
        "change_search": "Kun va vaqtni o'zgartirish",
        "ask_contact": "Telefon raqamingizni pastdagi tugma orqali yuboring — markaz siz bilan shu raqam orqali bog'lanadi.",
        "share_contact": "📱 Raqamni yuborish",
        "not_own_contact": "Iltimos, o'z raqamingizni pastdagi tugma orqali yuboring.",
        "contact_saved": "Rahmat, raqam saqlandi.",
        "held": "«{name}» guruhida joy {minutes} daqiqaga band qilindi.\nSinov darsi: <b>{trial}</b>.\nYozilishni tasdiqlang.",
        "confirm": "Yozilishni tasdiqlash",
        "cancel": "Bekor qilish",
        "confirmed": "Tayyor! Siz «{name}» guruhidagi sinov darsiga yozildingiz: <b>{trial}</b>. Sizni kutamiz!",
        "cancelled": "Yozilish bekor qilindi.",
        "my_empty": "Sizda hali yozuvlar yo'q. Guruh tanlash uchun /start ni bosing.",
        "my_title": "Sizning yozuvlaringiz:",
        "my_item": "• {name} — {status}",
        "status_held": "tasdiqlash kutilmoqda",
        "status_confirmed": "tasdiqlangan",
        "status_waitlist": "kutish ro'yxatida",
        "status_cancelled": "bekor qilingan",
        "status_expired": "band qilish muddati tugagan",
        "help": "/start — guruh tanlash\n/my — mening yozuvlarim\n/language — tilni o'zgartirish",
        "unknown": "Tushunmadim. Guruh tanlash uchun /start ni bosing yoki /help.",
        "err_GroupFull": "Bu guruhda hozirgina joylar tugadi. Boshqa guruhni tanlang.",
        "err_HoldExpired": "Band qilish muddati tugadi. Guruhni qaytadan tanlang: /start",
        "err_GroupNotFound": "Guruh endi o'quvchi qabul qilmaydi. Boshqasini tanlang.",
        "err_AgeMismatch": "Bu guruh yoshingizga mos emas.",
        "err_MissingContact": "Telefon raqami kerak.",
        "err_InvalidTransition": "Bu yozuvni endi o'zgartirib bo'lmaydi.",
        "err_BookingNotFound": "Yozuv topilmadi.",
        "err_unknown": "Nimadir xato ketdi. Qaytadan urinib ko'ring: /start",
        "chat_intro": "Rahmat, {name}! Men markazning sun'iy intellekt yordamchisiman. Kurslar, narxlar, filiallar va o'qish shartlari haqida so'rang — yoki darhol daraja testini topshiring.",
        "ai_unavailable": "Sun'iy intellekt yordamchisi hozir ishlamayapti. Pastdagi tugmalar orqali daraja testini topshirishingiz yoki guruh tanlashingiz mumkin.",
        "btn_test": "📝 Daraja testi",
        "btn_groups": "📅 Guruh tanlash",
        "test_intro": "Ingliz tili daraja testini boshlaymiz. Har bir savolda to'g'ri variantni tanlang.",
        "test_question": "<b>{number}-savol</b>\n\n{text}",
        "test_answered": "{text}\n\nSizning javobingiz: <b>{answer}</b>",
        "test_question_closed": "Bu savol allaqachon yopilgan.",
        "test_unavailable": "Test hozir mavjud emas. Siz aytgan daraja bo'yicha guruh tanlaymiz.",
        "writing_task": "Oxirgi topshiriq — ingliz tilida matn yozing (kamida {min_words} so'z):\n\n<i>{prompt}</i>",
        "writing_too_short": "{words} so'z bo'ldi, kamida {min_words} so'z kerak. Matnni to'ldirib, to'liq yuboring.",
        "writing_checking": "Matnni tekshiryapman, bu bir daqiqagacha vaqt oladi…",
        "test_result": "Ingliz tili darajangiz: <b>{level}</b>.",
        "test_review": "Markaz metodisti natijani qo'shimcha tekshiradi.",
        "test_next": "Endi darajangiz va qulay vaqtingizga mos guruh tanlash mumkin.",
        "welcome_back": "Qaytganingiz bilan, {name}! Savol bering — javob beraman.",
        "welcome_back_bookings": "Qaytganingiz bilan, {name}! Sizning yozuvlaringiz:",
        "booking_card": "<b>{name}</b> — {status}\n{course} · {branch}\n🎯 Sinov darsi: {trial}\n🗓 Guruh jadvali: {schedule}",
        "btn_my": "📋 Mening yozuvlarim",
        "btn_cancel_booking": "❌ Bekor qilish: {name}",
        "cancel_confirm": "«{name}» guruhiga yozilishni bekor qilasizmi (sinov darsi {start})?",
        "err_InvalidTrialLesson": "Guruh jadvali o'zgardi. Sinov darsi vaqtini qaytadan tanlang.",
        "cancel_yes": "Ha, bekor qilish",
        "cancel_no": "Yo'q, qoldirish",
        "kept": "Yaxshi, yozuv saqlandi.",
        "ai_busy": "Bir soniya, oldingi xabaringizga javob beryapman…",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS["ru"])[key]
    return text.format(**kwargs) if kwargs else text


def error_text(lang: str, exc: Exception) -> str:
    key = f"err_{type(exc).__name__}"
    return t(lang, key if key in TEXTS["ru"] else "err_unknown")


def format_schedule(lang: str, slots) -> str:
    """((1, 18:30, 20:00), (3, 18:30, 20:00)) → "Вт, Чт 18:30–20:00"."""
    names = WEEKDAYS.get(lang, WEEKDAYS["ru"])
    times = {(start, end) for _, start, end in slots}
    if len(times) == 1:
        start, end = times.pop()
        days = ", ".join(names[weekday] for weekday, _, _ in slots)
        return f"{days} {start:%H:%M}–{end:%H:%M}"
    return "; ".join(f"{names[weekday]} {start:%H:%M}–{end:%H:%M}" for weekday, start, end in slots)


def format_price(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_date(value: date) -> str:
    return f"{value:%d.%m.%Y}"


def format_trial(lang: str, trial_at: datetime | None, fallback: date | None = None) -> str:
    """Пробный урок: «Вт, 03.11.2026, 18:30». Для старых записей без даты — дата старта группы."""
    if trial_at is None:
        return format_date(fallback) if fallback else "—"
    local = timezone.localtime(trial_at)
    return f"{WEEKDAYS.get(lang, WEEKDAYS['ru'])[local.weekday()]}, {local:%d.%m.%Y}, {local:%H:%M}"


def _group_fields(lang: str, group) -> dict:
    return {
        "name": escape(group.name),
        "course": escape(group.course),
        "branch": escape(group.branch),
        "schedule": format_schedule(lang, group.slots),
    }


def group_card(lang: str, option) -> str:
    return t(
        lang,
        "group_card",
        **_group_fields(lang, option),
        trial=format_trial(lang, option.trial_at, option.start_date),
        free=option.free_seats,
        price=format_price(option.price),
    )


def booking_card(lang: str, booking) -> str:
    return t(
        lang,
        "booking_card",
        **_group_fields(lang, booking.group),
        status=t(lang, f"status_{booking.status}"),
        trial=format_trial(lang, booking.trial_at, booking.group.start_date),
    )
