"""Демо-данные для ручной проверки бота и API.

Группы генерируются из шаблонов расписания так, чтобы на каждом уровне в каждый день недели
и в каждое время суток (утро / день / вечер) нашлась группа. Даты старта считаются от сегодняшнего
дня: часть групп уже идёт (пробный урок — на ближайшем занятии), часть стартует позже.

Есть и особые случаи: детские и подростковые группы (согласие родителя), группы на 2 места
(«места закончились»), IELTS и разговорный клуб. Повторный запуск ничего не дублирует;
--reset пересоздаёт группы демо-центра, на которые ещё никто не записан.
"""

from datetime import time, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.assistant.models import FaqItem
from apps.catalog.models import Course, Group, GroupSlot, Level, Weekday
from apps.core.models import Branch, Center

MON, TUE, WED, THU, FRI, SAT, SUN = Weekday

BRANCHES = {
    "chilanzar": ("Чиланзар", "Ташкент, Чиланзар, 9-й квартал"),
    "yunusabad": ("Юнусабад", "Ташкент, Юнусабад, 4-й квартал"),
    "mirzo": ("Мирзо-Улугбек", "Ташкент, Мирзо-Улугбекский район, ул. Буюк Ипак Йули"),
}
BRANCH_ORDER = list(BRANCHES)

# название: (цена в месяц, описание, мин. возраст, макс. возраст)
COURSES = {
    "General English": (600_000, "Общий английский: грамматика, лексика, разговорная практика.", 16, None),
    "IELTS Preparation": (900_000, "Подготовка к IELTS Academic: все 4 части экзамена, пробные тесты.", 16, None),
    "Kids English": (450_000, "Английский для детей 7–12 лет в игровой форме.", 7, 12),
    "Teens English": (550_000, "Английский для подростков 13–17 лет.", 13, 17),
    "Speaking Club": (300_000, "Разговорный клуб: только практика речи, без грамматики.", 16, None),
}

DAY_NAMES = {MON: "Пн", TUE: "Вт", WED: "Ср", THU: "Чт", FRI: "Пт", SAT: "Сб", SUN: "Вс"}
MWF, TT, WEEKEND = (MON, WED, FRI), (TUE, THU), (SAT, SUN)


def t(hhmm: str) -> time:
    hours, minutes = map(int, hhmm.split(":"))
    return time(hours, minutes)


# Шаблон расписания: (дни, начало, конец, мест). Мест None — обычная вместимость курса.
GENERAL = [
    (MWF, "09:00", "10:30", None),
    (TT, "10:30", "12:00", None),
    (MWF, "14:00", "15:30", None),
    (TT, "15:30", "17:00", None),
    (MWF, "18:30", "20:00", None),
    (TT, "19:00", "20:30", None),
    (WEEKEND, "10:00", "11:30", 2),  # маленькая группа: удобно проверять «места закончились»
    (WEEKEND, "14:00", "15:30", None),
    ((SAT,), "17:00", "18:30", None),
]
# Детям и подросткам по будням утром — школа, поэтому их группы днём, вечером и в выходные.
TEMPLATES = {
    "General English": ([Level.A0, Level.A1, Level.A2, Level.B1, Level.B2, Level.C1], GENERAL, 12),
    "Kids English": ([Level.A0, Level.A1, Level.A2], [
        (MWF, "15:00", "16:00", None),
        (TT, "16:00", "17:00", None),
        (MWF, "17:00", "18:00", None),
        (WEEKEND, "11:00", "12:00", None),
    ], 10),
    "Teens English": ([Level.A0, Level.A1, Level.A2, Level.B1, Level.B2], [
        (MWF, "16:00", "17:00", None),
        (TT, "17:30", "18:30", None),
        (MWF, "18:00", "19:00", None),
        (WEEKEND, "10:00", "11:30", None),
    ], 12),
    "IELTS Preparation": ([Level.B1, Level.B2, Level.C1], [
        (TT, "08:00", "09:30", None),
        ((SAT,), "10:00", "13:00", None),
        (MWF, "19:00", "21:00", None),
        (TT, "18:00", "20:00", None),
    ], 10),
    "Speaking Club": ([Level.A2, Level.B1, Level.B2, Level.C1], [
        ((FRI,), "18:00", "19:30", 15),
        ((SUN,), "16:00", "17:30", 15),
    ], 15),
}


