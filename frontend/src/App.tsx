import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import { BulkOperations } from "./components/BulkOperations";
import { CampaignCreator } from "./components/CampaignCreator";
import { CampaignEditor } from "./components/CampaignEditor";
import { Logo } from "./components/Logo";
import { OperationLogs } from "./components/OperationLogs";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import type { MetaResponse, PendingRollback } from "./types";

type ActiveTab = "creator" | "editor" | "bulk" | "logs";

interface HealthState {
  status: string;
  database: string;
  demo_mode?: boolean;
}

/** Главный компонент приложения с навигацией и загрузкой справочников Keitaro. */
export function App() {
  const [tab, setTab] = useState<ActiveTab>("creator");
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(
    null
  );
  const [pendingRollback, setPendingRollback] =
    useState<PendingRollback | null>(null);

  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthError, setHealthError] = useState(false);

  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getHealth()
      .then((data) => {
        setHealth(data);
        setHealthError(data.status !== "ok");
      })
      .catch(() => setHealthError(true));
  }, []);

  const loadMeta = useCallback(async (refresh = false) => {
    setMetaLoading(true);
    setMetaError(null);
    try {
      const data = await api.getMeta(refresh);
      setMeta(data);
    } catch (err) {
      setMetaError(
        err instanceof ApiError
          ? err.message
          : "Не удалось загрузить справочники Keitaro"
      );
    } finally {
      setMetaLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMeta(false);
  }, [loadMeta]);

  const isDemoMode = Boolean(meta?.demo_mode || health?.demo_mode);
  const dotClass = healthError ? "err" : health?.status === "ok" ? "ok" : "";
  const statusLabel = healthError
    ? "API недоступен"
    : health
      ? `API: ${health.status} · БД: ${health.database}`
      : "Проверка API…";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <Logo />
          <span className="brand-text">
            <strong>KT Studio</strong>
            <small>Кампании и потоки Keitaro</small>
          </span>
        </a>

        <nav className="nav-tabs" aria-label="Разделы приложения">
          <button
            type="button"
            className={`nav-tab ${tab === "creator" ? "active" : ""}`}
            onClick={() => setTab("creator")}
          >
            Создание
          </button>
          <button
            type="button"
            className={`nav-tab ${tab === "editor" ? "active" : ""}`}
            onClick={() => setTab("editor")}
          >
            Управление
          </button>
          <button
            type="button"
            className={`nav-tab ${tab === "bulk" ? "active" : ""}`}
            onClick={() => setTab("bulk")}
          >
            Массовые
          </button>
          <button
            type="button"
            className={`nav-tab ${tab === "logs" ? "active" : ""}`}
            onClick={() => setTab("logs")}
          >
            Журнал
          </button>
        </nav>

        <div className="topbar-right">
          {isDemoMode && (
            <span
              className="status-badge status-warning"
              title="Встроенный in-memory mock Keitaro (DEMO_MODE=true)"
            >
              DEMO MODE
            </span>
          )}
          <div className="health-badge" aria-live="polite">
            <span className={`health-dot ${dotClass}`} aria-hidden="true" />
            <span>{statusLabel}</span>
          </div>
          <ThemeSwitcher />
        </div>
      </header>

      <main className="main-container">
        {tab === "creator" && (
          <CampaignCreator
            meta={meta}
            metaLoading={metaLoading}
            metaError={metaError}
            onReloadMeta={(refresh = true) => void loadMeta(refresh)}
            onCreated={(created) => setSelectedCampaignId(created.id)}
            onOpenInEditor={(campaignId) => {
              setSelectedCampaignId(campaignId);
              setTab("editor");
            }}
          />
        )}
        {tab === "editor" && (
          <CampaignEditor
            meta={meta}
            initialCampaignId={selectedCampaignId}
            pendingRollback={pendingRollback}
            onClearPendingRollback={() => setPendingRollback(null)}
          />
        )}
        {tab === "bulk" && (
          <BulkOperations
            meta={meta}
            onOpenInEditor={(campaignId) => {
              setSelectedCampaignId(campaignId);
              setTab("editor");
            }}
          />
        )}
        {tab === "logs" && (
          <OperationLogs
            onRollbackToSnapshot={(rollback) => {
              setPendingRollback(rollback);
              setSelectedCampaignId(rollback.campaignId);
              setTab("editor");
            }}
          />
        )}
      </main>
    </div>
  );
}
