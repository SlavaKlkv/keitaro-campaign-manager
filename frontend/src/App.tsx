import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import { CampaignCreator } from "./components/CampaignCreator";
import { Logo } from "./components/Logo";
import { OperationLogs } from "./components/OperationLogs";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import type { MetaResponse } from "./types";

type ActiveTab = "creator" | "editor" | "logs";

interface HealthState {
  status: string;
  database: string;
}

/** Главный компонент приложения с навигацией, проверкой здоровья и загрузкой справочников. */
export function App() {
  const [tab, setTab] = useState<ActiveTab>("creator");
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(
    null
  );

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

  const loadMeta = useCallback(async () => {
    setMetaLoading(true);
    setMetaError(null);
    try {
      const data = await api.getMeta();
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
    void loadMeta();
  }, [loadMeta]);

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
            <strong>Keitaro Campaign Manager</strong>
            <small>Управление кампаниями и потоками</small>
          </span>
        </a>

        <nav className="nav-tabs" aria-label="Разделы приложения">
          <button
            type="button"
            className={`nav-tab ${tab === "creator" ? "active" : ""}`}
            onClick={() => setTab("creator")}
          >
            Создаватор
          </button>
          <button
            type="button"
            className={`nav-tab ${tab === "editor" ? "active" : ""}`}
            onClick={() => setTab("editor")}
          >
            Редактор
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
            onReloadMeta={() => void loadMeta()}
            onCreated={(created) => setSelectedCampaignId(created.id)}
            onOpenInEditor={(campaignId) => {
              setSelectedCampaignId(campaignId);
              setTab("editor");
            }}
          />
        )}
        {tab === "editor" && (
          <section className="card">
            <div className="section-head">
              <div>
                <h1>Редактор кампании</h1>
                <p className="subtitle">
                  {selectedCampaignId
                    ? `Выбрана кампания #${selectedCampaignId}. Интерфейс редактора потоков и офферов подключается на этапе 4.`
                    : "Интерфейс редактора потоков и офферов подключается на этапе 4."}
                </p>
              </div>
            </div>
          </section>
        )}
        {tab === "logs" && <OperationLogs />}
      </main>
    </div>
  );
}
