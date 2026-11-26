export interface DraftOffer {
  offer_id: number;
  name: string;
  share: number;
  pinned: boolean;
  removed: boolean;
  country: string[];
}

export interface RecalculationResult {
  offers: DraftOffer[];
  error: string | null;
}

/** Проверяет, отличается ли текущий черновик потока от сохранённого baseline. */
export function isStreamDraftDirty(
  draft: DraftOffer[],
  baseline: DraftOffer[]
): boolean {
  if (draft.length !== baseline.length) return true;
  return draft.some((item, idx) => {
    const other = baseline[idx];
    return (
      item.offer_id !== other.offer_id ||
      item.share !== other.share ||
      item.pinned !== other.pinned ||
      item.removed !== other.removed
    );
  });
}

/**
 * Пересчитывает доли офферов в потоке до суммы ровно 100%.
 * Удалённые получают 0%; остаток `100 - sum(pinned)` делится поровну между
 * активными незакреплёнными офферами с распределением остатка +1% сверху вниз.
 */
export function recalculateDraftShares(
  items: DraftOffer[]
): RecalculationResult {
  const active = items.filter((item) => !item.removed);
  if (active.length === 0) {
    return {
      offers: items.map((item) => ({
        ...item,
        share: 0,
        pinned: false,
        removed: true,
      })),
      error: "В потоке должен остаться хотя бы один активный оффер.",
    };
  }

  let pinnedSum = 0;
  let unpinnedCount = 0;
  for (const item of active) {
    if (item.pinned) {
      if (!Number.isFinite(item.share) || item.share < 0 || item.share > 100) {
        return {
          offers: items,
          error: `Доля закреплённого оффера #${item.offer_id} должна быть от 0 до 100%.`,
        };
      }
      pinnedSum += Math.round(item.share);
    } else {
      unpinnedCount += 1;
    }
  }

  if (pinnedSum > 100) {
    return {
      offers: items,
      error: `Сумма закреплённых долей (${pinnedSum}%) превышает 100%. Уменьшите или открепите доли.`,
    };
  }

  if (unpinnedCount === 0) {
    const error =
      pinnedSum !== 100
        ? `Все активные офферы закреплены, но сумма их долей равна ${pinnedSum}% вместо 100%.`
        : null;
    return {
      offers: items.map((item) =>
        item.removed
          ? { ...item, share: 0, pinned: false }
          : { ...item, share: Math.round(item.share) }
      ),
      error,
    };
  }

  const remaining = 100 - pinnedSum;
  const baseShare = Math.floor(remaining / unpinnedCount);
  const remainder = remaining % unpinnedCount;

  let unpinnedIdx = 0;
  const updated = items.map((item) => {
    if (item.removed) {
      return { ...item, share: 0, pinned: false };
    }
    if (item.pinned) {
      return { ...item, share: Math.round(item.share) };
    }
    const extra = unpinnedIdx < remainder ? 1 : 0;
    unpinnedIdx += 1;
    return { ...item, share: baseShare + extra };
  });

  return { offers: updated, error: null };
}
