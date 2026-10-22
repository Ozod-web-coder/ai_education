from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from django.conf import settings

from apps.booking.services import ANY_PERIOD
from apps.catalog.models import DayPeriod, Level

from .texts import WEEKDAYS, t

PERIODS = (*DayPeriod.values, ANY_PERIOD)


def _inline(*rows) -> InlineKeyboardMarkup:
    """Ряды кнопок из пар (текст, callback_data)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows]
    )


def _column(buttons) -> InlineKeyboardMarkup:
    return _inline(*([button] for button in buttons))


def languages() -> InlineKeyboardMarkup:
    return _inline([("🇷🇺 Русский", "lang:ru"), ("🇺🇿 O'zbekcha", "lang:uz")])


def mini_app(lang: str) -> InlineKeyboardMarkup | None:
    if not settings.MINI_APP_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "open_app"), web_app=WebAppInfo(url=settings.MINI_APP_URL))]]
    )


def consent(lang: str) -> InlineKeyboardMarkup:
    return _inline([(t(lang, "consent_yes"), "consent:yes"), (t(lang, "consent_no"), "consent:no")])


def parent_consent(lang: str) -> InlineKeyboardMarkup:
    return _inline([(t(lang, "parent_consent_yes"), "pconsent:yes")])


def levels(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in Level.choices:
        builder.button(text=t(lang, "level_A0") if value == Level.A0 else label, callback_data=f"lvl:{value}")
    builder.adjust(1, 2, 2, 1)
    return builder.as_markup()


def days(lang: str, selected: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for weekday, name in enumerate(WEEKDAYS[lang]):
        builder.button(text=f"✅ {name}" if weekday in selected else name, callback_data=f"day:{weekday}")
    builder.button(text=t(lang, "days_done"), callback_data="day:done")
    builder.adjust(4, 3, 1)
    return builder.as_markup()


def periods(lang: str) -> InlineKeyboardMarkup:
    return _inline(
        [(t(lang, f"time_{p}"), f"time:{p}") for p in DayPeriod.values],
        [(t(lang, f"time_{ANY_PERIOD}"), f"time:{ANY_PERIOD}")],
    )


def group_choices(lang: str, options) -> InlineKeyboardMarkup:
    return _column(
        [*((t(lang, "book_button", name=o.name), f"grp:{o.id}") for o in options),
         (t(lang, "change_search"), "search:again")]
    )


def change_search(lang: str) -> InlineKeyboardMarkup:
    return _inline([(t(lang, "change_search"), "search:again")])


def share_contact(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_contact"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def chat_actions(lang: str, *, test: bool = True, my: bool = False) -> InlineKeyboardMarkup:
    row = [(t(lang, "btn_test"), "act:test")] if test else []
    row.append((t(lang, "btn_groups"), "act:groups"))
    return _inline(row, *([[(t(lang, "btn_my"), "act:my")]] if my else []))


def my_bookings(lang: str, bookings) -> InlineKeyboardMarkup:
    return _column(
        [*((t(lang, "btn_cancel_booking", name=b.group.name), f"bk:ask:{b.id}") for b in bookings),
         (t(lang, "btn_groups"), "act:groups")]
    )


def booking_actions(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    return _inline([(t(lang, "confirm"), f"bk:confirm:{booking_id}"), (t(lang, "cancel"), f"bk:cancel:{booking_id}")])


def cancel_confirm(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    return _inline([(t(lang, "cancel_yes"), f"bk:cancel:{booking_id}"), (t(lang, "cancel_no"), f"bk:keep:{booking_id}")])


def test_options(question_id: int, options) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, option in enumerate(options):
        builder.button(text=option, callback_data=f"ans:{question_id}:{index}")
    builder.adjust(2)
    return builder.as_markup()
