from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests import test_server_api as api_helpers

URL = "/v1/trq-bec/coupons/purchases/mine"


@pytest.fixture
def api():
    case = api_helpers.ServerApiTests()
    case.setUp()
    try:
        yield case
    finally:
        case.tearDown()


def seed(api, reference, *, buyer="visit-uid", currency="BRL", final=12000, saved=3000, status="REDEEMED", seconds=0):
    api.store.redemptions[(reference, buyer)] = {
        "redemption_id": reference, "merchant_uid": "entre-uid", "product_id": "PROD-HISTORY01",
        "status": status, "quantity": 3, "currency": currency,
        "original_amount_minor": final + saved if final is not None else None,
        "final_amount_minor": final, "amount_saved_minor": saved,
        "committed_at": datetime(2026, 10, 8, tzinfo=timezone.utc) + timedelta(seconds=seconds),
    }


def report(api, query=""):
    result = api.client.get(URL + query, headers=api.headers("visit-token"))
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    return result.json()


def test_report_is_private_and_excludes_unconfirmed_purchases(api):
    seed(api, "own")
    seed(api, "foreign", buyer="another-visitor", final=999999)
    seed(api, "denied", status="DENIED")
    body = report(api, "?buyer_uid=another-visitor")
    assert body["total_purchases"] == 1
    assert body["total_units"] == 3
    assert [row["redemption_id"] for row in body["items"]] == ["own"]
    assert body["totals"][0]["spent_amount_minor"] == 12000
    assert body["totals"][0]["saved_amount_minor"] == 3000
    assert "buyer_uid" not in body["items"][0]
    assert api.client.get(URL).status_code == 401
    assert api.client.get(URL, headers=api.headers("entre-token")).status_code == 403
    visitor = api.store.access_accounts["visit-uid"]
    api.store.access_accounts["visit-uid"] = replace(visitor, status="SUSPENDED")
    assert api.client.get(URL, headers=api.headers("visit-token")).status_code == 403


def test_report_requires_coupon_permission(api):
    visitor = api.store.access_accounts["visit-uid"]
    api.store.access_accounts["visit-uid"] = replace(visitor, permissions=())
    assert api.client.get(URL, headers=api.headers("visit-token")).status_code == 403


def test_totals_cover_all_pages_and_keep_currencies_separate(api):
    seed(api, "a")
    seed(api, "b", seconds=1)
    seed(api, "c", seconds=2, currency="USD", final=800, saved=200)
    first = report(api, "?limit=1")
    second = report(api, "?limit=1&offset=1")
    last = report(api, "?limit=1&offset=2")
    assert first["total_purchases"] == 3
    assert first["total_units"] == 9
    assert first["totals"] == second["totals"] == last["totals"]
    assert [row["redemption_id"] for row in first["items"] + second["items"] + last["items"]] == ["c", "b", "a"]
    assert first["totals"][0]["spent_amount_minor"] == 24000
    assert first["totals"][1]["spent_amount_minor"] == 800
    assert first["has_more"] and second["has_more"] and not last["has_more"]


def test_legacy_spending_is_explicitly_unavailable_and_empty_history_is_supported(api):
    assert report(api)["totals"] == []
    seed(api, "legacy", final=None, saved=500)
    body = report(api)
    assert body["items"][0]["final_amount_minor"] is None
    assert body["totals"][0]["amounts_unavailable_count"] == 1
    assert body["totals"][0]["spent_amount_minor"] == 0
    assert body["totals"][0]["saved_amount_minor"] == 500


@pytest.mark.parametrize("query", ["?limit=0", "?limit=51", "?offset=-1"])
def test_pagination_is_bounded(api, query):
    assert api.client.get(URL + query, headers=api.headers("visit-token")).status_code == 422


def test_actual_redemption_enters_history_once_and_survives_price_change_and_archival(api):
    api.test_seller_signed_qr_quantity_decrements_units_atomically()
    body = report(api)
    assert body["total_purchases"] == 1 and body["total_units"] == 3
    purchase = body["items"][0]
    assert purchase["merchant_name"] == "Artesã da Feira"
    assert purchase["establishment_name"] == "Feira LiberRotas"
    assert purchase["product_title"] == "Bordado artesanal"
    assert purchase["final_amount_minor"] == 12000
    assert purchase["saved_amount_minor"] == 3000
    product = api.store.products[purchase["product_id"]]
    api.store.products[product.product_id] = replace(product, price_minor=99999, status="ARCHIVED")
    assert report(api)["totals"] == body["totals"]
