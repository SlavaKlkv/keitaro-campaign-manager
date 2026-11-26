import { useEffect, useState } from "react";
import { Logo } from "./components/Logo";
import { ThemeSwitcher } from "./components/ThemeSwitcher";

interface HealthState {
  status: string;
  database: string;
}

/** Базовый каркас приложения с проверкой подключения к API и БД. */
export function App() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    fetch("/health")
      .then((res) => res.json())
      .then((data: HealthState) => {
        setHealth(data);
        setHealthError(data.status !== "ok");
      })
      .catch(() => setHealthError(true));
  }, []);

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
        <div className="topbar-right">
          <div className="health-badge" aria-live="polite">
            <span className={`health-dot ${dotClass}`} aria-hidden="true" />
            <span>{statusLabel}</span>
          </div>
          <ThemeSwitcher />
        </div>
      </header>
      <main>
        <section className="card">
          <h1>Инфраструктура готова</h1>
          <p>Создаватор кампаний и редактор потоков будут добавлены на следующих этапах.</p>
        </section>
      </main>
    </div>
  );
}
