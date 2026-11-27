import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type {
  CampaignCreateResponse,
  MetaResponse,
  OfferItem,
} from "../types";

interface CampaignCreatorProps {
  meta: MetaResponse | null;
  metaLoading: boolean;
  metaError: string | null;
  onReloadMeta: () => void;
  onCreated: (campaign: CampaignCreateResponse) => void;
  onOpenInEditor: (campaignId: number) => void;
}

const QUICK_GEO_CODES = ["AU", "RO", "MX", "DE", "PL", "ES", "IT", "FR", "GB"];

/** Форма создания кампании с двумя потоками (Geo → Google и выбранный оффер 100%). */
export function CampaignCreator({
  meta,
  metaLoading,
  metaError,
  onReloadMeta,
  onCreated,
  onOpenInEditor,
}: CampaignCreatorProps) {
  const [name, setName] = useState("");
  const [countryCode, setCountryCode] = useState("AU");
  const [alias, setAlias] = useState("");
  const [domainId, setDomainId] = useState<string>("");
  const [groupId, setGroupId] = useState<string>("");
  const [trafficSourceId, setTrafficSourceId] = useState<string>("");

  const [offerQuery, setOfferQuery] = useState("");
  const [selectedOffer, setSelectedOffer] = useState<OfferItem | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [createdResult, setCreatedResult] =
    useState<CampaignCreateResponse | null>(null);

  const offerBoxRef = useRef<HTMLDivElement>(null);

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
  }, [meta, domainId, groupId, trafficSourceId]);

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (
        offerBoxRef.current &&
        !offerBoxRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const filteredOffers = useMemo(() => {
    if (!meta) return [];
    const q = offerQuery.trim().toLowerCase();
    const list = meta.offers;
    if (!q) return list.slice(0, 60);
    return list
      .filter(
        (offer) =>
          String(offer.id).includes(q) || offer.name.toLowerCase().includes(q)
      )
      .slice(0, 60);
  }, [meta, offerQuery]);

  const handleSelectOffer = (offer: OfferItem) => {
    setSelectedOffer(offer);
    setOfferQuery(`[${offer.id}] ${offer.name}`);
    setDropdownOpen(false);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (!selectedOffer) {
      setSubmitError("Выберите оффер из выпадающего списка автокомплита.");
      return;
    }

    const cleanGeo = countryCode.trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(cleanGeo)) {
      setSubmitError(
        "Geo-код должен состоять ровно из 2 латинских букв (например, AU, RO, MX)."
      );
      return;
    }

    setSubmitting(true);
    try {
      const result = await api.createCampaign({
        name: name.trim(),
        country_code: cleanGeo,
        offer_id: selectedOffer.id,
        domain_id: Number(domainId),
        group_id: Number(groupId),
        traffic_source_id: Number(trafficSourceId),
        alias: alias.trim() ? alias.trim() : null,
      });
      setCreatedResult(result);
      onCreated(result);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Не удалось создать кампанию"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Создание кампании</p>
            <h1 className="page-title">Новая кампания</h1>
            <p className="muted-copy">
              Создаёт кампанию с ротацией «По позиции» и моделью затрат CPC:
              Flow 1 перехватывает выбранное гео и редиректит на{" "}
              <code>https://google.com</code>, Flow 2 ведёт на выбранный оффер
              (100%).
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onReloadMeta}
            disabled={metaLoading}
          >
            {metaLoading ? "Обновление…" : "Обновить справочники"}
          </button>
        </div>

        {metaError && (
          <div className="alert alert-danger" role="alert">
            <span>{metaError}</span>
          </div>
        )}

        <form className="form-grid" onSubmit={handleSubmit}>
          <div className="field field-span-2">
            <label htmlFor="cmp-name">Name (название кампании)</label>
            <input
              id="cmp-name"
              type="text"
              required
              maxLength={120}
              placeholder="Например: AU Beauty Offer Test"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="cmp-geo">Geo (ISO-2 код страны)</label>
            <div className="geo-row">
              <input
                id="cmp-geo"
                type="text"
                required
                maxLength={2}
                placeholder="AU"
                value={countryCode}
                onChange={(e) =>
                  setCountryCode(e.target.value.toUpperCase().slice(0, 2))
                }
              />
              <div className="geo-chips" aria-label="Быстрый выбор гео">
                {QUICK_GEO_CODES.map((code) => (
                  <button
                    key={code}
                    type="button"
                    className={`chip-btn ${
                      countryCode === code ? "active" : ""
                    }`}
                    onClick={() => setCountryCode(code)}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="field">
            <label htmlFor="cmp-alias">Alias / Идентификатор (опционально)</label>
            <input
              id="cmp-alias"
              type="text"
              maxLength={80}
              pattern="[A-Za-z0-9_-]*"
              placeholder="Сгенерируется автоматически, если пусто"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
            />
          </div>

          <div className="field field-span-2" ref={offerBoxRef}>
            <label htmlFor="cmp-offer">Offer (поиск по ID или названию)</label>
            <div className="autocomplete">
              <input
                id="cmp-offer"
                type="text"
                autoComplete="off"
                placeholder={
                  metaLoading
                    ? "Загрузка офферов из Keitaro…"
                    : "Начните вводить ID или название оффера…"
                }
                value={offerQuery}
                onFocus={() => setDropdownOpen(true)}
                onChange={(e) => {
                  setOfferQuery(e.target.value);
                  setSelectedOffer(null);
                  setDropdownOpen(true);
                }}
              />
              {selectedOffer && (
                <span className="selected-pill">
                  Выбран оффер #{selectedOffer.id}
                </span>
              )}
              {dropdownOpen && meta && (
                <ul className="autocomplete-list" role="listbox">
                  {filteredOffers.length === 0 ? (
                    <li className="autocomplete-empty">Офферы не найдены</li>
                  ) : (
                    filteredOffers.map((offer) => (
                      <li key={offer.id}>
                        <button
                          type="button"
                          className={`autocomplete-item ${
                            selectedOffer?.id === offer.id ? "selected" : ""
                          }`}
                          onClick={() => handleSelectOffer(offer)}
                        >
                          <span className="mono-id">#{offer.id}</span>
                          <span className="offer-title">{offer.name}</span>
                          {offer.country.length > 0 && (
                            <span className="tag">
                              {offer.country.join(", ")}
                            </span>
                          )}
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
          </div>

          <div className="field">
            <label htmlFor="cmp-domain">Домен</label>
            <select
              id="cmp-domain"
              required
              value={domainId}
              onChange={(e) => setDomainId(e.target.value)}
              disabled={!meta || meta.domains.length === 0}
            >
              {!meta && <option value="">Загрузка…</option>}
              {meta?.domains.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} (#{d.id})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="cmp-group">Группа</label>
            <select
              id="cmp-group"
              required
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              disabled={!meta || meta.groups.length === 0}
            >
              {!meta && <option value="">Загрузка…</option>}
              {meta?.groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} (#{g.id})
                </option>
              ))}
            </select>
          </div>

          <div className="field field-span-2">
            <label htmlFor="cmp-source">Источник трафика</label>
            <select
              id="cmp-source"
              required
              value={trafficSourceId}
              onChange={(e) => setTrafficSourceId(e.target.value)}
              disabled={!meta || meta.traffic_sources.length === 0}
            >
              {!meta && <option value="">Загрузка…</option>}
              {meta?.traffic_sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (#{s.id})
                </option>
              ))}
            </select>
          </div>

          {submitError && (
            <div className="alert alert-danger field-span-2" role="alert">
              {submitError}
            </div>
          )}

          <div className="form-actions field-span-2">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !meta}
            >
              {submitting ? "Создание кампании…" : "Create campaign"}
            </button>
          </div>
        </form>
      </section>

      {createdResult && (
        <section className="card result-card" aria-live="polite">
          <div className="card-head">
            <div>
              <span className="status-badge status-success">
                Кампания создана
              </span>
              <h2>
                #{createdResult.id} · {createdResult.name}
              </h2>
              <p className="muted-copy">
                Алиас: <code>{createdResult.alias}</code> · Geo:{" "}
                <code>{createdResult.country_code}</code> · Потоков:{" "}
                <strong>{createdResult.streams_created}</strong>
              </p>
            </div>
            <div className="btn-row">
              <a
                className="btn btn-secondary"
                href={createdResult.keitaro_url}
                target="_blank"
                rel="noreferrer"
              >
                VIEW IN KT ↗
              </a>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onOpenInEditor(createdResult.id)}
              >
                Настроить кампанию
              </button>
            </div>
          </div>

          {createdResult.tracking_url && (
            <div className="url-box">
              <span className="muted-copy">Tracking URL:</span>
              <code>{createdResult.tracking_url}</code>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
