import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  CampaignHealthSummary,
  CampaignStreamsResponse,
  CampaignSummary,
  MetaResponse,
  OfferItem,
  OfferStatsItem,
  PendingRollback,
  StatsPeriod,
  StreamFilterItem,
  StreamInfo,
} from "../types";
import {
  isStreamDraftDirty,
  rebalanceByPerformance,
  recalculateDraftShares,
  type DraftOffer,
  type OfferPerformanceMetric,
} from "../utils/weights";

interface CampaignEditorProps {
  meta: MetaResponse | null;
  initialCampaignId: number | null;
  pendingRollback?: PendingRollback | null;
  onClearPendingRollback?: () => void;
}

interface StreamState {
  baseline: DraftOffer[];
  draft: DraftOffer[];
  validationError: string | null;
  pushing: boolean;
  pushError: string | null;
  pushSuccess: string | null;
  rollbackNotice: string | null;
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
      return `${f.name || "filter"} (${f.mode || "accept"}): ${vals || "—"}`;
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
    name: o.name || `Offer #${o.offer_id}`,
    share: o.state === "active" ? o.share : 0,
    pinned: false,
    removed: o.state !== "active",
    country: o.country ?? [],
    removedExternally: Boolean(o.removed_externally),
  }));

  // Сохраняем ранее известные офферы в текущей сессии, исчезнувшие из Keitaro, как (removed)
  for (const prev of previousOffers) {
    if (!serverIds.has(prev.offer_id)) {
      current.push({
        ...prev,
        share: 0,
        pinned: false,
        removed: true,
        removedExternally: true,
      });
    }
  }
  return current;
}

const PERIOD_LABELS: Record<StatsPeriod, string> = {
  today: "Сегодня",
  "7d": "7 дней",
  "30d": "30 дней",
};

