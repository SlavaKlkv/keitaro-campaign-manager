import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  CampaignStreamsResponse,
  CampaignSummary,
  MetaResponse,
  OfferItem,
  StreamFilterItem,
  StreamInfo,
} from "../types";
import {
  isStreamDraftDirty,
  recalculateDraftShares,
  type DraftOffer,
} from "../utils/weights";

interface CampaignEditorProps {
  meta: MetaResponse | null;
  initialCampaignId: number | null;
}

interface StreamState {
  baseline: DraftOffer[];
  draft: DraftOffer[];
  validationError: string | null;
  pushing: boolean;
  pushError: string | null;
  pushSuccess: string | null;
  addQuery: string;
  selectedToAdd: OfferItem | null;
  addDropdownOpen: boolean;
}

function formatFilters(filters: StreamFilterItem[]): string {
  if (!filters || filters.length === 0) {
    return "filter by None";
  }
  return filters
    .map((f) => {
      const vals = Array.isArray(f.payload)
        ? f.payload.join(", ")
        : f.payload
          ? String(f.payload)
          : "";
      return `${f.name} (${f.mode || "accept"}): ${vals || "—"}`;
    })
    .join(" · ");
}

function toDraftOffers(
  stream: StreamInfo,
  previousOffers: DraftOffer[] = []
): DraftOffer[] {
  const serverIds = new Set(stream.offers.map((o) => o.offer_id));
  const current: DraftOffer[] = stream.offers.map((o) => ({
    offer_id: o.offer_id,
    name: o.name,
    share: o.share,
    pinned: false,
    removed: o.state !== "active",
    country: o.country ?? [],
  }));

  // Сохраняем ранее известные офферы, исчезнувшие из Keitaro, как (removed) для возможности BRING BACK
  for (const prev of previousOffers) {
    if (!serverIds.has(prev.offer_id)) {
      current.push({
        ...prev,
        share: 0,
        pinned: false,
        removed: true,
      });
    }
  }
  return current;
}

