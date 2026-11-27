<h1 align="center">Keitaro Campaign Manager</h1>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&amp;logoColor=white" alt="Python 3.14"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&amp;logoColor=white" alt="FastAPI 0.115+"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 16"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&amp;logoColor=black" alt="React 18"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&amp;logoColor=white" alt="TypeScript 5.6"></a>
  <a href="https://vite.dev/"><img src="https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite&amp;logoColor=white" alt="Vite 5.4"></a>
  <a href="https://docs.docker.com/compose/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose"></a>
</p>

<p align="center">
  <strong>KT Studio</strong> — веб-сервис для быстрого создания рекламных кампаний и управления потоками и долями офферов в трекере <strong>Keitaro</strong> через Admin API v1.
</p>

---

## Демо

https://github.com/user-attachments/assets/dd3ae24f-67e3-489e-a4a1-aad7956017eb

*Переключение тем (тёмная → светлая → системная) → создание кампании (`Geo` `ES` → `AU`, автокомплит `Offer`) → переход в управление потоками (`Настроить кампанию`) → добавление офферов (`ADD`) → ввод `Share` и закрепление `Pin` с пересчётом `38% / 37% / 25%` → отправка в трекер (`PUSH TO KT`) → удаление и откат черновика (`REMOVE` → `CANCEL`) → журнал операций в PostgreSQL.*

Локальная запись: [`docs/assets/demo.mp4`](docs/assets/demo.mp4) · Что осталось за кадром: [`SCREENCAST_NOTES.md`](SCREENCAST_NOTES.md).

## Архитектура

```mermaid
flowchart LR
    UI["KT Studio UI<br/>React 18 · TypeScript · Vite / Nginx"]
    API["Backend API<br/>FastAPI · SQLAlchemy · httpx"]
    KT["Keitaro Admin API v1"]
    DB[("PostgreSQL 16<br/>operation_logs")]

    UI <-->|"REST JSON"| API
    API <-->|"Кампании, потоки, справочники"| KT
    API -->|"Аудит изменений"| DB
```

| Эндпоинт | Назначение |
| --- | --- |
| `GET /health` | Проверка состояния API и подключения к PostgreSQL |
| `GET /api/meta` | Справочники Keitaro: домены, группы, источники трафика и офферы |
| `GET /api/campaigns` | Список кампаний Keitaro |
| `POST /api/campaigns` | Создание кампании с двумя потоками и запись в журнал |
| `GET /api/campaigns/{id}/streams` | Загрузка потоков и офферов выбранной кампании |
| `PUT /api/campaigns/{id}/streams/{stream_id}` | Обновление состава и долей офферов потока в Keitaro |
| `DELETE /api/campaigns/{id}` | Удаление кампании из Keitaro |
| `GET /api/logs` | История операций из таблицы `operation_logs` |

## Возможности

| Раздел интерфейса | Как работает |
| --- | --- |
| **Создание** | Поля `Name`, `Geo` (ISO-2 код страны), автокомплит `Offer` по ID/названию, выбор домена, группы и источника трафика со значениями по умолчанию. Создаёт кампанию с ротацией «По позиции» (`type: "position"`) и моделью затрат `CPC`: **Flow 1** фильтрует выбранную страну (`accept`) и редиректит на `https://google.com`, **Flow 2** ведёт трафик на выбранный оффер со `100%` веса. Возвращает ссылку `VIEW IN KT` и кнопку `Настроить кампанию`. |
| **Управление** | Поиск кампании по ID/имени/алиасу, `FETCH STREAMS FROM KT`, `VIEW IN KT`, переключатель `SHOW ALL OFFERS`. Все правки живут в локальном черновике (`draft`) с подсветкой изменений: `ADD` добавляет оффер, `REMOVE` переводит долю в `0%` со статусом `(removed)` и кнопкой `BRING BACK`. Закрепление `Pin` и ручной ввод `Share` делят остаток `100 - sum(pinned)` поровну между незакреплёнными активными офферами с распределением `+1%` сверху вниз. При `sum(pinned) > 100%` или сумме активных долей `!= 100%` кнопка `PUSH TO KT` блокируется; при ошибке API черновик сохраняется; `CANCEL` откатывает правки. |
| **Журнал** | Просмотр истории создания кампаний и обновлений потоков из таблицы `operation_logs` в PostgreSQL. |

