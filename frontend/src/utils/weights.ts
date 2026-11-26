/** Локальный черновик оффера в потоке редактора. */
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

/**
 * Пересчитывает доли офферов в потоке до суммы 100%.
 * - Удалённые офферы получают 0%.
 * - Закреплённые активные офферы сохраняют заданную долю.
 * - Остаток `100 - sum(pinned)` делится поровну между незакреплёнными активными,
 *   остаток от деления добавляется по +1% сверху вниз.
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

  for (const item of active) {
    if (item.pinned && (Number.isNaN(item.share) || item.share < 0 || item.share > 100)) {
      return {
        offers: items,
        error: `Доля закреплённого оффера #${item.offer_id} должна быть от 0 до 100%.`,
      };
    }
  }

  const pinnedSum = active
    .filter((item) => item.pinned)
    .reduce((acc, item) => acc + item.share, 0);

  if (pinnedSum > 100) {
    return {
      offers: items,
      error: `Сумма закреплённых долей (${pinnedSum}%) превышает 100%. Уменьшите доли или снимите Pin.`,
    };
  }

  const unpinnedIds = active
    .filter((item) => !item.pinned)
    .map((item) => item.offer_id);

  if (unpinnedIds.length === 0) {
    if (pinnedSum !== 100) {
      return {
        offers: items,
        error: `Все активные офферы закреплены, но сумма их долей равна ${pinnedSum}% вместо 100%.`,
      };
    }
    return {
      offers: items.map((item) =>
        item.removed ? { ...item, share: 0, pinned: false } : item
      ),
      error: null,
    };
  }

  const remaining = 100 - pinnedSum;
  const base = Math.floor(remaining / unpinnedIds.length);
  const extra = remaining % unpinnedIds.length;
  const unpinnedShareMap = new Map<number, number>();
  unpinnedIds.forEach((offerId, index) => {
    unpinnedShareMap.set(offerId, base + (index < extra ? 1 : 0));
  });

  return {
    offers: items.map((item) => {
      if (item.removed) {
        return { ...item, share: 0, pinned: false };
      }
      if (item.pinned) {
        return item;
      }
      return {
        ...item,
        share: unpinnedShareMap.get(item.offer_id) ?? 0,
      };
    }),
    error: null,
  };
}

/** Проверяет, отличается ли черновик активных/удалённых офферов от baseline. */
export function isStreamDraftDirty(
  draft: DraftOffer[],
  baseline: DraftOffer[]
): boolean {
  const norm = (list: DraftOffer[]) =>
    list
      .filter((o) => !o.removed)
      .map((o) => `${o.offer_id}:${o.share}`)
      .join("|");
  if (norm(draft) !== norm(baseline)) {
    return true;
  }
  const removedDraft = draft.filter((o) => o.removed).map((o) => o.offer_id).join(",");
  const removedBase = baseline.filter((o) => o.removed).map((o) => o.offer_id).join(",");
  return removedDraft !== removedBase;
}
