export interface DraftOffer {
  offer_id: number;
  name: string;
  share: number;
  pinned: boolean;
  removed: boolean;
  country: string[];
  removedExternally?: boolean;
}

export interface OfferPerformanceMetric {
  offer_id: number;
  clicks: number;
  conversions: number;
  cr: number;
  epc: number;
  revenue: number;
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

/**
 * Ребалансирует доли незакреплённых активных офферов по статистике (EPC, fallback на CR или поровну),
 * отсекая шум ниже порога `minClicks`. Сумма активных долей всегда равна 100%.
 */
export function rebalanceByPerformance(
  items: DraftOffer[],
  statsByOfferId: Record<number, OfferPerformanceMetric>,
  minClicks: number
): RecalculationResult {
  const active = items.filter((item) => !item.removed);
  if (active.length === 0) {
    return {
      offers: items,
      error: "В потоке должен остаться хотя бы один активный оффер.",
    };
  }

  const pinnedSum = active
    .filter((item) => item.pinned)
    .reduce((acc, item) => acc + Math.round(item.share), 0);

  if (pinnedSum > 100) {
    return {
      offers: items,
      error: `Сумма закреплённых долей (${pinnedSum}%) превышает 100%.`,
    };
  }

  const adjustable = active.filter((item) => !item.pinned);
  if (adjustable.length === 0) {
    return {
      offers: items,
      error:
        pinnedSum !== 100
          ? `Все активные офферы закреплены, но сумма их долей равна ${pinnedSum}% вместо 100%.`
          : null,
    };
  }

  const threshold = Math.max(0, Math.trunc(minClicks));
  const eligible = adjustable.filter(
    (item) => (statsByOfferId[item.offer_id]?.clicks ?? 0) >= threshold
  );

  if (eligible.length === 0) {
    return {
      offers: items,
      error: `Нет незакреплённых офферов с кликами ≥ ${threshold}. Снизьте порог кликов.`,
    };
  }

  const remaining = 100 - pinnedSum;
  const rawScores = new Map<number, number>();
  let totalScore = 0;

  for (const item of eligible) {
    const stat = statsByOfferId[item.offer_id];
    const epc = stat?.epc ?? 0;
    const cr = stat?.cr ?? 0;
    const score = epc > 0 ? epc : cr > 0 ? cr : 0;
    rawScores.set(item.offer_id, score);
    totalScore += score;
  }

  // Если у всех допущенных офферов нулевые EPC и CR — делим остаток поровну
  if (totalScore <= 0) {
    for (const item of eligible) {
      rawScores.set(item.offer_id, 1);
    }
    totalScore = eligible.length;
  }

  // Метод наибольших остатков (Hamilton) гарантирует целые доли с точной суммой remaining
  const allocations = new Map<number, number>();
  const remainders: { offerId: number; frac: number; score: number }[] = [];
  let allocated = 0;

  for (const item of eligible) {
    const score = rawScores.get(item.offer_id) ?? 0;
    const exact = (remaining * score) / totalScore;
    const floored = Math.floor(exact);
    allocations.set(item.offer_id, floored);
    allocated += floored;
    remainders.push({
      offerId: item.offer_id,
      frac: exact - floored,
      score,
    });
  }

  remainders.sort((a, b) => b.frac - a.frac || b.score - a.score);
  let left = remaining - allocated;
  for (let i = 0; i < remainders.length && left > 0; i += 1) {
    const id = remainders[i].offerId;
    allocations.set(id, (allocations.get(id) ?? 0) + 1);
    left -= 1;
  }

  const updated = items.map((item) => {
    if (item.removed) {
      return { ...item, share: 0, pinned: false };
    }
    if (item.pinned) {
      return { ...item, share: Math.round(item.share) };
    }
    return {
      ...item,
      share: allocations.get(item.offer_id) ?? 0,
    };
  });

  return { offers: updated, error: null };
}
