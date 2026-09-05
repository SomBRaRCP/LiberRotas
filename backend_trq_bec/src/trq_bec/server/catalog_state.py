"""Deriva estados públicos do catálogo sem revelar o estado interno dos tokens."""

from __future__ import annotations


ProductPublicState = tuple[str, str | None, int | None]
OfferPublicState = tuple[str, str | None, int | None] | None


def product_public_state(
    *,
    product_status: str,
    stock_quantity: int,
    updated_at: int,
) -> ProductPublicState | None:
    """Retorna estado, motivo e término; ARCHIVED representa exclusão pública."""

    if product_status == "ARCHIVED":
        return None
    if product_status == "PAUSED":
        return "PAUSED", "PAUSED", None
    if stock_quantity <= 0:
        return "ENDED", "OUT_OF_STOCK", updated_at
    if product_status == "ACTIVE":
        return "ACTIVE", None, None
    return None


def offer_public_state(
    *,
    offer_status: str,
    expires_at: int,
    updated_at: int,
    remaining_redemptions: int,
    token_redeemable: bool,
    product_status: str,
    product_status_reason: str | None,
    product_ended_at: int | None,
    now: int,
) -> OfferPublicState:
    """Classifica uma oferta; REVOKED e falhas internas não viram conteúdo público."""

    if offer_status == "REVOKED":
        return None
    if offer_status == "CANCELLED":
        return "ENDED", "CANCELLED", updated_at
    if offer_status == "EXHAUSTED":
        return "ENDED", "EXHAUSTED", updated_at
    if offer_status == "EXPIRED" or expires_at <= now:
        return "ENDED", "EXPIRED", expires_at
    if offer_status == "PAUSED":
        return "PAUSED", "PAUSED", None
    if product_status == "PAUSED":
        return "PAUSED", "PRODUCT_PAUSED", None
    if remaining_redemptions <= 0:
        if product_status_reason == "OUT_OF_STOCK":
            return "ENDED", "OUT_OF_STOCK", product_ended_at or updated_at
        return "ENDED", "EXHAUSTED", updated_at
    if offer_status != "ACTIVE" or not token_redeemable:
        return None
    return "ACTIVE", None, None
