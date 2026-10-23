import pytest

from apps.booking.models import Booking
from apps.core.models import Center, User
from apps.leads.models import Lead

LIST = "/api/c/demo/admin/leads/"


def detail(lead):
    return f"{LIST}{lead.id}/"


@pytest.fixture
def staff(center):
    return User.objects.create_user(username="admin1", telegram_id=900, is_staff=True, center=center)


@pytest.fixture
def admin_api(staff, api_for):
    return api_for(staff)


# ---------- доступ ----------


def test_anonymous_is_rejected(center, lead):
    from rest_framework.test import APIClient

    assert APIClient().get(LIST).status_code == 401


def test_student_cannot_open_admin_api(center, lead, api_for):
    assert api_for(lead.user).get(LIST).status_code == 403


def test_staff_of_other_center_is_rejected(center, lead, api_for):
    other = Center.objects.create(name="Other", slug="other")
    outsider = User.objects.create_user(username="o", telegram_id=901, is_staff=True, center=other)
    assert api_for(outsider).get(LIST).status_code == 403
    assert api_for(outsider).delete(detail(lead)).status_code == 403


def test_leads_of_other_center_are_not_visible(center, admin_api):
    other = Center.objects.create(name="Other", slug="other")
    foreign = Lead.objects.create(center=other, name="Чужой")
    assert admin_api.get(LIST).json()["count"] == 0
    assert admin_api.get(detail(foreign)).status_code == 404


# ---------- список, поиск, фильтры ----------


def test_list_has_required_fields(admin_api, make_lead, course):
    lead = make_lead(desired_course=course)
    lead.user.telegram_username = "ali_uz"
    lead.user.save()

    row = admin_api.get(LIST).json()["results"][0]
    assert row["name"] == lead.name
    assert row["phone"] == "+998901234567"
    assert row["telegram_username"] == "ali_uz"
    assert row["course"] == "General English"
    assert row["status"] == "new" and row["status_display"] == "Новая"
    assert row["created_at"]


def test_course_falls_back_to_latest_booking(admin_api, lead, make_group):
    group = make_group()
    Booking.objects.create(center=lead.center, lead=lead, group=group, status=Booking.Status.CONFIRMED)
    assert admin_api.get(LIST).json()["results"][0]["course"] == "General English"


def test_search_by_name_phone_and_username(admin_api, make_lead):
    ali = make_lead(phone="+998901111111")
    ali.name = "Алишер"
    ali.save()
    vali = make_lead(phone="+998932222222")
    vali.name = "Валиджон"
    vali.user.telegram_username = "valijon_uz"
    vali.user.save()
    vali.save()

    def names(**params):
        return [r["name"] for r in admin_api.get(LIST, params).json()["results"]]

    assert names(search="алиш") == ["Алишер"]
    assert names(search="93222") == ["Валиджон"]
    assert names(search="@valijon") == ["Валиджон"]
    assert len(names()) == 2


def test_filter_by_status_and_course(admin_api, make_lead, course, center):
    from apps.catalog.models import Course

    other_course = Course.objects.create(center=center, name="IELTS", price_per_month=900_000)
    make_lead(status=Lead.Status.NEW, desired_course=course)
    make_lead(status=Lead.Status.ATTENDED, desired_course=other_course)
    make_lead(status=Lead.Status.NO_SHOW, desired_course=other_course)

    assert admin_api.get(LIST, {"status": "attended"}).json()["count"] == 1
    assert admin_api.get(LIST, {"status": "attended,no_show"}).json()["count"] == 2
    assert admin_api.get(LIST, {"course": other_course.id}).json()["count"] == 2
    assert admin_api.get(LIST, {"course": other_course.id, "status": "no_show"}).json()["count"] == 1


def test_pagination(admin_api, make_lead):
    for _ in range(25):
        make_lead()
    page = admin_api.get(LIST).json()
    assert page["count"] == 25 and len(page["results"]) == 20 and page["next"]


def test_stats_counts_by_status(admin_api, make_lead):
    make_lead()
    make_lead()
    make_lead(status=Lead.Status.ENROLLED)
    stats = admin_api.get(f"{LIST}stats/").json()
    assert stats == {"total": 3, "by_status": {"new": 2, "enrolled": 1}}


# ---------- карточка ----------


def test_detail_shows_all_data(admin_api, make_lead, make_group):
    lead = make_lead(age=15, goal="IELTS 7", parent_name="Мама", parent_phone="+998900000000", manager_note="Звонить после 18")
    Booking.objects.create(center=lead.center, lead=lead, group=make_group(), status=Booking.Status.HELD)

    data = admin_api.get(detail(lead)).json()
    assert data["goal"] == "IELTS 7" and data["is_minor"] is True
    assert data["parent_phone"] == "+998900000000"
    assert data["manager_note"] == "Звонить после 18"
    assert data["bookings"][0]["status"] == "held"
    assert data["bookings"][0]["course"] == "General English"


# ---------- статусы, подтверждение, удаление ----------


@pytest.mark.parametrize("status", ["new", "confirmed", "attended", "no_show", "enrolled", "declined"])
def test_all_six_statuses_can_be_set(admin_api, lead, status):
    response = admin_api.patch(detail(lead), {"status": status}, format="json")
    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.status == status


