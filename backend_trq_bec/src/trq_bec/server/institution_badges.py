"""Distribuição em centavos: parcela por selo e divisão igual dentro da categoria."""

from .models import InstitutionBadgePolicy


def allocate_by_badges(
    budget: int, policy: InstitutionBadgePolicy | None, seller_badges: dict[str, str | None],
) -> tuple[tuple[str, int], ...]:
    if policy is None:
        raise ValueError("INSTITUTION_BADGE_POLICY_REQUIRED")
    badges = ("RED", "YELLOW", "GREEN")
    if not seller_badges or any(badge not in badges for badge in seller_badges.values()):
        raise ValueError("INSTITUTION_BADGE_CLASSIFICATION_REQUIRED")
    percentages = dict(zip(badges, (policy.red_percent, policy.yellow_percent, policy.green_percent)))
    members = {badge: sorted(uid for uid, value in seller_badges.items() if value == badge) for badge in badges}
    if any(percentages[badge] > 0 and not members[badge] for badge in badges):
        raise ValueError("INSTITUTION_BADGE_EMPTY_CATEGORY")
    amounts = {badge: budget * percentages[badge] // 100 for badge in badges}
    # Maiores restos; em empate, prioridade vermelho, amarelo, verde.
    remainder_order = sorted(badges, key=lambda badge: -(budget * percentages[badge] % 100))
    for badge in remainder_order[:budget - sum(amounts.values())]:
        amounts[badge] += 1
    allocations = []
    for badge in badges:
        if not members[badge]:
            continue
        amount, remainder = divmod(amounts[badge], len(members[badge]))
        allocations.extend((uid, amount + (index < remainder)) for index, uid in enumerate(members[badge]))
    return tuple(allocations)
