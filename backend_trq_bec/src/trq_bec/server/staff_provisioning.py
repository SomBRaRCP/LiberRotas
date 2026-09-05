"""Provisionamento fechado e validação de identidades privilegiadas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from firebase_admin import auth


STAFF_ROLES = frozenset({"admin", "support", "security"})


class StaffProvisioningError(RuntimeError):
    pass


class StaffEmailExists(StaffProvisioningError):
    pass


class StaffProvisioningRollbackError(StaffProvisioningError):
    pass


@dataclass(frozen=True, slots=True)
class ProvisionedStaffIdentity:
    firebase_uid: str
    email: str
    role: str


@dataclass(frozen=True, slots=True)
class StaffIdentityState:
    firebase_uid: str
    email: str
    role: str | None
    email_verified: bool
    disabled: bool


class StaffIdentityProvisioner(Protocol):
    def provision(
        self,
        email: str,
        display_name: str,
        role: str,
    ) -> ProvisionedStaffIdentity: ...

    def inspect(self, firebase_uid: str) -> StaffIdentityState: ...

    def set_validated(self, firebase_uid: str, role: str, validated: bool) -> None: ...

    def rollback(self, firebase_uid: str) -> None: ...


class FirebaseStaffIdentityProvisioner:
    """Mantém função e claims fora do contrato controlado pelo frontend."""

    @staticmethod
    def _claims(role: str, *, validated: bool) -> dict[str, object]:
        if role not in STAFF_ROLES:
            raise StaffProvisioningError("STAFF_ROLE_INVALID")
        return {
            "role": role,
            "admin": role == "admin",
            "staff_validated": validated,
            "official": False,
        }

    def provision(
        self,
        email: str,
        display_name: str,
        role: str,
    ) -> ProvisionedStaffIdentity:
        if role not in STAFF_ROLES:
            raise StaffProvisioningError("STAFF_ROLE_INVALID")
        try:
            user = auth.create_user(
                email=email,
                display_name=display_name,
                disabled=False,
            )
        except auth.EmailAlreadyExistsError as exc:
            raise StaffEmailExists("STAFF_EMAIL_EXISTS") from exc
        except Exception as exc:
            raise StaffProvisioningError("STAFF_PROVISION_FAILED") from exc

        try:
            auth.set_custom_user_claims(
                user.uid,
                self._claims(role, validated=False),
            )
        except Exception as exc:
            try:
                auth.delete_user(user.uid)
            except Exception as rollback_exc:
                raise StaffProvisioningRollbackError(
                    "STAFF_PROVISION_ROLLBACK_FAILED"
                ) from rollback_exc
            raise StaffProvisioningError("STAFF_PROVISION_FAILED") from exc

        return ProvisionedStaffIdentity(
            firebase_uid=user.uid,
            email=user.email or email,
            role=role,
        )

    def inspect(self, firebase_uid: str) -> StaffIdentityState:
        try:
            user = auth.get_user(firebase_uid)
        except auth.UserNotFoundError as exc:
            raise StaffProvisioningError("STAFF_IDENTITY_NOT_FOUND") from exc
        except Exception as exc:
            raise StaffProvisioningError("STAFF_IDENTITY_LOOKUP_FAILED") from exc
        claims = user.custom_claims or {}
        role = claims.get("role")
        return StaffIdentityState(
            firebase_uid=user.uid,
            email=user.email or "",
            role=role if isinstance(role, str) else None,
            email_verified=bool(user.email_verified),
            disabled=bool(user.disabled),
        )

    def set_validated(self, firebase_uid: str, role: str, validated: bool) -> None:
        try:
            auth.set_custom_user_claims(
                firebase_uid,
                self._claims(role, validated=validated),
            )
            auth.revoke_refresh_tokens(firebase_uid)
        except auth.UserNotFoundError as exc:
            raise StaffProvisioningError("STAFF_IDENTITY_NOT_FOUND") from exc
        except Exception as exc:
            raise StaffProvisioningError("STAFF_CLAIM_UPDATE_FAILED") from exc

    def rollback(self, firebase_uid: str) -> None:
        try:
            auth.delete_user(firebase_uid)
        except auth.UserNotFoundError:
            return
        except Exception as exc:
            raise StaffProvisioningRollbackError(
                "STAFF_PROVISION_ROLLBACK_FAILED"
            ) from exc