/** Редактор существующей кампании: потоки, аналитика, аудит здоровья, ребалансировка, PUSH TO KT. */
export function CampaignEditor({
  meta,
  initialCampaignId,
  pendingRollback = null,
  onClearPendingRollback,
}: CampaignEditorProps) {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignsHealth, setCampaignsHealth] = useState<
    Record<string, CampaignHealthSummary>
  >({});
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

  const [period, setPeriod] = useState<StatsPeriod>("7d");
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsByOffer, setStatsByOffer] = useState<
    Record<number, OfferStatsItem>
  >({});
  const [minClicks, setMinClicks] = useState<number>(30);

  const [streamStates, setStreamStates] = useState<Record<number, StreamState>>(
    {}
  );

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      const [list, healthMap] = await Promise.all([
        api.listCampaigns(),
        api.getCampaignsHealth().catch(() => ({})),
      ]);
      setCampaigns(list);
      setCampaignsHealth(healthMap);
      setSelectedCampaignId((prev) => {
        if (prev && list.some((c) => c.id === prev)) return prev;
        return list.length > 0 ? list[0].id : null;
      });
    } catch (err) {
      setStreamsError(
        err instanceof Error
          ? err.message
          : "Не удалось загрузить список кампаний"
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

  const fetchStats = useCallback(
    async (campaignId: number, targetPeriod: StatsPeriod) => {
      setStatsLoading(true);
      setStatsError(null);
      try {
        const resp = await api.getCampaignStats(campaignId, targetPeriod);
        const mapped: Record<number, OfferStatsItem> = {};
        for (const item of resp.offers) {
          mapped[item.offer_id] = item;
        }
        setStatsByOffer(mapped);
      } catch (err) {
        setStatsError(
          err instanceof Error
            ? err.message
            : "Не удалось загрузить статистику офферов"
        );
      } finally {
        setStatsLoading(false);
      }
    },
    []
  );

  const fetchStreamsFromKt = useCallback(async (campaignId: number) => {
    setStreamsLoading(true);
    setStreamsError(null);
    try {
      const data = await api.getCampaignStreams(campaignId);
      setStreamsData(data);
      if (data.health) {
        setCampaignsHealth((prev) => ({
          ...prev,
          [String(campaignId)]: data.health!,
        }));
      }
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
            rollbackNotice: null,
            addQuery: "",
            selectedToAdd: null,
            addDropdownOpen: false,
          };
        }
        return next;
      });
    } catch (err) {
      setStreamsError(
        err instanceof Error
          ? err.message
          : "Не удалось загрузить потоки из Keitaro"
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

  useEffect(() => {
    if (selectedCampaignId !== null) {
      void fetchStats(selectedCampaignId, period);
    }
  }, [selectedCampaignId, period, fetchStats]);

  // Применяем откат к снимку из журнала в черновик соответствующего потока
  useEffect(() => {
    if (!pendingRollback || !streamsData) return;
    if (streamsData.campaign.id !== pendingRollback.campaignId) return;
    const targetStream = streamsData.streams.find(
      (s) => s.id === pendingRollback.streamId
    );
    if (!targetStream) return;

    setStreamStates((prev) => {
      const st = prev[pendingRollback.streamId];
      if (!st) return prev;

      const snapshotActiveMap = new Map(
        pendingRollback.offers
          .filter((o) => o.state !== "disabled")
          .map((o) => [o.offer_id, o])
      );

      const nextDraft: DraftOffer[] = [];
      const seenIds = new Set<number>();

      for (const item of pendingRollback.offers) {
        seenIds.add(item.offer_id);
        const active = item.state !== "disabled";
        nextDraft.push({
          offer_id: item.offer_id,
          name: item.name || `Offer #${item.offer_id}`,
          share: active ? item.share : 0,
          pinned: false,
          removed: !active,
          country: [],
        });
      }

      for (const baseItem of st.baseline) {
        if (
          !seenIds.has(baseItem.offer_id) &&
          !snapshotActiveMap.has(baseItem.offer_id)
        ) {
          nextDraft.push({
            ...baseItem,
            share: 0,
            pinned: false,
            removed: true,
          });
        }
      }

      const activeSum = nextDraft
        .filter((o) => !o.removed)
        .reduce((acc, o) => acc + o.share, 0);
      const validationError =
        activeSum !== 100
          ? `Сумма долей снимка равна ${activeSum}% вместо 100%. Скорректируйте доли перед PUSH TO KT.`
          : null;

      return {
        ...prev,
        [pendingRollback.streamId]: {
          ...st,
          draft: nextDraft,
          validationError,
          pushError: null,
          pushSuccess: null,
          rollbackNotice: `В черновик загружен снимок из журнала #${pendingRollback.logId} (${pendingRollback.label}). Проверьте изменения и нажмите PUSH TO KT.`,
        },
      };
    });

    onClearPendingRollback?.();
  }, [pendingRollback, streamsData, onClearPendingRollback]);

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

  const anyPushing = useMemo(
    () => Object.values(streamStates).some((s) => s.pushing),
    [streamStates]
  );

  const metricsMap = useMemo(() => {
    const res: Record<number, OfferPerformanceMetric> = {};
    for (const [k, v] of Object.entries(statsByOffer)) {
      res[Number(k)] = {
        offer_id: v.offer_id,
        clicks: v.clicks,
        conversions: v.conversions,
        cr: v.cr,
        epc: v.epc,
        revenue: v.revenue,
      };
    }
    return res;
  }, [statsByOffer]);

  const updateStreamDraft = (
    streamId: number,
    updater: (
      prevDraft: DraftOffer[],
      prevState: StreamState
    ) => {
      offers: DraftOffer[];
      extra?: Partial<StreamState>;
      fixedOfferId?: number;
    }
  ) => {
    setStreamStates((prev) => {
      const current = prev[streamId];
      if (!current || current.pushing) return prev;
      const { offers, extra, fixedOfferId } = updater(current.draft, current);
      const calc = recalculateDraftShares(offers, fixedOfferId);
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

  const handleShareChange = (
    streamId: number,
    offerId: number,
    raw: string
  ) => {
    const parsed =
      raw === "" ? 0 : Math.max(0, Math.min(100, Math.trunc(Number(raw))));
    const nextShare = Number.isNaN(parsed) ? 0 : parsed;
    updateStreamDraft(streamId, (draft) => ({
      offers: draft.map((o) =>
        o.offer_id === offerId ? { ...o, share: nextShare } : o
      ),
      fixedOfferId: offerId,
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
          ? { ...o, removed: false, pinned: false, removedExternally: false }
          : o
      ),
    }));
  };

  const handleAddOffer = (streamId: number) => {
    const st = streamStates[streamId];
    if (!st?.selectedToAdd || st.pushing) return;
    const picked = st.selectedToAdd;
    updateStreamDraft(streamId, (draft) => {
      const existing = draft.find((o) => o.offer_id === picked.id);
      const nextOffers = existing
        ? draft.map((o) =>
            o.offer_id === picked.id
              ? { ...o, removed: false, pinned: false, removedExternally: false }
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

  const handleRebalanceStream = (streamId: number) => {
    setStreamStates((prev) => {
      const current = prev[streamId];
      if (!current || current.pushing) return prev;
      const res = rebalanceByPerformance(current.draft, metricsMap, minClicks);
      return {
        ...prev,
        [streamId]: {
          ...current,
          draft: res.offers,
          validationError: res.error,
          pushError: null,
          pushSuccess: null,
        },
      };
    });
  };

  const handleCancelDraft = (streamId: number) => {
    setStreamStates((prev) => {
      const current = prev[streamId];
      if (!current || current.pushing) return prev;
      return {
        ...prev,
        [streamId]: {
          ...current,
          draft: current.baseline,
          validationError: null,
          pushError: null,
          pushSuccess: null,
          rollbackNotice: null,
        },
      };
    });
  };

  const handlePushToKt = async (streamId: number) => {
    if (!selectedCampaignId) return;
    const current = streamStates[streamId];
    if (!current || current.pushing || current.validationError) return;

    const activeOffers = current.draft.filter((o) => !o.removed);
    if (activeOffers.length === 0) return;

    const sentSnapshot = current.draft.map((item) => ({ ...item }));

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
        }))
      );
      setStreamStates((prev) => {
        const st = prev[streamId];
        if (!st) return prev;
        return {
          ...prev,
          [streamId]: {
            ...st,
            baseline: sentSnapshot,
            pushing: false,
            rollbackNotice: null,
            pushSuccess: "Изменения сохранены в Keitaro",
          },
        };
      });
      // Обновляем health после сохранения потоков
      void fetchStreamsFromKt(selectedCampaignId);
    } catch (err) {
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

  const activeHealth = streamsData?.health;

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Настройка кампании</p>
            <h1 className="page-title">Потоки, аналитика и офферы</h1>
            <p className="muted-copy">
              Изменяйте состав и доли офферов в черновике с мгновенным
              пересчётом до 100%, анализируйте статистику и отправляйте
              изменения через <code>PUSH TO KT</code>.
            </p>
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!selectedCampaignId || streamsLoading || anyPushing}
              onClick={() => {
                if (!selectedCampaignId) return;
                void fetchStreamsFromKt(selectedCampaignId);
                void fetchStats(selectedCampaignId, period);
              }}
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
              disabled={
                campaignsLoading || filteredCampaigns.length === 0 || anyPushing
              }
              value={selectedCampaignId ?? ""}
              onChange={(e) =>
                setSelectedCampaignId(
                  e.target.value ? Number(e.target.value) : null
                )
              }
            >
              {filteredCampaigns.length === 0 && (
                <option value="">
                  {campaignsLoading
                    ? "Загрузка кампаний…"
                    : "Кампании не найдены"}
                </option>
              )}
              {filteredCampaigns.map((c) => {
                const h = campaignsHealth[String(c.id)];
                const prefix =
                  h?.status === "error"
                    ? "[!] "
                    : h?.status === "warning"
                      ? "[~] "
                      : "";
                return (
                  <option key={c.id} value={c.id}>
                    {prefix}#{c.id} · {c.name} {c.alias ? `(${c.alias})` : ""}
                  </option>
                );
              })}
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

        <div className="analytics-bar">
          <div className="btn-row">
            <span className="muted-copy">Период статистики:</span>
            <div className="period-pills" role="group" aria-label="Период статистики">
              {(["today", "7d", "30d"] as StatsPeriod[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip-btn ${period === p ? "active" : ""}`}
                  disabled={statsLoading}
                  onClick={() => setPeriod(p)}
                >
                  {PERIOD_LABELS[p]}
                </button>
              ))}
            </div>
            {statsLoading && (
              <span className="muted-copy">Загрузка статистики…</span>
            )}
          </div>

          <div className="btn-row">
            <label className="muted-copy" htmlFor="min-clicks-input">
              Мин. кликов (от шума):
            </label>
            <input
              id="min-clicks-input"
              type="number"
              min={0}
              max={100000}
              className="share-input"
              value={minClicks}
              onChange={(e) =>
                setMinClicks(Math.max(0, Math.trunc(Number(e.target.value) || 0)))
              }
            />
            {activeHealth && (
              <span
                className={`status-badge ${
                  activeHealth.status === "ok"
                    ? "status-success"
                    : activeHealth.status === "warning"
                      ? "status-warning"
                      : "status-danger"
                }`}
              >
                Health:{" "}
                {activeHealth.status === "ok"
                  ? "OK"
                  : `${activeHealth.issues.length} пробл.`}
              </span>
            )}
          </div>
        </div>

        {activeHealth && activeHealth.issues.length > 0 && (
          <div
            className={`alert ${
              activeHealth.status === "error" ? "alert-danger" : "alert-warning"
            }`}
            style={{ marginTop: "0.875rem" }}
            role="status"
          >
            <div>
              <strong>Pre-flight / Health Audit:</strong>
              <ul className="diff-list">
                {activeHealth.issues.map((issue, idx) => (
                  <li key={`${issue.code}-${idx}`} className="diff-item">
                    <span>{issue.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {statsError && (
          <div
            className="alert alert-warning"
            style={{ marginTop: "0.875rem" }}
            role="status"
          >
            Статистика недоступна: {statsError}
          </div>
        )}

        {streamsError && (
          <div
            className="alert alert-danger"
            style={{ marginTop: "0.875rem" }}
            role="alert"
          >
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
                <div className="btn-row" style={{ marginBottom: "0.375rem" }}>
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

              <div className="btn-row">
                {isLandings && st && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={st.pushing || statsLoading}
                    onClick={() => handleRebalanceStream(stream.id)}
                  >
                    Rebalance by performance
                  </button>
                )}
                {isLandings && st && (dirty || st.pushing) && (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={
                        Boolean(st.validationError) ||
                        st.pushing ||
                        activeSum !== 100
                      }
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
                  </>
                )}
              </div>
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
                {st.rollbackNotice && (
                  <div className="alert alert-warning" role="status">
                    {st.rollbackNotice}
                  </div>
                )}
                {st.validationError && (
                  <div className="alert alert-danger" role="alert">
                    {st.validationError}
                  </div>
                )}
                {st.pushError && (
                  <div className="alert alert-danger" role="alert">
                    <strong>Ошибка PUSH TO KT:</strong> {st.pushError}.
                    Черновик сохранён.
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
                        <th className="num-col">Clicks</th>
                        <th className="num-col">Conv</th>
                        <th className="num-col">CR</th>
                        <th className="num-col">EPC</th>
                        <th className="num-col">Rev</th>
                        <th style={{ width: "10.625rem" }}>
                          Share (сумма: {activeSum}%)
                        </th>
                        <th style={{ width: "8.75rem" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleOffers.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="muted-copy">
                            Нет отображаемых офферов.
                          </td>
                        </tr>
                      ) : (
                        visibleOffers.map((offer) => {
                          const stat = statsByOffer[offer.offer_id];
                          return (
                            <tr
                              key={offer.offer_id}
                              className={offer.removed ? "row-removed" : ""}
                            >
                              <td>
                                <div className="offer-cell">
                                  <span className="mono-id">
                                    #{offer.offer_id}
                                  </span>
                                  <span>{offer.name}</span>
                                  {offer.removed && (
                                    <span className="tag">(removed)</span>
                                  )}
                                  {offer.removed && offer.removedExternally && (
                                    <span className="status-badge status-warning">
                                      удалён в KT
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="num-col">
                                {stat ? stat.clicks : "—"}
                              </td>
                              <td className="num-col">
                                {stat ? stat.conversions : "—"}
                              </td>
                              <td className="num-col">
                                {stat ? `${stat.cr.toFixed(2)}%` : "—"}
                              </td>
                              <td className="num-col">
                                {stat ? stat.epc.toFixed(3) : "—"}
                              </td>
                              <td className="num-col">
                                {stat ? stat.revenue.toFixed(2) : "—"}
                              </td>
                              <td>
                                <div className="share-cell">
                                  <input
                                    type="number"
                                    min={0}
                                    max={100}
                                    disabled={offer.removed || st.pushing}
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
                                    disabled={offer.removed || st.pushing}
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
                                    className={`pin-btn ${
                                      offer.pinned ? "pinned" : ""
                                    }`}
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
                                    disabled={st.pushing}
                                    onClick={() =>
                                      handleBringBackOffer(
                                        stream.id,
                                        offer.offer_id
                                      )
                                    }
                                  >
                                    BRING BACK
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn btn-danger btn-sm"
                                    disabled={st.pushing}
                                    onClick={() =>
                                      handleRemoveOffer(
                                        stream.id,
                                        offer.offer_id
                                      )
                                    }
                                  >
                                    REMOVE
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })
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
                      disabled={st.pushing}
                      value={st.addQuery}
                      onFocus={() => {
                        if (st.pushing) return;
                        setStreamStates((prev) => ({
                          ...prev,
                          [stream.id]: {
                            ...prev[stream.id],
                            addDropdownOpen: true,
                          },
                        }));
                      }}
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
                    {st.addDropdownOpen && !st.pushing && meta && (
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
                                <span className="offer-title">
                                  {offer.name}
                                </span>
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
                    disabled={!st.selectedToAdd || st.pushing}
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
