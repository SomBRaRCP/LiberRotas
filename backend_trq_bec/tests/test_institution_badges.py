from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tests import test_server_api as api_helpers
from trq_bec.server.institution_badges import allocate_by_badges
from trq_bec.server.models import InstitutionBadgePolicy


@pytest.mark.parametrize("values", [(20, 30, 40), (-1, 31, 70), (101, 0, -1), (True, 29, 70), (20.5, 29.5, 50)])
def test_invalid_policy(values):
    with pytest.raises(ValidationError):
        InstitutionBadgePolicy(green_percent=values[0], yellow_percent=values[1], red_percent=values[2])


def test_distribution_conserves_every_cent_and_is_deterministic():
    policy = InstitutionBadgePolicy(green_percent=20, yellow_percent=30, red_percent=50)
    members = {"r2": "RED", "g": "GREEN", "r1": "RED", "y": "YELLOW"}
    assert dict(allocate_by_badges(100_000, policy, members)) == {"r1": 25_000, "r2": 25_000, "y": 30_000, "g": 20_000}
    for budget in range(1, 301):
        result = dict(allocate_by_badges(budget, policy, members))
        assert sum(result.values()) == budget
        assert abs(result["r1"] - result["r2"]) <= 1
        assert all(amount >= 0 for amount in result.values())
        assert result == dict(allocate_by_badges(budget, policy, dict(reversed(list(members.items())))))


def test_missing_classification_and_empty_categories_are_not_silently_redistributed():
    policy = InstitutionBadgePolicy(green_percent=20, yellow_percent=30, red_percent=50)
    with pytest.raises(ValueError, match="POLICY_REQUIRED"):
        allocate_by_badges(100, None, {"a": "RED"})
    with pytest.raises(ValueError, match="CLASSIFICATION_REQUIRED"):
        allocate_by_badges(100, policy, {"a": None})
    with pytest.raises(ValueError, match="EMPTY_CATEGORY"):
        allocate_by_badges(100, policy, {"a": "RED"})
    only_red = InstitutionBadgePolicy(green_percent=0, yellow_percent=0, red_percent=100)
    assert dict(allocate_by_badges(101, only_red, {"a": "RED", "b": "RED", "g": "GREEN"})) == {"a": 51, "b": 50, "g": 0}


@pytest.fixture
def api():
    case = api_helpers.ServerApiTests()
    case.setUp()
    try:
        yield case
    finally:
        case.tearDown()


def test_badges_authorization_validation_distribution_and_snapshot(api):
    owner = api.headers("institution-token")
    other = api.headers("institution-other-token")
    seller_headers = api.headers("entre-token")
    group = api.client.post("/v1/institution/groups", headers=owner, json={"name": "Grupo Selos"}).json()
    group_url = f"/v1/institution/groups/{group['group_id']}"
    assert group["badge_policy"] is None
    policy = {"green_percent": 0, "yellow_percent": 30, "red_percent": 70}
    assert api.client.put(group_url + "/badge-policy", headers=other, json=policy).status_code == 404
    assert api.client.put(group_url + "/badge-policy", headers=seller_headers, json=policy).status_code == 403
    assert api.client.put(group_url + "/badge-policy", headers=owner, json={**policy, "red_percent": 60}).status_code == 422
    saved = api.client.put(group_url + "/badge-policy", headers=owner, json=policy)
    assert saved.status_code == 200, saved.text
    assert saved.json()["badge_policy"] == policy

    memberships = []
    for token, name, badge in [("entre-token", "Feirante Selo Vermelho", "RED"), ("entre-other-token", "Feirante Selo Amarelo", "YELLOW")]:
        assert api.save_public_profile(token, name).status_code == 200
        member = api.client.post(group_url + "/invitations", headers=owner, json={"seller_name": name}).json()
        badge_url = group_url + f"/members/{member['membership_id']}/badge"
        assert member["support_badge"] is None
        assert api.client.put(badge_url, headers=owner, json={"support_badge": badge}).status_code == 409
        assert api.client.post(f"/v1/entrepreneur/institution-invitations/{member['membership_id']}/accept", headers=api.headers(token)).status_code == 200
        assert api.client.put(badge_url, headers=other, json={"support_badge": badge}).status_code == 404
        assert api.client.put(badge_url, headers=api.headers(token), json={"support_badge": badge}).status_code == 403
        assert api.client.put(badge_url, headers=owner, json={"support_badge": "BLUE"}).status_code == 422
        classified = api.client.put(badge_url, headers=owner, json={"support_badge": badge})
        assert classified.status_code == 200, classified.text
        assert classified.json()["support_badge"] == badge
        memberships.append((member, badge_url))

    now = datetime.now(timezone.utc)
    created = api.client.post("/v1/institution/funded-events", headers=owner, json={
        "group_id": group["group_id"], "name": "Evento por selos", "funding_source": "DONATION",
        "budget_amount_minor": 10001, "currency": "BRL", "end_mode": "TIME",
        "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=1)).isoformat(),
    })
    assert created.status_code == 201, created.text
    event_id = created.json()["event_id"]
    event_url = f"/v1/institution/funded-events/{event_id}"
    assert api.client.post(event_url + "/badge-allocations", headers=other).status_code == 404
    assert api.client.post(event_url + "/badge-allocations", headers=seller_headers).status_code == 403
    applied = api.client.post(event_url + "/badge-allocations", headers=owner)
    assert applied.status_code == 200, applied.text
    event = applied.json()
    assert {s["seller_uid"]: s["allocated_amount_minor"] for s in event["seller_allocations"]} == {"entre-uid": 7001, "entre-other-uid": 3000}
    assert event["badge_distribution"]["policy"] == policy

    # Reclassificar não reescreve uma distribuição já aplicada; falhas são atômicas.
    assert api.client.put(memberships[0][1], headers=owner, json={"support_badge": "GREEN"}).status_code == 200
    failed = api.client.post(event_url + "/badge-allocations", headers=owner)
    assert failed.status_code == 409 and failed.json()["code"] == "INSTITUTION_BADGE_EMPTY_CATEGORY"
    listed = api.client.get("/v1/institution/funded-events", headers=owner).json()["events"][0]
    assert listed["badge_distribution"] == event["badge_distribution"]
    assert listed["seller_allocations"] == event["seller_allocations"]
    # Eventos ativos não podem ter valores recalculados.
    api.store.institution_funded_events[event_id] = replace(api.store.institution_funded_events[event_id], status="ACTIVE", activated_at=now)
    assert api.client.post(event_url + "/badge-allocations", headers=owner).status_code == 409
    api.store.institution_funded_events[event_id] = replace(api.store.institution_funded_events[event_id], status="DRAFT", activated_at=None)
    manual = api.client.put(event_url + "/seller-allocations", headers=owner, json={"allocations": [
        {"seller_uid": "entre-uid", "allocated_amount_minor": 5001}, {"seller_uid": "entre-other-uid", "allocated_amount_minor": 5000},
    ]})
    assert manual.status_code == 200 and manual.json()["badge_distribution"] is None
    assert api.client.post(group_url + "/close", headers=owner).status_code == 200
    assert api.client.put(group_url + "/badge-policy", headers=owner, json=policy).status_code == 409
    assert api.client.put(memberships[0][1], headers=owner, json={"support_badge": "RED"}).status_code == 409
