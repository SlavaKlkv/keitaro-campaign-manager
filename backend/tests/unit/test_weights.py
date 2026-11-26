"""Unit-тесты алгоритма пересчёта долей офферов и округления остатков."""

import pytest

from app.services.weights import OfferWeightInput, recalculate_offer_shares


def test_equal_split_divisible_and_with_remainder() -> None:
    """Остаток от деления распределяется по +1% сверху вниз, сумма всегда 100%."""
    items_3 = [
        OfferWeightInput(offer_id=1, share=0),
        OfferWeightInput(offer_id=2, share=0),
        OfferWeightInput(offer_id=3, share=0),
    ]
    res_3 = recalculate_offer_shares(items_3)
    assert [r.share for r in res_3] == [34, 33, 33]
    assert sum(r.share for r in res_3) == 100

    items_5 = [OfferWeightInput(offer_id=i, share=0) for i in range(1, 6)]
    res_5 = recalculate_offer_shares(items_5)
    assert [r.share for r in res_5] == [20, 20, 20, 20, 20]


def test_pinned_offer_preserves_share_and_splits_remainder() -> None:
    """Закреплённая доля 25% сохраняется, остаток 75% делится как 38% и 37%."""
    items = [
        OfferWeightInput(offer_id=10, share=0, pinned=False, removed=False),
        OfferWeightInput(offer_id=11, share=0, pinned=False, removed=False),
        OfferWeightInput(offer_id=12, share=25, pinned=True, removed=False),
        OfferWeightInput(offer_id=13, share=50, pinned=False, removed=True),
    ]
    res = recalculate_offer_shares(items)
    assert [(r.offer_id, r.share, r.pinned, r.removed) for r in res] == [
        (10, 38, False, False),
        (11, 37, False, False),
        (12, 25, True, False),
        (13, 0, False, True),
    ]
    assert sum(r.share for r in res if not r.removed) == 100


def test_pinned_sum_over_100_raises_error() -> None:
    """При сумме закреплённых долей > 100% выбрасывается ValueError."""
    items = [
        OfferWeightInput(offer_id=1, share=60, pinned=True),
        OfferWeightInput(offer_id=2, share=50, pinned=True),
        OfferWeightInput(offer_id=3, share=10, pinned=False),
    ]
    with pytest.raises(ValueError, match="превышает 100%"):
        recalculate_offer_shares(items)


def test_all_pinned_not_equal_100_raises_error() -> None:
    """Если все активные офферы закреплены, но сумма != 100%, выбрасывается ValueError."""
    items = [
        OfferWeightInput(offer_id=1, share=40, pinned=True),
        OfferWeightInput(offer_id=2, share=40, pinned=True),
    ]
    with pytest.raises(ValueError, match="вместо 100%"):
        recalculate_offer_shares(items)


def test_all_pinned_equal_100_succeeds() -> None:
    """Если все активные офферы закреплены и сумма == 100%, доли сохраняются."""
    items = [
        OfferWeightInput(offer_id=1, share=70, pinned=True),
        OfferWeightInput(offer_id=2, share=30, pinned=True),
    ]
    res = recalculate_offer_shares(items)
    assert [r.share for r in res] == [70, 30]
