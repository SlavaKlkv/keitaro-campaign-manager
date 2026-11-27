import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type {
  BulkCampaignCreateItem,
  BulkCampaignCreateResponse,
  BulkOfferReplaceApplyResponse,
  BulkOfferReplacePreviewResponse,
  CampaignSummary,
  CloneGeosResponse,
  MetaResponse,
} from "../types";

interface BulkOperationsProps {
  meta: MetaResponse | null;
  onOpenInEditor: (campaignId: number) => void;
}

function parseBulkLines(raw: string): {
  items: BulkCampaignCreateItem[];
  error: string | null;
} {
  const lines = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return { items: [], error: "Введите хотя бы одну строку: Название, GEO, Offer ID" };
  }

  const items: BulkCampaignCreateItem[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const parts = lines[i].split(/[;,|\t]/).map((p) => p.trim());
    if (parts.length < 3) {
      return {
        items: [],
        error: `Строка ${i + 1}: ожидается формат «Название, GEO, Offer ID»`,
      };
    }
    const [name, rawGeo, rawOfferId, alias] = parts;
    const geo = rawGeo.toUpperCase();
    const offerId = Number(rawOfferId);
    if (!name) {
      return { items: [], error: `Строка ${i + 1}: пустое название кампании` };
    }
    if (!/^[A-Z]{2}$/.test(geo)) {
      return {
        items: [],
        error: `Строка ${i + 1}: некорректный GEO '${rawGeo}' (нужно 2 латинские буквы)`,
      };
    }
    if (!Number.isInteger(offerId) || offerId <= 0) {
      return {
        items: [],
        error: `Строка ${i + 1}: некорректный Offer ID '${rawOfferId}'`,
      };
    }
    items.push({
      name,
      country_code: geo,
      offer_id: offerId,
      alias: alias || null,
    });
  }
  return { items, error: null };
}