/** Редактор существующей кампании: потоки, локальный draft, Pin, REMOVE/BRING BACK, PUSH TO KT. */
export function CampaignEditor({
  meta,
  initialCampaignId,
}: CampaignEditorProps) {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [campaignFilter, setCampaignFilter] = useState("");
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(
    initialCampaignId
  );

  const [streamsData, setStreamsData] = useState<CampaignStreamsResponse | null>(
    null
  );
  const [streamsLoading, setStreamsLoading] = useState(false);
  const [streamsError, setStreamsError] = useState<string | null>(null);
  const [showAllOffers, setShowAllOffers] = useState(true);

  const [streamStates, setStreamStates] = useState<Record<number, StreamState>>(
    {}
  );

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      const list = await api.listCampaigns();
      setCampaigns(list);
      setSelectedCampaignId((prev) => {
        if (prev && list.some((c) => c.id === prev)) return prev;
        return list.length > 0 ? list[0].id : null;
      });
    } catch (err) {
      setStreamsError(
        err instanceof Error ? err.message : "Не удалось загрузить список кампаний"
      );
    } finally {
      setCampaignsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);

  useEffect(() => {
    if (initialCampaignId !== null) {
      setSelectedCampaignId(initialCampaignId);
    }
  }, [initialCampaignId]);

  const fetchStreamsFromKt = useCallback(async (campaignId: number) => {
    setStreamsLoading(true);
    setStreamsError(null);
    try {
      const data = await api.getCampaignStreams(campaignId);
      setStreamsData(data);
      setStreamStates((prev) => {
        const next: Record<number, StreamState> = {};
        for (const stream of data.streams) {
          const prevOffers = prev[stream.id]?.draft ?? [];
          const offers = toDraftOffers(stream, prevOffers);
          next[stream.id] = {
            baseline: offers,
            draft: offers,
            validationError: null,
            pushing: false,
            pushError: null,
            pushSuccess: null,
            addQuery: "",
            selectedToAdd: null,
            addDropdownOpen: false,
          };
        }
        return next;
      });
    } catch (err) {
      setStreamsError(
        err instanceof Error ? err.message : "Не удалось загрузить потоки из Keitaro"
      );
    } finally {
      setStreamsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCampaignId !== null) {
      void fetchStreamsFromKt(selectedCampaignId);
    }
  }, [selectedCampaignId, fetchStreamsFromKt]);

  const filteredCampaigns = useMemo(() => {
    const q = campaignFilter.trim().toLowerCase();
    if (!q) return campaigns;
    return campaigns.filter(
      (c) =>
        String(c.id).includes(q) ||
        c.name.toLowerCase().includes(q) ||
        (c.alias ?? "").toLowerCase().includes(q)
    );
  }, [campaigns, campaignFilter]);

  const updateStreamDraft = (
    streamId: number,
    updater: (prevDraft: DraftOffer[], prevState: StreamState) => {
      offers: DraftOffer[];
      extra?: Partial<StreamState>;
      recalculate?: boolean;
    }
  ) => {
    setStreamStates((prev) => {
      const current = prev[streamId];
      if (!current) return prev;
      const { offers, extra, recalculate = true } = updater(current.draft, current);
      const calc = recalculate
        ? recalculateDraftShares(offers)
        : { offers, error: null };
      return {
        ...prev,
        [streamId]: {
          ...current,
          ...extra,
          draft: calc.offers,
          validationError: calc.error,
          pushError: null,
          pushSuccess: null,
        },
      };
    });
  };

  const handleTogglePin = (streamId: number, offerId: number) => {
    updateStreamDraft(streamId, (draft) => ({
      offers: draft.map((o) =>
        o.offer_id === offerId ? { ...o, pinned: !o.pinned } : o
      ),
    }));
  };

  const handleShareChange = (streamId: number, offerId: number, raw: string) => {
    const parsed = raw === "" ? 0 : Math.max(0, Math.min(100, Math.trunc(Number(raw))));
    updateStreamDraft(streamId, (draft) => ({
      offers: draft.map((o) =>
        o.offer_id === offerId
          ? { ...o, share: Number.isNaN(parsed) ? 0 : parsed, pinned: true }
          : o
      ),
    }));
  };

  const handleRemoveOffer = (streamId: number, offerId: number) => {
    updateStreamDraft(streamId, (draft) => ({
      offers: draft.map((o) =>
        o.offer_id === offerId
          ? { ...o, removed: true, pinned: false, share: 0 }
          : o
      ),
    }));
  };

  const handleBringBackOffer = (streamId: number, offerId: number) => {
    updateStreamDraft(streamId, (draft) => ({
      offers: draft.map((o) =>
        o.offer_id === offerId
          ? { ...o, removed: false, pinned: false }
          : o
      ),
    }));
  };

  const handleAddOffer = (streamId: number) => {
    const st = streamStates[streamId];
    if (!st?.selectedToAdd) return;
    const picked = st.selectedToAdd;
    updateStreamDraft(streamId, (draft) => {
      const existing = draft.find((o) => o.offer_id === picked.id);
      const nextOffers = existing
        ? draft.map((o) =>
            o.offer_id === picked.id
              ? { ...o, removed: false, pinned: false }
              : o
          )
        : [
            ...draft,
            {
              offer_id: picked.id,
              name: picked.name,
              share: 0,
              pinned: false,
              removed: false,
              country: picked.country ?? [],
            },
          ];
      return {
        offers: nextOffers,
        extra: {
          addQuery: "",
          selectedToAdd: null,
          addDropdownOpen: false,
        },
      };
    });
  };

  const handleCancelDraft = (streamId: number) => {
    setStreamStates((prev) => {
      const current = prev[streamId];
      if (!current) return prev;
      return {
        ...prev,
        [streamId]: {
          ...current,
          draft: current.baseline,
          validationError: null,
          pushError: null,
          pushSuccess: null,
        },
      };
    });
  };

  const handlePushToKt = async (streamId: number) => {
    if (!selectedCampaignId) return;
    const current = streamStates[streamId];
    if (!current || current.validationError) return;

    const activeOffers = current.draft.filter((o) => !o.removed);
    if (activeOffers.length === 0) return;

    setStreamStates((prev) => ({
      ...prev,
      [streamId]: {
        ...prev[streamId],
        pushing: true,
        pushError: null,
        pushSuccess: null,
      },
    }));

    try {
      await api.updateStreamOffers(
        selectedCampaignId,
        streamId,
        activeOffers.map((o) => ({
          offer_id: o.offer_id,
          share: o.share,
          state: "active",
        }))
      );
      setStreamStates((prev) => {
        const st = prev[streamId];
        if (!st) return prev;
        return {
          ...prev,
          [streamId]: {
            ...st,
            baseline: st.draft,
            pushing: false,
            pushSuccess: "Изменения сохранены в Keitaro",
          },
        };
      });
    } catch (err) {
      // При ошибке API сохраняем draft, чтобы пользователь не потерял изменения
      setStreamStates((prev) => {
        const st = prev[streamId];
        if (!st) return prev;
        return {
          ...prev,
          [streamId]: {
            ...st,
            pushing: false,
            pushError:
              err instanceof Error
                ? err.message
                : "Ошибка при отправке изменений в Keitaro",
          },
        };
      });
    }
  };

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Часть 2 · Редактор кампании</p>
            <h1 className="page-title">Управление потоками и долями офферов</h1>
            <p className="muted-copy">
              Изменяйте состав и доли офферов в черновике с мгновенным пересчётом до 100%,
              затем отправляйте изменения через <code>PUSH TO KT</code>.
            </p>
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!selectedCampaignId || streamsLoading}
              onClick={() =>
                selectedCampaignId && void fetchStreamsFromKt(selectedCampaignId)
              }
            >
              {streamsLoading ? "Загрузка…" : "FETCH STREAMS FROM KT"}
            </button>
            {streamsData?.campaign.keitaro_url && (
              <a
                className="btn btn-secondary"
                href={streamsData.campaign.keitaro_url}
                target="_blank"
                rel="noreferrer"
              >
                VIEW IN KT ↗
              </a>
            )}
          </div>
        </div>

        <div className="editor-toolbar">
          <div className="field">
            <label htmlFor="cmp-search">Поиск кампании (ID, имя, алиас)</label>
            <input
              id="cmp-search"
              type="text"
              placeholder="Фильтр списка кампаний…"
              value={campaignFilter}
              onChange={(e) => setCampaignFilter(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="cmp-select">Кампания</label>
            <select
              id="cmp-select"
              disabled={campaignsLoading || filteredCampaigns.length === 0}
              value={selectedCampaignId ?? ""}
              onChange={(e) =>
                setSelectedCampaignId(e.target.value ? Number(e.target.value) : null)
              }
            >
              {filteredCampaigns.length === 0 && (
                <option value="">
                  {campaignsLoading ? "Загрузка кампаний…" : "Кампании не найдены"}
                </option>
              )}
              {filteredCampaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} · {c.name} {c.alias ? `(${c.alias})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="toolbar-toggle">
            <label className="checkbox-pill">
              <input
                type="checkbox"
                checked={showAllOffers}
                onChange={(e) => setShowAllOffers(e.target.checked)}
              />
              <span>SHOW ALL OFFERS</span>
            </label>
          </div>
        </div>

        {streamsError && (
          <div className="alert alert-danger" style={{ marginTop: 14 }} role="alert">
            {streamsError}
          </div>
        )}
      </section>

      {streamsData && streamsData.streams.length === 0 && !streamsLoading && (
        <section className="card">
          <p className="muted-copy">У выбранной кампании пока нет потоков.</p>
        </section>
      )}

      {streamsData?.streams.map((stream) => {
        const st = streamStates[stream.id];
        const isLandings = stream.schema === "landings";
        const dirty = st ? isStreamDraftDirty(st.draft, st.baseline) : false;

        const visibleOffers = st
          ? st.draft.filter((o) => showAllOffers || !o.removed)
          : [];
        const activeSum = st
          ? st.draft
              .filter((o) => !o.removed)
              .reduce((acc, o) => acc + o.share, 0)
          : 0;

        const activeOfferIds = new Set(
          st ? st.draft.filter((o) => !o.removed).map((o) => o.offer_id) : []
        );
        const addCandidates = (meta?.offers ?? [])
          .filter((offer) => {
            if (activeOfferIds.has(offer.id)) return false;
            const q = (st?.addQuery ?? "").trim().toLowerCase();
            if (!q) return true;
            return (
              String(offer.id).includes(q) ||
              offer.name.toLowerCase().includes(q)
            );
          })
          .slice(0, 50);

        return (
          <section
            key={stream.id}
            className={`card ${dirty ? "dirty-card" : ""}`}
          >
            <div className="card-head">
              <div>
                <div className="btn-row" style={{ marginBottom: 6 }}>
                  <span className="status-badge">
                    {stream.type || "stream"} · {stream.schema || "unknown"}
                  </span>
                  <span className="mono-id">stream_id: {stream.id}</span>
                  {dirty && (
                    <span className="status-badge status-warning">
                      Несохранённые изменения
                    </span>
                  )}
                </div>
                <h2 className="stream-title">
                  Stream: {stream.name}
                  {stream.position !== null && stream.position !== undefined
                    ? ` (#${stream.position})`
                    : ""}
                </h2>
                <p className="muted-copy">{formatFilters(stream.filters)}</p>
              </div>

              {isLandings && st && (dirty || st.pushing) && (
                <div className="btn-row">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={Boolean(st.validationError) || st.pushing || activeSum !== 100}
                    onClick={() => void handlePushToKt(stream.id)}
                  >
                    {st.pushing ? "Отправка…" : "PUSH TO KT"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={st.pushing}
                    onClick={() => handleCancelDraft(stream.id)}
                  >
                    CANCEL
                  </button>
                </div>
              )}
            </div>

            {!isLandings ? (
              <div className="url-box">
                <span className="muted-copy">
                  Действие ({stream.action_type || "redirect"}):
                </span>
                <code>{stream.action_payload || "—"}</code>
              </div>
            ) : st ? (
              <div className="stack">
                {st.validationError && (
                  <div className="alert alert-danger" role="alert">
                    {st.validationError}
                  </div>
                )}
                {st.pushError && (
                  <div className="alert alert-danger" role="alert">
                    <strong>Ошибка PUSH TO KT:</strong> {st.pushError}. Черновик сохранён.
                  </div>
                )}
                {st.pushSuccess && (
                  <div className="alert alert-success" role="status">
                    {st.pushSuccess}
                  </div>
                )}

                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Offer</th>
                        <th style={{ width: 170 }}>
                          Share (сумма: {activeSum}%)
                        </th>
                        <th style={{ width: 140 }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleOffers.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="muted-copy">
                            Нет отображаемых офферов.
                          </td>
                        </tr>
                      ) : (
                        visibleOffers.map((offer) => (
                          <tr
                            key={offer.offer_id}
                            className={offer.removed ? "row-removed" : ""}
                          >
                            <td>
                              <div className="offer-cell">
                                <span className="mono-id">#{offer.offer_id}</span>
                                <span>{offer.name}</span>
                                {offer.removed && (
                                  <span className="tag">(removed)</span>
                                )}
                              </div>
                            </td>
                            <td>
                              <div className="share-cell">
                                <input
                                  type="number"
                                  min={0}
                                  max={100}
                                  disabled={offer.removed}
                                  aria-label={`Доля для оффера ${offer.name}`}
                                  className="share-input"
                                  value={offer.share}
                                  onChange={(e) =>
                                    handleShareChange(
                                      stream.id,
                                      offer.offer_id,
                                      e.target.value
                                    )
                                  }
                                />
                                <span className="muted-copy">%</span>
                                <button
                                  type="button"
                                  disabled={offer.removed}
                                  aria-label={
                                    offer.pinned
                                      ? `Открепить долю ${offer.name}`
                                      : `Закрепить долю ${offer.name}`
                                  }
                                  title={
                                    offer.pinned
                                      ? "Доля закреплена (Pin)"
                                      : "Закрепить долю (Pin)"
                                  }
                                  aria-pressed={offer.pinned}
                                  className={`pin-btn ${offer.pinned ? "pinned" : ""}`}
                                  onClick={() =>
                                    handleTogglePin(stream.id, offer.offer_id)
                                  }
                                >
                                  <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 17v5M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" />
                                  </svg>
                                </button>
                              </div>
                            </td>
                            <td>
                              {offer.removed ? (
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={() =>
                                    handleBringBackOffer(stream.id, offer.offer_id)
                                  }
                                >
                                  BRING BACK
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="btn btn-danger btn-sm"
                                  onClick={() =>
                                    handleRemoveOffer(stream.id, offer.offer_id)
                                  }
                                >
                                  REMOVE
                                </button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="add-offer-row">
                  <div className="autocomplete" style={{ flex: 1 }}>
                    <input
                      type="text"
                      className="inline-input"
                      placeholder="Поиск оффера по ID или названию для добавления…"
                      aria-label="Поиск оффера для добавления в поток"
                      value={st.addQuery}
                      onFocus={() =>
                        setStreamStates((prev) => ({
                          ...prev,
                          [stream.id]: {
                            ...prev[stream.id],
                            addDropdownOpen: true,
                          },
                        }))
                      }
                      onChange={(e) => {
                        const val = e.target.value;
                        setStreamStates((prev) => ({
                          ...prev,
                          [stream.id]: {
                            ...prev[stream.id],
                            addQuery: val,
                            selectedToAdd: null,
                            addDropdownOpen: true,
                          },
                        }));
                      }}
                    />
                    {st.addDropdownOpen && meta && (
                      <ul className="autocomplete-list" role="listbox">
                        {addCandidates.length === 0 ? (
                          <li className="autocomplete-empty">
                            Подходящие офферы не найдены
                          </li>
                        ) : (
                          addCandidates.map((offer) => (
                            <li key={offer.id}>
                              <button
                                type="button"
                                className="autocomplete-item"
                                onClick={() =>
                                  setStreamStates((prev) => ({
                                    ...prev,
                                    [stream.id]: {
                                      ...prev[stream.id],
                                      selectedToAdd: offer,
                                      addQuery: `[${offer.id}] ${offer.name}`,
                                      addDropdownOpen: false,
                                    },
                                  }))
                                }
                              >
                                <span className="mono-id">#{offer.id}</span>
                                <span className="offer-title">{offer.name}</span>
                              </button>
                            </li>
                          ))
                        )}
                      </ul>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={!st.selectedToAdd}
                    onClick={() => handleAddOffer(stream.id)}
                  >
                    ADD
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
