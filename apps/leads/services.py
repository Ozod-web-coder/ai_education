from django.db import transaction
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Booking
from apps.core import notify

from .models import Lead
from .notifications import declined_message

NO_TELEGRAM = "no_telegram"
OPEN_BOOKING_STATUSES = (Booking.Status.HELD, Booking.Status.CONFIRMED, Booking.Status.WAITLIST)


def decline_lead(lead: Lead) -> dict:
    """Администратор отметил «Отказался»: отменяем действующие записи и сообщаем ученику в бот.

    Статус заявки уже сохранён вызывающим кодом. Возвращает {"sent": bool, "reason": str},
    чтобы Mini App показал администратору, дошло ли сообщение. Сбой Telegram статус не откатывает.
    """
    with transaction.atomic():
        bookings = list(lead.bookings.filter(status__in=OPEN_BOOKING_STATUSES).select_related("group"))
        for booking in bookings:
            booking_services.cancel_booking(booking, by_student=False)
    group_names = [booking.group.name for booking in bookings]

    center = lead.center
    user = lead.user
    if user is None or not user.telegram_id:
        result = NO_TELEGRAM
    else:
        text = declined_message(
            user.language,
            center_name=center.name,
            admin_phone=center.admin_phone,
            group_names=group_names,
        )
        result = notify.send_message(center.bot_token, user.telegram_id, text)

    # Запись в заметке: менеджеры видят, что произошло и дошло ли уведомление.
    outcome = "ученик уведомлён в Telegram" if result == notify.SENT else f"уведомление не доставлено ({result})"
    cancelled = f", отменены записи: {', '.join(group_names)}" if group_names else ""
    note = f"{timezone.localdate():%d.%m.%Y}: администратор отметил отказ{cancelled}; {outcome}"
    lead.manager_note = f"{lead.manager_note}\n{note}".strip()[:5000]
    lead.save(update_fields=["manager_note", "updated_at"])

    return {"sent": result == notify.SENT, "reason": result}
