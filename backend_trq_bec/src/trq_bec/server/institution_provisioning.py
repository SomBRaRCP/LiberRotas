"""Provisionamento fechado de identidades institucionais no Firebase Auth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from firebase_admin import auth


class InstitutionProvisioningError(RuntimeError):
    pass


class InstitutionEmailExists(InstitutionProvisioningError):
    pass


class InstitutionProvisioningRollbackError(InstitutionProvisioningError):
    pass


@dataclass(frozen=True, slots=True)
class ProvisionedInstitutionIdentity:
    firebase_uid: str
    email: str


class InstitutionIdentityProvisioner(Protocol):
    def provision(self, email: str, name: str) -> ProvisionedInstitutionIdentity: ...

    def rollback(self, firebase_uid: str) -> None: ...


class FirebaseInstitutionIdentityProvisioner:
    """Cria sempre role institution; nenhuma funcao e recebida do cliente."""

    def provision(self, email: str, name: str) -> ProvisionedInstitutionIdentity:
        try:
            user = auth.create_user(
                email=email,
                display_name=name,
                disabled=False,
            )
        except auth.EmailAlreadyExistsError as exc:
            raise InstitutionEmailExists("INSTITUTION_EMAIL_EXISTS") from exc
        except Exception as exc:
            raise InstitutionProvisioningError("INSTITUTION_PROVISION_FAILED") from exc

        try:
            auth.set_custom_user_claims(
                user.uid,
                {
                    "role": "institution",
                    "admin": False,
                },
            )
        except Exception as exc:
            try:
                auth.delete_user(user.uid)
            except Exception as rollback_exc:
                raise InstitutionProvisioningRollbackError(
                    "INSTITUTION_PROVISION_ROLLBACK_FAILED"
                ) from rollback_exc
            raise InstitutionProvisioningError("INSTITUTION_PROVISION_FAILED") from exc

        return ProvisionedInstitutionIdentity(
            firebase_uid=user.uid,
            email=user.email or email,
        )

    def rollback(self, firebase_uid: str) -> None:
        try:
            auth.delete_user(firebase_uid)
        except auth.UserNotFoundError:
            return
        except Exception as exc:
            raise InstitutionProvisioningRollbackError(
                "INSTITUTION_PROVISION_ROLLBACK_FAILED"
            ) from exc
