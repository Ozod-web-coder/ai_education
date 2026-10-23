import io
import urllib.error
from unittest.mock import patch

import pytest

from apps.booking.models import Booking
from apps.booking.services import taken_seats
from apps.core import notify
from apps.core.models import User
from apps.leads.models import Lead
from apps.leads.notifications import declined_message

LIST = "/api/c/demo/admin/leads/"
SEND = "apps.leads.services.notify.send_message"


def detail(lead):
    return f"{LIST}{lead.id}/"


@pytest.fixture
def admin_api(center, api_for):
    staff = User.objects.create_user(username="admin1", telegram_id=900_000, is_staff=True, center=center)
    return api_for(staff)


@pytest.fixture
def with_phone(center):
    center.admin_phone = "+998 71 200 00 00"
    center.save()


def decline(api, lead):
    return api.patch(detail(lead), {"status": "declined"}, format="json")


# ---------- уведомление ученику ----------


def test_declining_sends_notification_to_student(admin_api, make_lead, with_phone, center):
    lead = make_lead()
    with patch(SEND, return_value=notify.SENT) as send:
        response = decline(admin_api, lead)

    assert response.status_code == 200
    assert response.json()["student_notification"] == {"sent": True, "reason": "sent"}
    token, chat_id, text = send.call_args.args
    assert token == center.bot_token and chat_id == lead.user.telegram_id
    assert "запись на пробный урок" in text and "отменена" in text
    assert "сам отказался" in text
    assert "+998 71 200 00 00" in text  # телефон администрации
    assert "по ошибке или это были не вы" in text


def test_message_is_in_students_language(admin_api, make_lead, with_phone):
    lead = make_lead()
    lead.user.language = "uz"
    lead.user.save()
    with patch(SEND, return_value=notify.SENT) as send:
        decline(admin_api, lead)
    text = send.call_args.args[2]
    assert "Sinov darsiga" in text and "+998 71 200 00 00" in text
    assert "пробный" not in text


def test_message_without_admin_phone_points_to_center(center):
    text = declined_message("ru", center_name="Demo", admin_phone="  ", group_names=[])
    assert "администрацию центра «Demo»" in text and "телефону" not in text


def test_message_escapes_html_in_group_name():
    text = declined_message("ru", center_name="C", admin_phone="1", group_names=["<b>X</b> & Y"])
    assert "<b>X</b>" not in text and "&lt;b&gt;X&lt;/b&gt; &amp; Y" in text


def test_group_names_are_listed(admin_api, make_lead, make_group, with_phone):
    lead = make_lead()
    Booking.objects.create(center=lead.center, lead=lead, group=make_group(name="B1 вечер"), status=Booking.Status.CONFIRMED)
    with patch(SEND, return_value=notify.SENT) as send:
        decline(admin_api, lead)
    assert "в группе «B1 вечер»" in send.call_args.args[2]


# ---------- отмена записей ----------


def test_declining_cancels_open_bookings_and_frees_seats(admin_api, make_lead, make_group):
    group = make_group(capacity=2)
    lead = make_lead()
    held = Booking.objects.create(center=lead.center, lead=lead, group=group, status=Booking.Status.HELD)
    other = make_lead()
    Booking.objects.create(center=lead.center, lead=other, group=group, status=Booking.Status.CONFIRMED)
    from django.utils import timezone

    held.expires_at = timezone.now() + timezone.timedelta(minutes=10)
    held.save()
    assert taken_seats(group) == 2

    with patch(SEND, return_value=notify.SENT):
        decline(admin_api, lead)

    held.refresh_from_db()
    assert held.status == Booking.Status.CANCELLED
    assert taken_seats(group) == 1  # место освободилось, чужая запись не тронута


def test_declining_keeps_declined_status_and_logs_admin_note(admin_api, make_lead, make_group):
    lead = make_lead(manager_note="Просил позвонить")
    Booking.objects.create(center=lead.center, lead=lead, group=make_group(), status=Booking.Status.CONFIRMED)
    with patch(SEND, return_value=notify.SENT):
        decline(admin_api, lead)

    lead.refresh_from_db()
    assert lead.status == Lead.Status.DECLINED
    assert lead.manager_note.startswith("Просил позвонить")
    assert "администратор отметил отказ" in lead.manager_note and "ученик уведомлён" in lead.manager_note
    assert "ученик отменил запись" not in lead.manager_note  # это не отмена самим учеником


