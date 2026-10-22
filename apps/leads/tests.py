from apps.core.models import User
from apps.leads.models import Lead

URL = "/api/c/demo/lead/"


def test_get_before_create_is_404(center, api_for):
    user = User.objects.create_user(username="u1", telegram_id=1)
    assert api_for(user).get(URL).status_code == 404


def test_create_requires_personal_data_consent(center, api_for):
    user = User.objects.create_user(username="u1", telegram_id=1)
    response = api_for(user).put(URL, {"name": "Ali", "age": 20}, format="json")
    assert response.status_code == 400
    assert "consent_personal_data" in response.json()


def test_minor_requires_parent(center, api_for):
    user = User.objects.create_user(username="u1", telegram_id=1)
    response = api_for(user).put(URL, {"age": 15, "consent_personal_data": True}, format="json")
    assert response.status_code == 400
    assert {"parent_phone", "consent_parent"} <= response.json().keys()


def test_create_then_partial_update(center, branch, api_for):
    user = User.objects.create_user(username="u1", telegram_id=1)
    client = api_for(user)
    created = client.put(
        URL, {"age": 20, "goal": "IELTS 7.0", "preferred_branch": branch.id, "consent_personal_data": True}, format="json"
    )
    assert created.status_code == 201
    assert created.json()["personal_data_consent_at"]

    updated = client.patch(URL, {"phone": "+998901234567"}, format="json")
    assert updated.status_code == 200
    lead = Lead.objects.get(user=user)
    assert lead.phone == "+998901234567" and lead.goal == "IELTS 7.0"


def test_branch_of_other_center_rejected(center, api_for):
    from apps.core.models import Branch, Center

    other = Center.objects.create(name="Other", slug="other")
    foreign_branch = Branch.objects.create(center=other, name="Чужой")
    user = User.objects.create_user(username="u1", telegram_id=1)
    response = api_for(user).put(
        URL, {"preferred_branch": foreign_branch.id, "consent_personal_data": True}, format="json"
    )
    assert response.status_code == 400
