"""Probe isolado dos eventos financiados contra PostgreSQL real.

Execute somente em banco temporario cujo nome comece com
``trq_bec_funded_probe``. O banco pode ser descartado apos a execucao.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from trq_bec.server.access_control import default_permissions
from trq_bec.server.models import (
    AccessAccountRecord,
    InstitutionBadgePolicy,
    InstitutionFundedEventRecord,
    InstitutionGroupRecord,
)
from trq_bec.server.store import PostgresStore, StoreNotFound, StoreConflict


def main() -> None:
    database_url = os.environ["TRQ_BEC_DATABASE_URL"]
    if not database_url.rsplit("/", 1)[-1].startswith(
        "trq_bec_funded_probe"
    ):
        raise RuntimeError("PROBE_REQUIRES_A_TEMPORARY_DATABASE")
    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    store = PostgresStore(pool, signing_provider=None)
    now = datetime.now(timezone.utc)
    institution_uid = "probe-funded-institution"
    seller_a = "probe-funded-seller-a"
    seller_b = "probe-funded-seller-b"
    group_id = "IGRP-FUNDEDPOSTGRES01"
    event_id = "IEVT-POSTGRESFUNDED0001"
    try:
        for uid, role in (
            (institution_uid, "institution"),
            (seller_a, "entrepreneur"),
            (seller_b, "entrepreneur"),
        ):
            store.set_access_account(
                AccessAccountRecord(
                    firebase_uid=uid,
                    email=f"{uid}@example.test",
                    role=role,
                    status="ACTIVE",
                    allow_entrepreneur_fallback=False,
                    permissions=default_permissions(role),
                )
            )
        with pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO institutional_profiles
                  (firebase_uid, email, name, city)
                VALUES (%s, %s, 'Instituicao Probe Financiado', 'Pinhais')
                """,
                (institution_uid, f"{institution_uid}@example.test"),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO merchant_accounts
                      (firebase_uid, display_name, establishment_id,
                       establishment_name, status)
                    VALUES (%s, %s, %s, %s, 'ACTIVE')
                    """,
                    [
                        (
                            seller_a,
                            "Vendedor Financiado A",
                            "EST-PROBE-FUNDED-A",
                            "Banca A",
                        ),
                        (
                            seller_b,
                            "Vendedor Financiado B",
                            "EST-PROBE-FUNDED-B",
                            "Banca B",
                        ),
                    ],
                )
        store.create_institution_group(
            InstitutionGroupRecord(
                group_id=group_id,
                owner_uid=institution_uid,
                name="Grupo Probe Financiado",
                description=None,
                city="Pinhais",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
                closed_at=None,
            )
        )
        with pool.connection() as conn, conn.transaction():
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO institution_group_memberships
                      (membership_id, group_id, merchant_uid, invited_by_uid,
                       status, invited_at, responded_at, active_from, updated_at)
                    VALUES (%s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s)
                    """,
                    [
                        (
                            "IGM-FUNDEDPOSTGRES0001",
                            group_id,
                            seller_a,
                            institution_uid,
                            now,
                            now,
                            now,
                            now,
                        ),
                        (
                            "IGM-FUNDEDPOSTGRES0002",
                            group_id,
                            seller_b,
                            institution_uid,
                            now,
                            now,
                            now,
                            now,
                        ),
                    ],
                )
                cursor.executemany(
                    """
                    INSERT INTO products
                      (product_id, merchant_uid, title, price_minor, currency,
                       stock_quantity, status)
                    VALUES (%s, %s, %s, 1000, 'BRL', 10, 'ACTIVE')
                    """,
                    [
                        (
                            "PROD-FUNDEDPOSTGRES01",
                            seller_a,
                            "Produto A",
                        ),
                        (
                            "PROD-FUNDEDPOSTGRES02",
                            seller_b,
                            "Produto B",
                        ),
                    ],
                )
        created = store.create_institution_funded_event(
            InstitutionFundedEventRecord(
                event_id=event_id,
                owner_uid=institution_uid,
                institution_name="",
                group_id=group_id,
                group_name="",
                name="Evento financiado do probe",
                description=None,
                funding_source="DONATION",
                budget_amount_minor=1001,
                currency="BRL",
                end_mode="TIME",
                starts_at=now,
                ends_at=now + timedelta(days=1),
                coupon_limit=None,
                current_coupon_redemptions=0,
                status="DRAFT",
                end_reason=None,
                created_at=now,
                updated_at=now,
                activated_at=None,
                ended_at=None,
                seller_allocations=(),
            )
        )
        equal = {
            row.seller_uid: row.allocated_amount_minor
            for row in created.seller_allocations
        }
        if sum(equal.values()) != 1001 or sorted(equal.values()) != [500, 501]:
            raise AssertionError(f"EQUAL_SPLIT_INVALID:{equal}")
        policy = InstitutionBadgePolicy(green_percent=0, yellow_percent=30, red_percent=70)
        store.set_institution_badge_policy(institution_uid, group_id, policy, now)
        saved_group = store.list_institution_groups(institution_uid, 100)[0]
        assert saved_group.badge_policy == policy
        for membership_id, badge in (("IGM-FUNDEDPOSTGRES0001", "RED"), ("IGM-FUNDEDPOSTGRES0002", "YELLOW")):
            member = store.set_institution_member_badge(institution_uid, group_id, membership_id, badge, now)
            assert member.support_badge == badge
        applied = store.set_institution_event_seller_allocations(institution_uid, event_id, (), now, by_badges=True)
        assert {row.seller_uid: row.allocated_amount_minor for row in applied.seller_allocations} == {seller_a: 701, seller_b: 300}
        assert applied.badge_distribution.policy == policy
        store.set_institution_member_badge(institution_uid, group_id, "IGM-FUNDEDPOSTGRES0001", "GREEN", now)
        try:
            store.set_institution_event_seller_allocations(institution_uid, event_id, (), now, by_badges=True)
        except StoreConflict as exc:
            assert str(exc) == "INSTITUTION_BADGE_EMPTY_CATEGORY"
        else:
            raise AssertionError("EMPTY_BADGE_CATEGORY_ACCEPTED")
        persisted = store.list_institution_funded_events(institution_uid, 100)[0]
        assert persisted.badge_distribution == applied.badge_distribution
        assert persisted.seller_allocations == applied.seller_allocations
        print("POSTGRES_SUPPORT_BADGES_PROBE_OK")
        adjusted = store.set_institution_event_seller_allocations(
            institution_uid,
            event_id,
            ((seller_a, 600), (seller_b, 401)),
            now + timedelta(seconds=1),
        )
        if [row.allocated_amount_minor for row in adjusted.seller_allocations] != [
            600,
            401,
        ]:
            raise AssertionError("CUSTOM_SELLER_SPLIT_INVALID")
        assert adjusted.badge_distribution is None
        store.set_institution_event_product_allocations(
            seller_a,
            event_id,
            (("PROD-FUNDEDPOSTGRES01", 600),),
            now + timedelta(seconds=2),
        )
        store.set_institution_event_product_allocations(
            seller_b,
            event_id,
            (("PROD-FUNDEDPOSTGRES02", 401),),
            now + timedelta(seconds=3),
        )
        active = store.activate_institution_funded_event(
            institution_uid,
            event_id,
            now + timedelta(seconds=4),
        )
        if active.status != "ACTIVE":
            raise AssertionError("FUNDED_EVENT_NOT_ACTIVATED")
        report = store.get_institution_funded_event_report(
            institution_uid,
            event_id,
            now + timedelta(seconds=5),
        )
        if (
            report.amount_due_minor != 0
            or report.remaining_budget_minor != 1001
            or len(report.sellers) != 2
        ):
            raise AssertionError("EMPTY_FUNDED_REPORT_INVALID")
        try:
            store.get_institution_funded_event_report(
                "another-institution",
                event_id,
                now + timedelta(seconds=5),
            )
        except StoreNotFound:
            pass
        else:
            raise AssertionError("CROSS_INSTITUTION_FUNDED_REPORT_EXPOSED")
        ended = store.end_institution_funded_event(
            institution_uid,
            event_id,
            now + timedelta(seconds=6),
        )
        if ended.status != "ENDED" or ended.end_reason != "MANUAL":
            raise AssertionError("FUNDED_EVENT_MANUAL_END_INVALID")
        print("POSTGRES_FUNDED_EVENTS_PROBE_OK")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