## Быстрый старт (Docker Compose)

1. Скопируйте [`.env.example`](.env.example) в `.env` и заполните `KEITARO_BASE_URL` и `KEITARO_API_KEY`:

```bash
cp .env.example .env
```

2. Запустите PostgreSQL, backend и frontend одной командой (миграции Alembic применяются автоматически при старте `backend`):

```bash
docker compose up --build -d
```

| Сервис / поверхность | Адрес |
| --- | --- |
| Веб-интерфейс (`frontend`, Nginx) | `http://localhost:5173` |
| Backend API и Swagger UI | `http://localhost:8000/docs` |
| Healthcheck API и БД | `http://localhost:8000/health` |

### Переменные окружения

| Переменная | Назначение | Значение по умолчанию в [`.env.example`](.env.example) |
| --- | --- | --- |
| `KEITARO_BASE_URL` | Базовый URL трекера Keitaro (суффиксы `/admin`, `/admin_api/v1` нормализуются автоматически) | `https://keitaro-for-tests.etolegko.com` |
| `KEITARO_API_KEY` | Ключ Admin API v1 Keitaro | `""` |
| `POSTGRES_DB` | Имя базы данных PostgreSQL | `keitaro_manager` |
| `POSTGRES_USER` | Пользователь PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | `postgres` |
| `DATABASE_URL` | Строка подключения SQLAlchemy (в Docker Compose переопределяется на сервис `postgres`) | `postgresql+psycopg://postgres:postgres@localhost:5432/keitaro_manager` |
| `BACKEND_PORT` | Внешний порт контейнера `backend` | `8000` |
| `FRONTEND_PORT` | Внешний порт контейнера `frontend` | `5173` |
| `VITE_API_BASE_URL` | Адрес backend API для локального Vite dev-сервера | `http://localhost:8000` |

## Локальная разработка и тесты

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Запуск unit- и API-тестов (изолированы от живого Keitaro через `httpx.MockTransport` и in-memory SQLite):

```bash
cd backend
pytest -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Проверка типов и production-сборка:

```bash
cd frontend
npm run build
```

### Миграции Alembic

Создать новую миграцию (из каталога `backend/`):

```bash
alembic revision --autogenerate -m "описание изменений"
```

Применить миграции:

```bash
alembic upgrade head
```

## Структура проекта

```text
keitaro-campaign-manager/
├── backend/
│   ├── alembic/                 # Миграции Alembic (operation_logs)
│   ├── app/
│   │   ├── routers/             # health, meta, campaigns, logs
│   │   ├── services/            # Расчёт и округление весов офферов
│   │   ├── config.py            # Конфигурация и нормализация KEITARO_BASE_URL
│   │   ├── database.py          # Подключение SQLAlchemy и запись логов
│   │   ├── keitaro.py           # Асинхронный клиент Keitaro Admin API
│   │   ├── main.py              # Приложение FastAPI и CORS
│   │   ├── models.py            # ORM-модель OperationLog
│   │   └── schemas.py           # Pydantic-схемы API
│   ├── tests/
│   │   ├── unit/                # Unit-тесты конфига, клиента и весов
│   │   └── api/                 # API-тесты с подменённым клиентом Keitaro
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── public/favicon.svg
│   ├── src/
│   │   ├── api/client.ts
│   │   ├── components/          # CampaignCreator, CampaignEditor, OperationLogs, ThemeSwitcher, Logo
│   │   ├── styles/              # tokens.css, global.css
│   │   └── utils/weights.ts
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── scripts/record_demo.py       # Скрипт записи демо-ролика через Playwright
├── .env.example
└── docker-compose.yml
```
