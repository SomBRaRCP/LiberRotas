"""Vocabulário fechado de funções, painéis e permissões do LiberRotas."""

from __future__ import annotations


ACCESS_ROLES = frozenset(
    {"admin", "support", "security", "institution", "entrepreneur", "visitor"}
)

PANEL_BY_ROLE = {
    "admin": "admin",
    "support": "support",
    "security": "security",
    "institution": "institution",
    "entrepreneur": "entrepreneur",
    "visitor": "visitor",
}

PANEL_PERMISSION_BY_ROLE = {
    role: f"{role}.panel.access" for role in ACCESS_ROLES
}

DEFAULT_PERMISSIONS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "admin": (
        "admin.panel.access",
        "admin.accounts.manage",
        "admin.staff_accounts.manage",
        "admin.institutions.manage",
        "admin.marketplace.manage",
        "media.admin",
        "ledger.checkpoint.create",
    ),
    "support": (
        "support.panel.access",
        "support.accounts.read",
        "support.institutions.create",
        "support.requests.manage",
        "media.support",
        "directory.search",
    ),
    "security": (
        "security.panel.access",
        "security.audit.read",
        "security.incidents.manage",
        "security.trq_bec.monitor",
    ),
    "institution": (
        "institution.panel.access",
        "institution.groups.manage",
        "institution.events.manage",
        "institution.profile.manage",
        "institution.reports.read",
        "locations.publish",
        "media.upload",
        "directory.search",
        "messaging.use",
        "support.requests.create",
    ),
    "entrepreneur": (
        "entrepreneur.panel.access",
        "feed.publish",
        "institution.memberships.respond",
        "institution.event_allocations.manage",
        "locations.publish",
        "marketplace.manage",
        "media.upload",
        "profile.manage",
        "directory.search",
        "messaging.use",
        "support.requests.create",
    ),
    "visitor": (
        "visitor.panel.access",
        "coupons.redeem",
        "feed.publish",
        "feed.read",
        "media.upload",
        "profile.manage",
        "directory.search",
        "messaging.use",
        "support.requests.create",
    ),
}


def default_permissions(role: str) -> tuple[str, ...]:
    """Retorna a política inicial usada apenas no provisionamento administrativo."""

    return DEFAULT_PERMISSIONS_BY_ROLE.get(role, ())