/** Массовые операции для байеров: Bulk Create, Clone to GEOs, Bulk Offer Replace. */
export function BulkOperations({ meta, onOpenInEditor }: BulkOperationsProps) {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);

  // --- 1. Bulk Create ---
  const [bulkText, setBulkText] = useState(
    "Offer_Test_DE, DE, 18004\nOffer_Test_ES, ES, 18005"
  );
  const [domainId, setDomainId] = useState<string>("");
  const [groupId, setGroupId] = useState<string>("");
  const [trafficSourceId, setTrafficSourceId] = useState<string>("");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [bulkResult, setBulkResult] =
    useState<BulkCampaignCreateResponse | null>(null);

  // --- 2. Clone to GEOs ---
  const [cloneCampaignId, setCloneCampaignId] = useState<string>("");
  const [cloneGeosRaw, setCloneGeosRaw] = useState("DE, FR, ES");
  const [cloneSubmitting, setCloneSubmitting] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [cloneResult, setCloneResult] = useState<CloneGeosResponse | null>(null);

  // --- 3. Bulk Offer Replace ---
  const [sourceOfferId, setSourceOfferId] = useState<string>("");
  const [replaceMode, setReplaceMode] = useState<"replace" | "disable">(
    "replace"
  );
  const [targetOfferId, setTargetOfferId] = useState<string>("");
  const [replaceLoading, setReplaceLoading] = useState(false);
  const [replaceError, setReplaceError] = useState<string | null>(null);
  const [replacePreview, setReplacePreview] =
    useState<BulkOfferReplacePreviewResponse | null>(null);
  const [replaceApplyResult, setReplaceApplyResult] =
    useState<BulkOfferReplaceApplyResponse | null>(null);

  const loadCampaigns = useCallback(async () => {
    try {
      const list = await api.listCampaigns();
      setCampaigns(list);
      setCloneCampaignId((prev) =>
        prev && list.some((c) => String(c.id) === prev)
          ? prev
          : list.length > 0
            ? String(list[0].id)
            : ""
      );
    } catch {
      /* Список подгрузится позже при наличии подключения */
    }
  }, []);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);

  useEffect(() => {
    if (!meta) return;
    if (!domainId && meta.defaults.domain_id) {
      setDomainId(String(meta.defaults.domain_id));
    }
    if (!groupId && meta.defaults.group_id) {
      setGroupId(String(meta.defaults.group_id));
    }
    if (!trafficSourceId && meta.defaults.traffic_source_id) {
      setTrafficSourceId(String(meta.defaults.traffic_source_id));
    }
    if (!sourceOfferId && meta.offers.length > 0) {
      setSourceOfferId(String(meta.offers[0].id));
    }
    if (!targetOfferId && meta.offers.length > 1) {
      setTargetOfferId(String(meta.offers[1].id));
    }
  }, [meta, domainId, groupId, trafficSourceId, sourceOfferId, targetOfferId]);

  const handleBulkCreate = async (e: FormEvent) => {
    e.preventDefault();
    setBulkError(null);
    setBulkResult(null);

    const parsed = parseBulkLines(bulkText);
    if (parsed.error) {
      setBulkError(parsed.error);
      return;
    }

    setBulkSubmitting(true);
    try {
      const res = await api.bulkCreateCampaigns({
        domain_id: Number(domainId),
        group_id: Number(groupId),
        traffic_source_id: Number(trafficSourceId),
        items: parsed.items,
      });
      setBulkResult(res);
      void loadCampaigns();
    } catch (err) {
      setBulkError(
        err instanceof Error ? err.message : "Ошибка пакетного создания"
      );
    } finally {
      setBulkSubmitting(false);
    }
  };

  const handleCloneGeos = async (e: FormEvent) => {
    e.preventDefault();
    setCloneError(null);
    setCloneResult(null);

    const geos = cloneGeosRaw
      .split(/[\s,;]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (geos.length === 0) {
      setCloneError("Укажите хотя бы один GEO-код через запятую.");
      return;
    }

    setCloneSubmitting(true);
    try {
      const res = await api.cloneCampaignToGeos(Number(cloneCampaignId), geos);
      setCloneResult(res);
      void loadCampaigns();
    } catch (err) {
      setCloneError(
        err instanceof Error ? err.message : "Ошибка клонирования на GEO"
      );
    } finally {
      setCloneSubmitting(false);
    }
  };

  const handlePreviewReplace = async () => {
    setReplaceError(null);
    setReplacePreview(null);
    setReplaceApplyResult(null);
    setReplaceLoading(true);
    try {
      const res = await api.previewBulkOfferReplace({
        source_offer_id: Number(sourceOfferId),
        target_offer_id:
          replaceMode === "replace" ? Number(targetOfferId) : null,
      });
      setReplacePreview(res);
    } catch (err) {
      setReplaceError(
        err instanceof Error ? err.message : "Ошибка предпросмотра замены"
      );
    } finally {
      setReplaceLoading(false);
    }
  };

  const handleApplyReplace = async () => {
    setReplaceError(null);
    setReplaceLoading(true);
    try {
      const res = await api.applyBulkOfferReplace({
        source_offer_id: Number(sourceOfferId),
        target_offer_id:
          replaceMode === "replace" ? Number(targetOfferId) : null,
      });
      setReplaceApplyResult(res);
      setReplacePreview(null);
    } catch (err) {
      setReplaceError(
        err instanceof Error ? err.message : "Ошибка применения массовой замены"
      );
    } finally {
      setReplaceLoading(false);
    }
  };

  return (
    <div className="stack">
      {/* 1. Bulk Create */}
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Массовый запуск</p>
            <h1 className="page-title">Bulk Create (пакетное создание)</h1>
            <p className="muted-copy">
              Вставьте список строк в формате{" "}
              <code>Название, GEO, Offer ID</code> (по одной на строке). Каждая
              строка обрабатывается независимо.
            </p>
          </div>
        </div>

        <form className="form-grid" onSubmit={handleBulkCreate}>
          <div className="field field-span-2">
            <label htmlFor="bulk-lines">Список кампаний</label>
            <textarea
              id="bulk-lines"
              rows={5}
              className="bulk-textarea"
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              placeholder={"Camp_DE, DE, 18004\nCamp_ES, ES, 18005"}
            />
          </div>

          <div className="field">
            <label htmlFor="bulk-domain">Домен</label>
            <select
              id="bulk-domain"
              required
              value={domainId}
              onChange={(e) => setDomainId(e.target.value)}
              disabled={!meta}
            >
              {meta?.domains.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} (#{d.id})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="bulk-group">Группа</label>
            <select
              id="bulk-group"
              required
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              disabled={!meta}
            >
              {meta?.groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} (#{g.id})
                </option>
              ))}
            </select>
          </div>

          <div className="field field-span-2">
            <label htmlFor="bulk-source">Источник трафика</label>
            <select
              id="bulk-source"
              required
              value={trafficSourceId}
              onChange={(e) => setTrafficSourceId(e.target.value)}
              disabled={!meta}
            >
              {meta?.traffic_sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (#{s.id})
                </option>
              ))}
            </select>
          </div>

          {bulkError && (
            <div className="alert alert-danger field-span-2" role="alert">
              {bulkError}
            </div>
          )}

          <div className="form-actions field-span-2">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={bulkSubmitting || !meta}
            >
              {bulkSubmitting ? "Создание пакета…" : "Создать кампании"}
            </button>
          </div>
        </form>

        {bulkResult && (
          <div className="stack" style={{ marginTop: "1rem" }}>
            <div className="alert alert-success">
              Обработано: {bulkResult.total} · Успешно: {bulkResult.succeeded} ·
              Ошибок: {bulkResult.failed}
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Название</th>
                    <th>GEO</th>
                    <th>Offer</th>
                    <th>Статус</th>
                    <th>Ссылки</th>
                  </tr>
                </thead>
                <tbody>
                  {bulkResult.results.map((r) => (
                    <tr key={r.index}>
                      <td className="mono-id">{r.index + 1}</td>
                      <td>{r.name}</td>
                      <td>{r.country_code}</td>
                      <td className="mono-id">#{r.offer_id}</td>
                      <td>
                        <span
                          className={`status-badge ${
                            r.status === "success"
                              ? "status-success"
                              : "status-danger"
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td>
                        {r.status === "success" && r.campaign_id ? (
                          <div className="btn-row">
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => onOpenInEditor(r.campaign_id!)}
                            >
                              Редактор #{r.campaign_id}
                            </button>
                            {r.keitaro_url && (
                              <a
                                className="btn btn-secondary btn-sm"
                                href={r.keitaro_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                VIEW IN KT ↗
                              </a>
                            )}
                          </div>
                        ) : (
                          <span className="muted-cell">{r.error}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* 2. Clone to GEOs */}
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Мульти-GEO</p>
            <h2 className="page-title">Clone to GEOs (клонирование на пачку GEO)</h2>
            <p className="muted-copy">
              Копирует настройки и потоки выбранной кампании для каждого GEO,
              подменяя фильтр страны в Flow 1 и суффикс в имени.
            </p>
          </div>
        </div>

        <form className="form-grid" onSubmit={handleCloneGeos}>
          <div className="field">
            <label htmlFor="clone-cmp">Исходная кампания</label>
            <select
              id="clone-cmp"
              value={cloneCampaignId}
              onChange={(e) => setCloneCampaignId(e.target.value)}
              disabled={campaigns.length === 0}
            >
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} · {c.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="clone-geos">Список GEO (через запятую)</label>
            <input
              id="clone-geos"
              type="text"
              value={cloneGeosRaw}
              onChange={(e) => setCloneGeosRaw(e.target.value)}
              placeholder="DE, FR, ES, IT"
            />
          </div>

          {cloneError && (
            <div className="alert alert-danger field-span-2" role="alert">
              {cloneError}
            </div>
          )}

          <div className="form-actions field-span-2">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={cloneSubmitting || !cloneCampaignId}
            >
              {cloneSubmitting ? "Клонирование…" : "Clone to GEOs"}
            </button>
          </div>
        </form>

        {cloneResult && (
          <div className="table-wrap" style={{ marginTop: "1rem" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>GEO</th>
                  <th>Кампания</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {cloneResult.results.map((r) => (
                  <tr key={r.country_code}>
                    <td>
                      <strong>{r.country_code}</strong>
                    </td>
                    <td>{r.name ?? "—"}</td>
                    <td>
                      <span
                        className={`status-badge ${
                          r.status === "success"
                            ? "status-success"
                            : "status-danger"
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td>
                      {r.status === "success" && r.campaign_id ? (
                        <div className="btn-row">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => onOpenInEditor(r.campaign_id!)}
                          >
                            Открыть #{r.campaign_id}
                          </button>
                          {r.keitaro_url && (
                            <a
                              className="btn btn-secondary btn-sm"
                              href={r.keitaro_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              VIEW IN KT ↗
                            </a>
                          )}
                        </div>
                      ) : (
                        <span className="muted-cell">{r.error}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 3. Bulk Offer Replace */}
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Ротация по всем кампаниям</p>
            <h2 className="page-title">
              Bulk Offer Replace (замена / отключение оффера)
            </h2>
            <p className="muted-copy">
              Находит все активные потоки с указанным оффером, перераспределяет
              доли до 100% и показывает предпросмотр до применения.
            </p>
          </div>
        </div>

        <div className="form-grid-3">
          <div className="field">
            <label htmlFor="replace-src">Заменяемый оффер</label>
            <select
              id="replace-src"
              value={sourceOfferId}
              onChange={(e) => setSourceOfferId(e.target.value)}
              disabled={!meta}
            >
              {meta?.offers.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} · {o.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="replace-mode">Режим</label>
            <select
              id="replace-mode"
              value={replaceMode}
              onChange={(e) =>
                setReplaceMode(e.target.value as "replace" | "disable")
              }
            >
              <option value="replace">Заменить на другой оффер</option>
              <option value="disable">Отключить в потоках</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="replace-dst">Целевой оффер</label>
            <select
              id="replace-dst"
              value={targetOfferId}
              onChange={(e) => setTargetOfferId(e.target.value)}
              disabled={!meta || replaceMode === "disable"}
            >
              {meta?.offers.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} · {o.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="btn-row" style={{ marginTop: "1rem" }}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={replaceLoading || !sourceOfferId}
            onClick={() => void handlePreviewReplace()}
          >
            {replaceLoading ? "Расчёт…" : "Предпросмотр"}
          </button>
          {replacePreview && replacePreview.affected_streams.length > 0 && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={replaceLoading}
              onClick={() => void handleApplyReplace()}
            >
              Применить ({replacePreview.affected_streams.length} пот.)
            </button>
          )}
        </div>

        {replaceError && (
          <div
            className="alert alert-danger"
            style={{ marginTop: "0.875rem" }}
            role="alert"
          >
            {replaceError}
          </div>
        )}

        {replacePreview && (
          <div className="stack" style={{ marginTop: "1rem" }}>
            {replacePreview.affected_streams.length === 0 ? (
              <p className="muted-copy">
                Подходящих потоков для изменения не найдено.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Кампания</th>
                      <th>Поток</th>
                      <th>Изменение долей (было → стало)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {replacePreview.affected_streams.map((s) => (
                      <tr key={s.stream_id}>
                        <td>
                          #{s.campaign_id} · {s.campaign_name}
                        </td>
                        <td>
                          #{s.stream_id} · {s.stream_name}
                        </td>
                        <td>
                          <ul className="diff-list">
                            {s.diff.map((d) => (
                              <li key={d.offer_id} className="diff-item">
                                <span className="mono-id">#{d.offer_id}</span>{" "}
                                <span>{d.name}:</span>{" "}
                                {d.before_share ?? 0}% →{" "}
                                <strong>{d.after_share ?? 0}%</strong>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {replacePreview.skipped_streams.length > 0 && (
              <div className="alert alert-warning">
                <div>
                  <strong>
                    Пропущено потоков ({replacePreview.skipped_streams.length}):
                  </strong>
                  <ul className="diff-list">
                    {replacePreview.skipped_streams.map((sk) => (
                      <li key={sk.stream_id} className="diff-item">
                        Кампания #{sk.campaign_id}, поток #{sk.stream_id}:{" "}
                        {sk.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}

        {replaceApplyResult && (
          <div
            className="alert alert-success"
            style={{ marginTop: "1rem" }}
            role="status"
          >
            Применено потоков: {replaceApplyResult.succeeded} из{" "}
            {replaceApplyResult.total_streams} (ошибок:{" "}
            {replaceApplyResult.failed})
          </div>
        )}
      </section>
    </div>
  );
}
