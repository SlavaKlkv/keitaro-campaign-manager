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
      item.removed !== other.removed
    );
  });
}

/**
 * Пересчитывает доли офферов в потоке до суммы ровно 100%.
 * Удалённые получают 0%; закреплённые (pinned) и опционально редактируемый сейчас
 * оффер (`fixedOfferId`) сохраняют заданные доли, а остаток `100 - sum(fixed)`
 * делится поровну между остальными активными незакреплёнными офферами
 * с распределением остатка +1% сверху вниз.
 */
export function recalculateDraftShares(
  items: DraftOffer[],
  fixedOfferId?: number
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

  const isFixed = (item: DraftOffer): boolean =>
    item.pinned || (fixedOfferId !== undefined && item.offer_id === fixedOfferId);

  let fixedSum = 0;
  let adjustableCount = 0;
  for (const item of active) {
    if (isFixed(item)) {
      if (!Number.isFinite(item.share) || item.share < 0 || item.share > 100) {
        return {
          offers: items,
          error: `Доля оффера #${item.offer_id} должна быть от 0 до 100%.`,
        };
      }
      fixedSum += Math.round(item.share);
    } else {
      adjustableCount += 1;
    }
  }

  if (fixedSum > 100) {
    return {
      offers: items,
      error: `Сумма заданных долей (${fixedSum}%) превышает 100%. Уменьшите значение или открепите закреплённые доли.`,
    };
  }

  if (adjustableCount === 0) {
    const allPinned = active.every((item) => item.pinned);
    const error =
      fixedSum !== 100
        ? allPinned
          ? `Все активные офферы закреплены, но сумма их долей равна ${fixedSum}% вместо 100%.`
          : `Сумма долей активных офферов равна ${fixedSum}% вместо 100%. Измените значение или открепите закреплённые доли.`
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

  const remaining = 100 - fixedSum;
  const baseShare = Math.floor(remaining / adjustableCount);
  const remainder = remaining % adjustableCount;

  let adjustableIdx = 0;
  const updated = items.map((item) => {
    if (item.removed) {
      return { ...item, share: 0, pinned: false };
    }
    if (isFixed(item)) {
      return { ...item, share: Math.round(item.share) };
    }
    const extra = adjustableIdx < remainder ? 1 : 0;
    adjustableIdx += 1;
    return { ...item, share: baseShare + extra };
  });

  return { offers: updated, error: null };
}