def period_name(start: time) -> str:
    return "утро" if start < time(12) else "день" if start < time(17) else "вечер"


def generate_groups(today):
    """Список групп: dict с полями Group и списком занятий."""
    groups = []
    for course, (levels, schedule, capacity) in TEMPLATES.items():
        for level_index, level in enumerate(levels):
            for index, (days, start, end, seats) in enumerate(schedule):
                branch = BRANCH_ORDER[(level_index + index) % len(BRANCH_ORDER)]
                start_time = t(start)
                # Чётные шаблоны уже идут три недели, нечётные стартуют в ближайшие дни.
                start_date = today - timedelta(days=21) if index % 2 == 0 else today + timedelta(days=3 + index)
                prefix = "" if course == "General English" else f"{course.split()[0]} "
                groups.append({
                    "course": course,
                    "name": f"{prefix}{level} {period_name(start_time)} "
                            f"{'/'.join(DAY_NAMES[d] for d in days)} ({BRANCHES[branch][0]})",
                    "branch": branch,
                    "level": level,
                    "capacity": seats or capacity,
                    "start_date": start_date,
                    "slots": [(day, start_time, t(end)) for day in days],
                })
    return groups


# Демо-ответы для проверки ИИ. У реального центра их заполняет администратор в админке.
FAQ = [
    ("ru", "Есть ли бесплатный пробный урок?",
     "Да, первый пробный урок бесплатный. После него можно решить, продолжать ли обучение."),
    ("ru", "Сколько длится занятие?",
     "Обычное занятие длится 90 минут, детские группы — 60 минут, IELTS по субботам — 3 часа."),
    ("ru", "Сколько человек в группе?", "В группе от 8 до 15 человек, в детских — до 10."),
    ("ru", "Как оплатить обучение?",
     "Оплата помесячно: наличными в филиале, через Click или Payme. Оплата за первый месяц — после пробного урока."),
    ("ru", "Можно ли заморозить обучение?",
     "Да, один раз за курс можно заморозить обучение на срок до 1 месяца, предупредив администратора заранее."),
    ("ru", "Что если я пропустил занятие?",
     "Материалы занятия пришлёт преподаватель. Пропущенные занятия не переносятся и не возвращаются."),
    ("ru", "Выдаёте ли вы сертификат?",
     "Да, после окончания уровня выдаётся сертификат центра. Это не международный сертификат вроде IELTS."),
    ("ru", "Есть ли скидки?", "Скидка 10% при оплате сразу за 3 месяца и 10% для второго члена семьи."),
    ("ru", "Можно ли присоединиться к группе, которая уже идёт?",
     "Да. Пробный урок можно пройти в любой группе, которая уже занимается; преподаватель поможет догнать программу."),
    ("ru", "Можно ли поменять группу?",
     "Да, если в другой группе того же уровня есть места. Запишитесь на пробный урок в новой группе и отмените старую запись."),
    ("ru", "Есть ли онлайн-занятия?", "Нет, все занятия проходят очно в филиалах центра."),
    ("ru", "Что взять на пробный урок?", "Ничего не нужно: учебные материалы на пробном уроке выдаёт преподаватель."),
    ("uz", "Bepul sinov darsi bormi?",
     "Ha, birinchi sinov darsi bepul. Shundan keyin o'qishni davom ettirish-ettirmaslikni hal qilasiz."),
    ("uz", "Dars qancha davom etadi?",
     "Oddiy dars 90 daqiqa, bolalar guruhlarida 60 daqiqa, shanba kungi IELTS — 3 soat."),
    ("uz", "Guruhda necha kishi bo'ladi?", "Guruhda 8 dan 15 gacha, bolalar guruhida 10 tagacha o'quvchi."),
    ("uz", "O'qish uchun qanday to'lanadi?",
     "To'lov oyma-oy: filialda naqd, Click yoki Payme orqali. Birinchi oy uchun to'lov sinov darsidan keyin."),
    ("uz", "O'qishni muzlatish mumkinmi?",
     "Ha, kurs davomida bir marta 1 oygacha muzlatish mumkin, administratorni oldindan ogohlantirib."),
    ("uz", "Darsni o'tkazib yuborsam nima bo'ladi?",
     "O'qituvchi dars materiallarini yuboradi. O'tkazib yuborilgan darslar ko'chirilmaydi va qaytarilmaydi."),
    ("uz", "Sertifikat berasizmi?",
     "Ha, daraja tugagach markaz sertifikati beriladi. Bu IELTS kabi xalqaro sertifikat emas."),
    ("uz", "Chegirmalar bormi?", "3 oy uchun birdaniga to'lasangiz 10% va oilaning ikkinchi a'zosi uchun 10% chegirma."),
    ("uz", "Allaqachon boshlangan guruhga qo'shilish mumkinmi?",
     "Ha. Sinov darsini allaqachon o'qiyotgan istalgan guruhda o'tish mumkin; o'qituvchi dasturga yetib olishga yordam beradi."),
    ("uz", "Guruhni almashtirish mumkinmi?",
     "Ha, agar shu darajadagi boshqa guruhda joy bo'lsa. Yangi guruhda sinov darsiga yoziling va eski yozuvni bekor qiling."),
    ("uz", "Onlayn darslar bormi?", "Yo'q, barcha darslar markaz filiallarida yuzma-yuz o'tadi."),
    ("uz", "Sinov darsiga nima olib kelish kerak?", "Hech narsa kerak emas: o'quv materiallarini o'qituvchi beradi."),
]


