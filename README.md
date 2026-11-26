# Keitaro Campaign Manager

Веб-сервис для быстрого создания рекламных кампаний и управления потоками/офферами в трекере **Keitaro** через Admin API v1.

## Стек

- **Backend:** Python 3.13+, FastAPI, SQLAlchemy 2.x, Alembic, `httpx`, `pydantic-settings`
- **База данных:** PostgreSQL 16 (`psycopg`) — журнал операций `operation_logs`
- **Frontend:** React 18, TypeScript, Vite (монохромный UI с тёмной/светлой/системной темой и SVG-логотипом)
- **Инфраструктура:** Docker Compose (`postgres`, `backend`, `frontend` на Nginx)

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
├── .env.example
└── docker-compose.yml
```

## Возможности

### 1. Создаватор кампаний
- Поля: `Name`, `Geo` (ISO-2 код страны), `Offer` (автокомплит по ID и названию), выбор домена, группы и источника трафика с подставленными значениями по умолчанию.
- Создаёт кампанию в Keitaro с ротацией потоков «По позиции» (`type: "position"`) и моделью затрат `CPC`:
  - **Flow 1:** фильтр по выбранной стране (`accept`) → редирект на `https://google.com`.
  - **Flow 2:** выбранный оффер со 100% веса.
- Возвращает прямую ссылку в админку Keitaro (`VIEW IN KT`) и позволяет сразу перейти в редактор.

### 2. Редактор существующей кампании
- Выбор кампании с поиском по ID/имени/алиасу, `FETCH STREAMS FROM KT`, `VIEW IN KT`, переключатель `SHOW ALL OFFERS`.
- Отображение метаданных потоков (`stream_id`, фильтры) и локальный черновик (`draft`) на каждый поток с визуальной подсветкой несохранённых изменений.
- Операции с офферами: поиск по ID/названию + `ADD`, `REMOVE` (`0%`, серый стиль, статус `(removed)`, кнопка `BRING BACK`), `BRING BACK`.
- Закрепление долей (`Pin`) и ручное редактирование `Share`: остаток `100 - sum(pinned)` делится поровну между активными незакреплёнными офферами с распределением остатка `+1%` сверху вниз; при `sum(pinned) > 100%` кнопка `PUSH TO KT` блокируется с сообщением об ошибке.
- `PUSH TO KT` обновляет поток через `PUT /streams/{id}` (при ошибке API черновик сохраняется) и фиксирует операцию в PostgreSQL; `CANCEL` откатывает черновик к последнему загруженному состоянию.

### 3. Журнал операций
- Просмотр истории создания кампаний и обновлений потоков из таблицы `operation_logs` (`GET /api/logs`).

## Быстрый старт через Docker Compose

1. Скопируйте `.env.example` в `.env` и заполните `KEITARO_BASE_URL` и `KEITARO_API_KEY`:

```bash
cp .env.example .env
```

2. Запустите все сервисы одной командой:

```bash
docker compose up --build -d
```

После запуска:
- Веб-интерфейс: `http://localhost:5173`
- Backend API и Swagger: `http://localhost:8000/docs`
- Проверка состояния: `http://localhost:8000/health`

Миграции Alembic применяются автоматически при старте контейнера `backend`.

## Локальный запуск (без Docker для backend/frontend)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Миграции Alembic

Создать новую миграцию (из каталога `backend/`):

```bash
alembic revision --autogenerate -m "описание изменений"
```

Применить миграции:

```bash
alembic upgrade head
```

## Запуск тестов

Все тесты backend изолированы от живого Keitaro (используются `httpx.MockTransport`, подмена зависимостей и in-memory SQLite):

```bash
cd backend
pytest -v
```

Сборка и проверка типов фронтенда:

```bash
cd frontend
npm run build
```
