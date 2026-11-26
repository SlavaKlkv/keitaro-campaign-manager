import { useEffect, useState } from "react";

type ThemeMode = "dark" | "light" | "system";

const STORAGE_KEY = "kcm-theme";

function resolveTheme(mode: ThemeMode): "dark" | "light" {
  if (mode === "system") {
    return window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }
  return mode;
}

function applyTheme(mode: ThemeMode): void {
  const resolved = resolveTheme(mode);
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = resolved;
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.setAttribute("content", resolved);
  }
}

/** Иконочный переключатель темы (тёмная / светлая / системная) без текстовых подписей. */
export function ThemeSwitcher() {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const attr = document.documentElement.dataset.themeMode;
    if (attr === "dark" || attr === "light" || attr === "system") {
      return attr;
    }
    return "system";
  });

  useEffect(() => {
    applyTheme(mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* Игнорируем недоступность localStorage */
    }
  }, [mode]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => {
      if (mode === "system") {
        applyTheme("system");
      }
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [mode]);

  return (
    <div className="theme-switch" role="group" aria-label="Тема оформления">
      <button
        type="button"
        className="theme-option"
        aria-label="Тёмная тема"
        title="Тёмная тема"
        aria-pressed={mode === "dark"}
        onClick={() => setMode("dark")}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            className="theme-solid"
            d="M18.75 15.75A8.25 8.25 0 0 1 8.25 5.25a8.25 8.25 0 1 0 10.5 10.5Z"
          />
        </svg>
      </button>
      <button
        type="button"
        className="theme-option"
        aria-label="Светлая тема"
        title="Светлая тема"
        aria-pressed={mode === "light"}
        onClick={() => setMode("light")}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.4M12 19.1v2.4M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7" />
        </svg>
      </button>
      <button
        type="button"
        className="theme-option"
        aria-label="Системная тема"
        title="Системная тема"
        aria-pressed={mode === "system"}
        onClick={() => setMode("system")}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8.5" />
          <path className="theme-solid" d="M12 3.5a8.5 8.5 0 0 1 0 17z" />
        </svg>
      </button>
    </div>
  );
}