def test_unknown_status_rejected(admin_api, lead):
    assert admin_api.patch(detail(lead), {"status": "banana"}, format="json").status_code == 400


def test_patch_cannot_change_read_only_fields(admin_api, lead):
    admin_api.patch(detail(lead), {"age": 99, "contacted_at": "2020-01-01T00:00:00Z"}, format="json")
    lead.refresh_from_db()
    assert lead.age == 20 and lead.contacted_at is None


def test_manager_note_and_course_update(admin_api, lead, course):
    response = admin_api.patch(detail(lead), {"manager_note": "Перезвонить", "desired_course": course.id}, format="json")
    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.manager_note == "Перезвонить" and lead.desired_course == course


def test_course_of_other_center_rejected(admin_api, lead):
    from apps.catalog.models import Course

    foreign = Course.objects.create(center=Center.objects.create(name="O", slug="o"), name="X", price_per_month=1)
    assert admin_api.patch(detail(lead), {"desired_course": foreign.id}, format="json").status_code == 400


def test_confirm_marks_contact(admin_api, lead):
    data = admin_api.post(f"{detail(lead)}confirm/").json()
    assert data["status"] == "confirmed" and data["contacted_at"]


def test_confirm_does_not_roll_back_later_status(admin_api, make_lead):
    lead = make_lead(status=Lead.Status.ENROLLED)
    data = admin_api.post(f"{detail(lead)}confirm/").json()
    assert data["status"] == "enrolled" and data["contacted_at"]


def test_setting_confirmed_status_stamps_contact_time(admin_api, lead):
    data = admin_api.patch(detail(lead), {"status": "confirmed"}, format="json").json()
    assert data["contacted_at"]


def test_delete_lead(admin_api, lead):
    assert admin_api.delete(detail(lead)).status_code == 204
    assert not Lead.objects.filter(pk=lead.pk).exists()


def test_delete_releases_held_seat(admin_api, lead, make_group):
    Booking.objects.create(center=lead.center, lead=lead, group=make_group(), status=Booking.Status.HELD)
    admin_api.delete(detail(lead))
    assert Booking.objects.count() == 0


def test_put_and_create_are_not_allowed(admin_api, lead):
    assert admin_api.put(detail(lead), {"name": "X"}, format="json").status_code == 405
    assert admin_api.post(LIST, {"name": "X"}, format="json").status_code == 405


# ---------- защита от дубликатов ----------


def test_same_phone_in_other_format_is_duplicate(admin_api, make_lead):
    first = make_lead(phone="+998 90 123-45-67")
    second = make_lead(phone="998901234567")

    rows = {r["id"]: r for r in admin_api.get(LIST).json()["results"]}
    assert rows[first.id]["duplicate_count"] == 1 and rows[second.id]["duplicate_count"] == 1

    card = admin_api.get(detail(first)).json()
    assert [d["id"] for d in card["duplicates"]] == [second.id]


def test_same_telegram_username_is_duplicate(admin_api, make_lead):
    a = make_lead(phone="+998901111111")
    b = make_lead(phone="+998932222222")
    for lead in (a, b):
        lead.user.telegram_username = "Same_User"
        lead.user.save()
    b.user.telegram_username = "same_user"
    b.user.save()
    assert admin_api.get(detail(a)).json()["duplicate_count"] == 1


def test_different_people_are_not_duplicates(admin_api, make_lead):
    a = make_lead(phone="+998901111111")
    make_lead(phone="+998932222222")
    card = admin_api.get(detail(a)).json()
    assert card["duplicate_count"] == 0 and card["duplicates"] == []


def test_empty_phone_is_never_a_duplicate(admin_api, make_lead):
    make_lead(phone="")
    b = make_lead(phone="")
    assert admin_api.get(detail(b)).json()["duplicate_count"] == 0


def test_duplicates_do_not_cross_centers(admin_api, make_lead):
    a = make_lead()
    other = Center.objects.create(name="Other", slug="other")
    Lead.objects.create(center=other, name="Тот же номер", phone=a.phone)
    assert admin_api.get(detail(a)).json()["duplicate_count"] == 0


# ---------- сквозной сценарий Mini App: вход по initData → работа с заявками ----------


def _login_via_telegram(client, center, tg_id):
    from apps.core.tests import build_init_data

    init_data = build_init_data(user={"id": tg_id, "first_name": "Admin", "username": "admin_tg"})
    response = client.post("/api/auth/telegram/", {"center": center.slug, "init_data": init_data}, format="json")
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")


def test_staff_logs_in_with_telegram_and_manages_leads(center, lead):
    from rest_framework.test import APIClient

    User.objects.create_user(username="boss", telegram_id=777, is_staff=True, center=center)
    client = APIClient()
    _login_via_telegram(client, center, 777)

    assert client.get(LIST).json()["count"] == 1
    assert client.post(f"{detail(lead)}confirm/").json()["status"] == "confirmed"
    assert client.delete(detail(lead)).status_code == 204


def test_unknown_telegram_user_gets_403_not_data(center, lead):
    from rest_framework.test import APIClient

    client = APIClient()
    _login_via_telegram(client, center, 888)  # аккаунт создаётся, но сотрудником не является
    assert client.get(LIST).status_code == 403
