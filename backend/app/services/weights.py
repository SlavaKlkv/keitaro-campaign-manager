"""Алгоритм расчёта и округления долей (весов) офферов в потоке."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OfferWeightInput:
    """Входное состояние строки оффера для пересчёта долей."""

    offer_id: int
    share: int
    pinned: bool = False
    removed: bool = False


@dataclass(frozen=True)
class OfferWeightResult:
    """Результат пересчёта доли для одного оффера."""

    offer_id: int
    share: int
    pinned: bool
    removed: bool


def recalculate_offer_shares(items: list[OfferWeightInput]) -> list[OfferWeightResult]:
    """Пересчитывает доли офферов до суммы 100%.

    Правила:
    - удалённые офферы всегда получают 0%;
    - сумма закреплённых (pinned) активных офферов не может превышать 100%;
    - остаток ``100 - sum(pinned)`` делится поровну между незакреплёнными активными
      офферами, а остаток от целочисленного деления распределяется по +1% сверху вниз;
    - если все активные офферы закреплены, их сумма обязана равняться 100%.
    """
    active = [item for item in items if not item.removed]
    if not active:
        return [
            OfferWeightResult(
                offer_id=item.offer_id,
                share=0,
                pinned=False,
                removed=True,
            )
            for item in items
        ]

    for item in active:
        if item.pinned and (item.share < 0 or item.share > 100):
            raise ValueError(
                f"Закреплённая доля оффера #{item.offer_id} должна быть от 0 до 100%"
            )

    pinned_sum = sum(item.share for item in active if item.pinned)
    if pinned_sum > 100:
        raise ValueError(
            f"Сумма закреплённых долей ({pinned_sum}%) превышает 100%"
        )

    unpinned_ids = [item.offer_id for item in active if not item.pinned]
    if not unpinned_ids:
        if pinned_sum != 100:
            raise ValueError(
                f"Все активные офферы закреплены, но сумма их долей равна {pinned_sum}% вместо 100%"
            )
        return [
            OfferWeightResult(
                offer_id=item.offer_id,
                share=0 if item.removed else item.share,
                pinned=False if item.removed else item.pinned,
                removed=item.removed,
            )
            for item in items
        ]

    remaining = 100 - pinned_sum
    base, extra = divmod(remaining, len(unpinned_ids))
    unpinned_shares: dict[int, int] = {}
    for idx, offer_id in enumerate(unpinned_ids):
        unpinned_shares[offer_id] = base + (1 if idx < extra else 0)

    results: list[OfferWeightResult] = []
    for item in items:
        if item.removed:
            results.append(
                OfferWeightResult(
                    offer_id=item.offer_id,
                    share=0,
                    pinned=False,
                    removed=True,
                )
            )
        elif item.pinned:
            results.append(
                OfferWeightResult(
                    offer_id=item.offer_id,
                    share=item.share,
                    pinned=True,
                    removed=False,
                )
            )
        else:
            results.append(
                OfferWeightResult(
                    offer_id=item.offer_id,
                    share=unpinned_shares[item.offer_id],
                    pinned=False,
                    removed=False,
                )
            )
    return results