def test_student_cancel_still_leaves_old_note(make_lead, make_group):
    from apps.booking import services

    lead = make_lead()
    booking = Booking.objects.create(center=lead.center, lead=lead, group=make_group(), status=Booking.Status.CONFIRMED)
    services.cancel_booking(booking)
    lead.refresh_from_db()
    assert "ученик отменил запись" in lead.manager_note


# ---------- когда не уведомляем ----------


@pytest.mark.parametrize("status", ["new", "confirmed", "attended", "no_show", "enrolled"])
def test_other_statuses_do_not_notify(admin_api, make_lead, status):
    lead = make_lead()
    with patch(SEND) as send:
        response = admin_api.patch(detail(lead), {"status": status}, format="json")
    send.assert_not_called()
    assert "student_notification" not in response.json()


def test_no_repeat_notification_when_already_declined(admin_api, make_lead):
    lead = make_lead()
    with patch(SEND, return_value=notify.SENT) as send:
        decline(admin_api, lead)
        decline(admin_api, lead)
        admin_api.patch(detail(lead), {"manager_note": "ещё заметка"}, format="json")
    assert send.call_count == 1


def test_notifies_again_after_status_was_restored(admin_api, make_lead):
    lead = make_lead()
    with patch(SEND, return_value=notify.SENT) as send:
        decline(admin_api, lead)
        admin_api.patch(detail(lead), {"status": "new"}, format="json")
        decline(admin_api, lead)
    assert send.call_count == 2


def test_confirm_action_never_notifies(admin_api, make_lead):
    lead = make_lead()
    with patch(SEND) as send:
        admin_api.post(f"{detail(lead)}confirm/")
    send.assert_not_called()


# ---------- сбои не ломают смену статуса ----------


@pytest.mark.parametrize("result", [notify.BLOCKED, notify.ERROR, notify.NO_BOT])
def test_delivery_failure_is_reported_but_status_is_saved(admin_api, make_lead, result):
    lead = make_lead()
    with patch(SEND, return_value=result):
        response = decline(admin_api, lead)
    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    assert response.json()["student_notification"] == {"sent": False, "reason": result}
    lead.refresh_from_db()
    assert f"уведомление не доставлено ({result})" in lead.manager_note


def test_student_without_telegram_gets_no_message(admin_api, center):
    lead = Lead.objects.create(center=center, name="Без Telegram", phone="+998901112233")
    with patch(SEND) as send:
        response = decline(admin_api, lead)
    send.assert_not_called()
    assert response.json()["student_notification"] == {"sent": False, "reason": "no_telegram"}


# ---------- отправка в Telegram ----------


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_message_posts_to_bot_api():
    with patch("apps.core.notify.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        assert notify.send_message("123:ABC", 555, "Привет") == notify.SENT
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert b'"chat_id": 555' in request.data and b"parse_mode" in request.data
    assert urlopen.call_args.kwargs["timeout"] == notify.TIMEOUT_SECONDS


def test_send_message_without_token_does_nothing():
    with patch("apps.core.notify.urllib.request.urlopen") as urlopen:
        assert notify.send_message("", 555, "x") == notify.NO_BOT
    urlopen.assert_not_called()


@pytest.mark.parametrize("code, expected", [(403, notify.BLOCKED), (400, notify.BLOCKED), (500, notify.ERROR), (429, notify.ERROR)])
def test_send_message_maps_http_errors(code, expected):
    error = urllib.error.HTTPError("https://api.telegram.org", code, "err", {}, io.BytesIO(b"{}"))
    with patch("apps.core.notify.urllib.request.urlopen", side_effect=error):
        assert notify.send_message("123:ABC", 555, "x") == expected


@pytest.mark.parametrize("error", [urllib.error.URLError("down"), TimeoutError(), OSError("boom")])
def test_send_message_survives_network_errors(error):
    with patch("apps.core.notify.urllib.request.urlopen", side_effect=error):
        assert notify.send_message("123:ABC", 555, "x") == notify.ERROR
