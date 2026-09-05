from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trq_bec.server.institution_provisioning import (
    FirebaseInstitutionIdentityProvisioner,
    InstitutionProvisioningError,
)


def test_firebase_institution_provisioner_hardcodes_claims_without_password() -> None:
    user = SimpleNamespace(
        uid="firebase-institution-uid",
        email="institution@example.test",
    )
    with (
        patch("trq_bec.server.institution_provisioning.auth.create_user", return_value=user) as create,
        patch(
            "trq_bec.server.institution_provisioning.auth.set_custom_user_claims"
        ) as set_claims,
    ):
        identity = FirebaseInstitutionIdentityProvisioner().provision(
            "institution@example.test",
            "Instituicao de Teste",
        )

    assert identity.firebase_uid == "firebase-institution-uid"
    assert identity.email == "institution@example.test"
    create.assert_called_once_with(
        email="institution@example.test",
        display_name="Instituicao de Teste",
        disabled=False,
    )
    assert "password" not in create.call_args.kwargs
    set_claims.assert_called_once_with(
        "firebase-institution-uid",
        {"role": "institution", "admin": False},
    )


def test_firebase_institution_provisioner_deletes_user_when_claim_write_fails() -> None:
    user = SimpleNamespace(uid="rollback-uid", email="rollback@example.test")
    with (
        patch("trq_bec.server.institution_provisioning.auth.create_user", return_value=user),
        patch(
            "trq_bec.server.institution_provisioning.auth.set_custom_user_claims",
            side_effect=RuntimeError("claims unavailable"),
        ),
        patch("trq_bec.server.institution_provisioning.auth.delete_user") as delete_user,
    ):
        with pytest.raises(InstitutionProvisioningError):
            FirebaseInstitutionIdentityProvisioner().provision(
                "rollback@example.test",
                "Rollback",
            )

    delete_user.assert_called_once_with("rollback-uid")
