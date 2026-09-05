"""Provisiona Custom Claim e acesso autoritativo pelo ambiente do backend."""

from __future__ import annotations

import argparse

import psycopg
from firebase_admin import auth

from .access_control import ACCESS_ROLES, default_permissions
from .auth import FirebaseAuthenticator
from .config import get_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Provision LiberRotas role, status and database permissions"
    )
    parser.add_argument("identity", help="Firebase UID or exact account e-mail")
    parser.add_argument("role", choices=sorted(ACCESS_ROLES))
    parser.add_argument(
        "--status",
        choices=["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"],
        default="ACTIVE",
    )
    parser.add_argument(
        "--allow-entrepreneur-fallback",
        action="store_true",
        help="Explicitly permit entrepreneur access when the role claim is temporarily absent",
    )
    args = parser.parse_args(argv)

    if args.allow_entrepreneur_fallback and args.role != "entrepreneur":
        parser.error("--allow-entrepreneur-fallback is valid only for entrepreneur")

    settings = get_settings()
    FirebaseAuthenticator(settings)
    user = (
        auth.get_user_by_email(args.identity.strip().lower())
        if "@" in args.identity
        else auth.get_user(args.identity.strip())
    )
    permissions = default_permissions(args.role)
    privileged_role = args.role in {"admin", "support", "security"}

    # O banco é atualizado antes da claim. Qualquer falha parcial permanece
    # fechada porque /v1/access/me exige que os dois lados coincidam.
    with psycopg.connect(settings.database_url) as connection:
        validation = (
            connection.execute(
                """
                SELECT requested_role, validation_state, protection_level
                  FROM privileged_account_validations
                 WHERE firebase_uid = %s
                """,
                (user.uid,),
            ).fetchone()
            if privileged_role
            else None
        )
        authority_approved = bool(
            validation
            and validation[0] == args.role
            and validation[1] == "APPROVED"
        )
        effective_status = (
            args.status
            if not privileged_role or authority_approved
            else "PENDING"
        )
        connection.execute(
            """
            INSERT INTO access_accounts
              (firebase_uid, email, role, status, allow_entrepreneur_fallback)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (firebase_uid) DO UPDATE SET
              email = EXCLUDED.email,
              role = EXCLUDED.role,
              status = EXCLUDED.status,
              allow_entrepreneur_fallback = EXCLUDED.allow_entrepreneur_fallback,
              updated_at = now()
            """,
            (
                user.uid,
                user.email.lower() if user.email else None,
                args.role,
                effective_status,
                args.allow_entrepreneur_fallback,
            ),
        )
        connection.execute(
            "DELETE FROM account_permissions WHERE firebase_uid = %s",
            (user.uid,),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO account_permissions (firebase_uid, permission) VALUES (%s, %s)",
                [(user.uid, permission) for permission in permissions],
            )

    claims = dict(user.custom_claims or {})
    claims.pop("account_type", None)
    claims["role"] = args.role
    if args.role == "admin":
        claims["admin"] = True
    else:
        claims.pop("admin", None)
    if privileged_role:
        claims["staff_validated"] = authority_approved
        claims["official"] = bool(
            validation and validation[2] == "SYSTEM"
        )
    else:
        claims.pop("staff_validated", None)
        claims.pop("official", None)
    auth.set_custom_user_claims(user.uid, claims)
    auth.revoke_refresh_tokens(user.uid)
    print(
        f"Provisioned UID {user.uid} as {args.role} with status {effective_status}; "
        "the account must sign in again"
    )


if __name__ == "__main__":
    main()