class Command(BaseCommand):
    help = "Создать или дополнить демо-центр: филиалы, курсы, группы, расписание, FAQ и банк вопросов теста"

    def add_arguments(self, parser):
        parser.add_argument("--bot-token", default="", help="Токен Telegram-бота для демо-центра")
        parser.add_argument(
            "--reset", action="store_true",
            help="Пересоздать группы демо-центра (группы с записями не удаляются, а закрываются для набора)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        center, _ = Center.objects.get_or_create(slug="demo", defaults={"name": "Demo Language Center"})
        if options["bot_token"]:
            center.bot_token = options["bot_token"]
            center.save(update_fields=["bot_token"])

        branches = {
            key: Branch.objects.update_or_create(center=center, name=name, defaults={"address": address})[0]
            for key, (name, address) in BRANCHES.items()
        }
        courses = {
            name: Course.objects.update_or_create(
                center=center, name=name, defaults={"price_per_month": price, "description": description}
            )[0]
            for name, (price, description, _, _) in COURSES.items()
        }

        planned = generate_groups(timezone.localdate())
        if options["reset"]:
            names = {g["name"] for g in planned}
            old = Group.objects.filter(center=center).exclude(name__in=names)
            old.filter(bookings__isnull=False).update(is_active=False)
            old.filter(bookings__isnull=True).delete()

        created = 0
        for spec in planned:
            _, _, min_age, max_age = COURSES[spec["course"]]
            group, is_new = Group.objects.get_or_create(
                course=courses[spec["course"]],
                name=spec["name"],
                defaults={
                    "branch": branches[spec["branch"]],
                    "level": spec["level"],
                    "capacity": spec["capacity"],
                    "min_age": min_age,
                    "max_age": max_age,
                    "start_date": spec["start_date"],
                },
            )
            if is_new:
                created += 1
                GroupSlot.objects.bulk_create(
                    GroupSlot(group=group, weekday=day, start_time=start, end_time=end)
                    for day, start, end in spec["slots"]
                )

        for language, question, answer in FAQ:
            FaqItem.objects.update_or_create(
                center=center, question=question, defaults={"answer": answer, "language": language}
            )
        call_command("seed_assessment", stdout=self.stdout)

        active = center.groups.filter(is_active=True)
        self.stdout.write(self.style.SUCCESS(
            f"Центр «{center.name}» (slug=demo): филиалов {center.branches.count()}, "
            f"курсов {center.courses.count()}, групп в наборе {active.count()} (новых: {created}), "
            f"вопросов в базе знаний {center.faq_items.count()}"
        ))
