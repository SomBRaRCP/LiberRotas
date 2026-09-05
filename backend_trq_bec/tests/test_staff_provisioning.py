from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from trq_bec.server.staff_provisioning import (
    FirebaseStaffIdentityProvisioner,
    StaffProvisioningError,
)


def test_firebase_staff_provisioner_creates_pending_claims_without_password() -> None:
    user = SimpleNamespace(
        uid="firebase-support-uid",
        email="novo-suporte@example.test",
    )
    with (
        patch(
            "trq_bec.server.staff_provisioning.auth.create_user",
            return_value=user,
        ) as create,
        patch(
            "trq_bec.server.staff_provisioning.auth.set_custom_user_claims"
        ) as set_claims,
    ):
        identity = FirebaseStaffIdentityProvisioner().provision(
            "novo-suporte@example.test",
            "Novo Suporte",
            "support",
        )

    assert identity.firebase_uid == "firebase-support-uid"
    assert identity.role == "support"
    create.assert_called_once_with(
        email="novo-suporte@example.test",
        display_name="Novo Suporte",
        disabled=False,
    )
    assert "password" not in create.call_args.kwargs
    set_claims.assert_called_once_with(
        "firebase-support-uid",
        {
            "role": "support",
            "admin": False,
            "staff_validated": False,
            "official": False,
        },
    )


def test_firebase_staff_validation_sets_claim_and_revokes_sessions() -> None:
    provisioner = FirebaseStaffIdentityProvisioner()
    with (
        patch(
            "trq_bec.server.staff_provisioning.auth.set_custom_user_claims"
        ) as set_claims,
        patch(
            "trq_bec.server.staff_provisioning.auth.revoke_refresh_tokens"
        ) as revoke,
    ):
        provisioner.set_validated("security-uid", "security", True)
        provisioner.set_validated("security-uid", "security", False)

    assert set_claims.call_args_list == [
        call(
            "security-uid",
            {
                "role": "security",
                "admin": False,
                "staff_validated": True,
                "official": False,
            },
        ),
        call(
            "security-uid",
            {
                "role": "security",
                "admin": False,
                "staff_validated": False,
                "official": False,
            },
        ),
    ]
    assert revoke.call_count == 2


def test_firebase_staff_provisioner_rolls_back_when_claim_write_fails() -> None:
    user = SimpleNamespace(uid="rollback-staff-uid", email="rollback@example.test")
    with (
        patch(
            "trq_bec.server.staff_provisioning.auth.create_user",
            return_value=user,
        ),
        patch(
            "trq_bec.server.staff_provisioning.auth.set_custom_user_claims",
            side_effect=RuntimeError("claims unavailable"),
        ),
        patch(
            "trq_bec.server.staff_provisioning.auth.delete_user"
        ) as delete_user,
    ):
        with pytest.raises(StaffProvisioningError):
            FirebaseStaffIdentityProvisioner().provision(
                "rollback@example.test",
                "Rollback",
                "admin",
            )

    delete_user.assert_called_once_with("rollback-staff-uid")
