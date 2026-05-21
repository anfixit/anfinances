# 🐷 anfinances

Персональная система управления финансами. Google Sheets как база данных, Node.js бэкенд, React фронтенд.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Stack](https://img.shields.io/badge/stack-React%20%2B%20Node.js%20%2B%20Google%20Sheets-brightgreen)

## Что умеет

- 📊 **Дашборд** — net worth, активы, долги, runway, расходы по категориям
- 💳 **Счета** — все счета с балансами в рублях (мультивалюта: RUB, USD, UZS)
- 📋 **Транзакции** — история операций с фильтрами по типу, периоду, категории и поиском
- ➕ **Добавление операций** — расходы, доходы, переводы между счетами, конвертация валюты с комиссией
- 💰 **Бюджет** — YNAB-стиль: лимиты по категориям, прогресс-бары, импорт из плана минимум, rollover остатков
- 🌙 **Тёмная / светлая тема** — сохраняется между сессиями
- 📱 **Адаптивный дизайн** — работает на мобилке и десктопе

## Стек

| Слой | Технологии |
|------|-----------|
| Фронтенд | React 19, Vite, Recharts, Lucide |
| Бэкенд | Node.js, Express 5 |
| База данных | Google Sheets API v4 |
| Дизайн | Material Design 3, Inter + JetBrains Mono |

## Быстрый старт

### 1. Подготовь Google Sheets

1. Создай новую таблицу Google Sheets
2. Создай листы: `accounts`, `moneyflow`, `plan_min`, `rates`, `reference`, `budget`, `dashboard`
3. Структура листов — смотри [шаблон таблицы](#шаблон-таблицы)

### 2. Настрой Google Cloud

1. Создай проект на [console.cloud.google.com](https://console.cloud.google.com)
2. Включи **Google Sheets API**
3. Создай **Service Account** → скачай JSON-ключ
4. Дай сервисному аккаунту доступ **Editor** к твоей таблице (Share → вставь email из JSON)

### 3. Установи зависимости

```bash
git clone https://github.com/твой-юзернейм/anfinances.git
cd anfinances

# Бэкенд
cd backend
npm install
cp .env.example .env
# Заполни .env своими данными

# Фронтенд
cd ../frontend
npm install
```

### 4. Настрой .env

```env
PORT=3001
GOOGLE_CREDENTIALS_PATH=./credentials.json
SPREADSHEET_ID=твой_id_таблицы
```

Положи скачанный JSON-ключ как `backend/credentials.json`

### 5. Запусти

```bash
# Терминал 1 — бэкенд
cd backend && npm run dev

# Терминал 2 — фронтенд
cd frontend && npm run dev
```

Открой [http://localhost:5173](http://localhost:5173)

## Структура проекта

```
anfinances/
├── backend/
│   ├── src/
│   │   ├── routes/          # API эндпоинты
│   │   │   ├── accounts.js
│   │   │   ├── moneyflow.js
│   │   │   ├── budget.js
│   │   │   ├── rates.js
│   │   │   ├── recurring.js
│   │   │   ├── reference.js
│   │   │   └── summary.js
│   │   ├── services/
│   │   │   └── sheets.js    # Google Sheets клиент
│   │   └── index.js
│   ├── .env.example
│   └── package.json
│
└── frontend/
    ├── src/
    │   ├── api/             # HTTP клиент
    │   ├── components/
    │   │   ├── Dashboard.jsx
    │   │   ├── Transactions.jsx
    │   │   ├── Budget.jsx
    │   │   └── AddTransaction.jsx
    │   ├── App.jsx
    │   └── index.css        # Design tokens (MD3)
    └── package.json
```

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Статус сервера |
| GET | `/api/accounts` | Список счетов |
| GET | `/api/moneyflow` | Транзакции |
| POST | `/api/moneyflow` | Добавить транзакцию |
| GET | `/api/summary` | Агрегированные данные |
| GET | `/api/rates` | Курсы валют |
| GET | `/api/recurring` | Регулярные расходы |
| GET | `/api/reference` | Категории и подкатегории |
| GET | `/api/budget?month=2026-05` | Бюджет за месяц |
| POST | `/api/budget` | Сохранить лимит категории |
| DELETE | `/api/budget` | Удалить категорию из бюджета |

## Шаблон таблицы

Публичный шаблон Google Sheets: _скоро_

## Деплой на VPS

_Инструкция скоро_

## Лицензия

MIT — делай что хочешь, но звёздочку поставь 🌟
