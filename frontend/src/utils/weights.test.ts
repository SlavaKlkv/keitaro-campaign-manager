import { describe, expect, it } from "vitest";
import {
  isStreamDraftDirty,
  recalculateDraftShares,
  type DraftOffer,
} from "./weights";

/** Хелпер для создания строки черновика оффера в тестах. */
function makeOffer(
  offer_id: number,
  share: number,
  overrides: Partial<DraftOffer> = {}
): DraftOffer {
  return {
    offer_id,
    name: `Offer #${offer_id}`,
    share,
    pinned: false,
    removed: false,
    country: [],
    ...overrides,
  };
}

describe("recalculateDraftShares", () => {
  it("делит 100% поровну и распределяет остаток +1% сверху вниз", () => {
    const three = recalculateDraftShares([
      makeOffer(1, 0),
      makeOffer(2, 0),
      makeOffer(3, 0),
    ]);
    expect(three.error).toBeNull();
    expect(three.offers.map((o) => o.share)).toEqual([34, 33, 33]);

    const five = recalculateDraftShares([
      makeOffer(1, 0),
      makeOffer(2, 0),
      makeOffer(3, 0),
      makeOffer(4, 0),
      makeOffer(5, 0),
    ]);
    expect(five.error).toBeNull();
    expect(five.offers.map((o) => o.share)).toEqual([20, 20, 20, 20, 20]);
  });

  it("мгновенно пересчитывает остальных при ручном вводе Share у незакреплённого оффера", () => {
    const three = recalculateDraftShares(
      [makeOffer(1, 34), makeOffer(2, 33), makeOffer(3, 25)],
      3
    );
    expect(three.error).toBeNull();
    expect(three.offers.map((o) => o.share)).toEqual([38, 37, 25]);
    expect(three.offers.every((o) => !o.pinned)).toBe(true);

    const two = recalculateDraftShares(
      [makeOffer(1, 20), makeOffer(2, 50)],
      1
    );
    expect(two.error).toBeNull();
    expect(two.offers.map((o) => o.share)).toEqual([20, 80]);
  });

  it("сохраняет закреплённую долю и обнуляет удалённые офферы", () => {
    const res = recalculateDraftShares([
      makeOffer(10, 0),
      makeOffer(11, 0),
      makeOffer(12, 25, { pinned: true }),
      makeOffer(13, 50, { removed: true }),
    ]);
    expect(res.error).toBeNull();
    expect(
      res.offers.map((o) => [o.offer_id, o.share, o.pinned, o.removed])
    ).toEqual([
      [10, 38, false, false],
      [11, 37, false, false],
      [12, 25, true, false],
      [13, 0, false, true],
    ]);
  });

  it("при правке незакреплённого оффера сохраняет и его, и закреплённые офферы", () => {
    const res = recalculateDraftShares(
      [
        makeOffer(1, 40),
        makeOffer(2, 37),
        makeOffer(3, 25, { pinned: true }),
      ],
      1
    );
    expect(res.error).toBeNull();
    expect(res.offers.map((o) => o.share)).toEqual([40, 35, 25]);
  });

  it("валидирует сумму при правке последнего незакреплённого оффера", () => {
    const bad = recalculateDraftShares(
      [makeOffer(1, 60, { pinned: true }), makeOffer(2, 30)],
      2
    );
    expect(bad.error).toContain("90% вместо 100%");

    const ok = recalculateDraftShares(
      [makeOffer(1, 60, { pinned: true }), makeOffer(2, 40)],
      2
    );
    expect(ok.error).toBeNull();
    expect(ok.offers.map((o) => o.share)).toEqual([60, 40]);
  });

  it("возвращает ошибку при сумме заданных/закреплённых долей > 100%", () => {
    const pinnedOverflow = recalculateDraftShares([
      makeOffer(1, 60, { pinned: true }),
      makeOffer(2, 50, { pinned: true }),
      makeOffer(3, 10),
    ]);
    expect(pinnedOverflow.error).toContain("превышает 100%");

    const editedOverflow = recalculateDraftShares(
      [makeOffer(1, 60, { pinned: true }), makeOffer(2, 50), makeOffer(3, 10)],
      2
    );
    expect(editedOverflow.error).toContain("превышает 100%");
  });

  it("проверяет сумму 100%, когда все активные офферы закреплены", () => {
    const bad = recalculateDraftShares([
      makeOffer(1, 40, { pinned: true }),
      makeOffer(2, 40, { pinned: true }),
    ]);
    expect(bad.error).toContain("вместо 100%");

    const ok = recalculateDraftShares([
      makeOffer(1, 70, { pinned: true }),
      makeOffer(2, 30, { pinned: true }),
    ]);
    expect(ok.error).toBeNull();
    expect(ok.offers.map((o) => o.share)).toEqual([70, 30]);
  });

  it("возвращает ошибку и обнуляет доли, если не осталось активных офферов", () => {
    const res = recalculateDraftShares([
      makeOffer(1, 50, { removed: true }),
      makeOffer(2, 50, { removed: true }),
    ]);
    expect(res.error).toContain("хотя бы один активный оффер");
    expect(res.offers.every((o) => o.share === 0 && o.removed && !o.pinned)).toBe(
      true
    );
  });
});

describe("isStreamDraftDirty", () => {
  it("отслеживает изменения состава и долей, игнорируя только UI-флаг pinned", () => {
    const baseline = [makeOffer(1, 50), makeOffer(2, 50)];
    expect(isStreamDraftDirty(baseline, baseline)).toBe(false);

    const onlyPinned = [makeOffer(1, 50, { pinned: true }), makeOffer(2, 50)];
    expect(isStreamDraftDirty(onlyPinned, baseline)).toBe(false);

    const changedShare = [makeOffer(1, 60), makeOffer(2, 40)];
    expect(isStreamDraftDirty(changedShare, baseline)).toBe(true);

    const removedOffer = [
      makeOffer(1, 100),
      makeOffer(2, 0, { removed: true }),
    ];
    expect(isStreamDraftDirty(removedOffer, baseline)).toBe(true);

    const addedOffer = [makeOffer(1, 34), makeOffer(2, 33), makeOffer(3, 33)];
    expect(isStreamDraftDirty(addedOffer, baseline)).toBe(true);
  });
});
