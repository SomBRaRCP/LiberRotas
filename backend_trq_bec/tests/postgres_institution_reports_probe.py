"""Probe isolado da filiacao e do relatorio contra PostgreSQL real.

Execute apenas em um banco temporario cujo nome comece com
``trq_bec_institution_probe``. O script nao integra a suite pytest comum.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from trq_bec.server.access_control import default_permissions
from trq_bec.server.models import (
    AccessAccountRecord,
    InstitutionGroupRecord,
)
from trq_bec.server.store import PostgresStore, StoreConflict, StoreNotFound


def main() -> None:
    database_url = os.environ["TRQ_BEC_DATABASE_URL"]
    if not database_url.rsplit("/", 1)[-1].startswith("trq_bec_institution_probe"):
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
    try:
        for uid, role in (
            ("probe-institution-a", "institution"),
            ("probe-institution-b", "institution"),
            ("probe-seller", "entrepreneur"),
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
                INSERT INTO institutional_profiles(firebase_uid, email, name, city)
                VALUES
                  ('probe-institution-a', 'probe-institution-a@example.test', 'Instituicao A', 'Pinhais'),
                  ('probe-institution-b', 'probe-institution-b@example.test', 'Instituicao B', 'Curitiba')
                """
            )
            conn.execute(
                """
                INSERT INTO merchant_accounts
                  (firebase_uid, display_name, establishment_id, establishment_name, status)
                VALUES
                  ('probe-seller', 'Vendedor PostgreSQL', 'EST-PROBE-INST-01',
                   'Banca PostgreSQL', 'ACTIVE')
                """
            )
            conn.execute(
                """
                INSERT INTO public_profile_directory
                  (firebase_uid, display_name, normalized_name, role, city)
                VALUES
                  ('probe-seller', 'Vendedor PostgreSQL', 'vendedor postgresql',
                   'entrepreneur', 'Pinhais')
                """
            )

        group_a = store.create_institution_group(
            InstitutionGroupRecord(
                group_id="IGRP-POSTGRES0001",
                owner_uid="probe-institution-a",
                name="Grupo PostgreSQL A",
                description=None,
                city="Pinhais",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
                closed_at=None,
            )
        )
        group_b = store.create_institution_group(
            InstitutionGroupRecord(
                group_id="IGRP-POSTGRES0002",
                owner_uid="probe-institution-b",
                name="Grupo PostgreSQL B",
                description=None,
                city="Curitiba",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
                closed_at=None,
            )
        )
        invite_a = store.invite_institution_seller(
            group_a.owner_uid,
            group_a.group_id,
            "vendedor postgresql",
            "IGM-POSTGRES00000000001",
            now,
            "probe-event-invite-a",
        )
        repeated = store.invite_institution_seller(
            group_a.owner_uid,
            group_a.group_id,
            "vendedor postgresql",
            "IGM-POSTGRES00000000002",
            now,
            "probe-event-invite-a-retry",
        )
        if repeated.membership_id != invite_a.membership_id:
            raise AssertionError("INVITATION_NOT_IDEMPOTENT")
        active_a = store.respond_institution_invitation(
            "probe-seller",
            invite_a.membership_id,
            "ACCEPT",
            now + timedelta(seconds=1),
            "probe-event-accept-a",
        )
        if active_a.status != "ACTIVE":
            raise AssertionError("INVITATION_ACCEPT_FAILED")

        pending_b = store.invite_institution_seller(
            group_b.owner_uid,
            group_b.group_id,
            "vendedor postgresql",
            "IGM-POSTGRES00000000003",
            now + timedelta(seconds=2),
            "probe-event-invite-b",
        )
        try:
            store.respond_institution_invitation(
                "probe-seller",
                pending_b.membership_id,
                "ACCEPT",
                now + timedelta(seconds=3),
                "probe-event-accept-b",
            )
        except StoreConflict as exc:
            if str(exc) != "SELLER_ALREADY_HAS_ACTIVE_MEMBERSHIP":
                raise
        else:
            raise AssertionError("MULTIPLE_ACTIVE_MEMBERSHIP_ACCEPTED")

        store.close_institution_group(
            group_b.owner_uid,
            group_b.group_id,
            now + timedelta(seconds=4),
        )
        pending_rows, _ = store.list_entrepreneur_institution_memberships(
            "probe-seller", "REMOVED", 10, 0
        )
        if not any(item.membership_id == pending_b.membership_id for item in pending_rows):
            raise AssertionError("PENDING_INVITATION_NOT_REMOVED_ON_GROUP_CLOSE")

        report = store.get_institution_sales_report(
            group_a.owner_uid,
            group_a.group_id,
            now - timedelta(days=1),
            now + timedelta(days=1),
            50,
            0,
        )
        if report.confirmed_redemptions != 0 or len(report.sellers) != 1:
            raise AssertionError("EMPTY_REPORT_MISMATCH")
        try:
            store.get_institution_sales_report(
                group_b.owner_uid,
                group_a.group_id,
                now - timedelta(days=1),
                now + timedelta(days=1),
                50,
                0,
            )
        except StoreNotFound:
            pass
        else:
            raise AssertionError("CROSS_INSTITUTION_REPORT_EXPOSED")

        closed_a = store.close_institution_group(
            group_a.owner_uid,
            group_a.group_id,
            now + timedelta(seconds=5),
        )
        if closed_a.status != "CLOSED":
            raise AssertionError("GROUP_CLOSE_FAILED")
        active_rows, _ = store.list_entrepreneur_institution_memberships(
            "probe-seller", "ACTIVE", 10, 0
        )
        if active_rows:
            raise AssertionError("ACTIVE_MEMBERSHIP_SURVIVED_GROUP_CLOSE")
        print("POSTGRES_INSTITUTION_REPORTS_PROBE_OK")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
