# anfinances

Персональная система управления финансами. Google Sheets как база данных, Node.js бэкенд, React фронтенд.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Stack](https://img.shields.io/badge/stack-React%20%2B%20Node.js%20%2B%20Google%20Sheets-brightgreen)

## Что умеет

- **Дашборд** — net worth, активы, долги, runway, расходы по категориям, кредитные карты с лимитом и доступным остатком
- **Счета** — все счета с балансами в рублях, мультивалюта (RUB, USD, UZS, THB и т.д.), кредитные карты с лимитом
- **Транзакции** — история операций с фильтрами по типу/периоду/категории и поиском, редактирование и удаление любых записей
- **Добавление операций** — расходы, доходы, переводы между счетами, конвертация валюты с комиссией. Переводы создаются как пара строк с общим `pair_id`
- **Бюджет** — YNAB-стиль: лимиты по категориям, прогресс-бары, импорт из плана минимум или предыдущего месяца, rollover остатков
- **Прожиточный минимум** — список обязательных и опциональных регулярных трат, основа для расчёта runway
- **Тёмная / светлая тема** — сохраняется между сессиями
- **Адаптивный дизайн** — работает на мобилке и десктопе

## Стек

| Слой | Технологии |
|------|-----------|
| Фронтенд | React 19, Vite, Recharts |
| Бэкенд | Node.js, Express 5 |
| База данных | Google Sheets API v4 |
| Дизайн | Material Design 3, Inter + JetBrains Mono |

## Быстрый старт

### 1. Подготовь Google Sheets

1. Создай новую таблицу Google Sheets
2. Создай листы: `accounts`, `moneyflow`, `plan_min`, `rates`, `reference`, `budget`
3. Структура листов:
   - `accounts`: `account, acc.type, currency, initial_balance, balance in acc.currency, balance in RUB, comments, credit_limit`
   - `moneyflow`: `id, pair_id, date, type, required, amount, amount RUB, account, account_to, currency, category, subcategory, comment`
   - `plan_min`: `required, category, subcategory, monthly_amount, currency, amount_rub, comments`
   - `rates`: `currency, rate, updated`
   - `reference`: первая колонка — название категории, последующие — подкатегории
   - `budget`: `month, category, planned, notes, rollover`

### 2. Настрой Google Cloud

1. Создай проект на [console.cloud.google.com](https://console.cloud.google.com)
2. Включи **Google Sheets API**
3. Создай **Service Account** → скачай JSON-ключ
4. Дай сервисному аккаунту доступ **Editor** к таблице (Share → вставь email из JSON)

### 3. Установи зависимости

```bash
git clone https://github.com/твой-юзернейм/anfinances.git
cd anfinances

# Бэкенд
cd backend
npm install
cp .env.example .env
# Заполни .env

# Фронтенд
cd ../frontend
npm install
```

### 4. Настрой .env

```env
PORT=3001
GOOGLE_CREDENTIALS_PATH=./credentials.json
SPREADSHEET_ID=твой_id_таблицы
# Для продакшна:
# NODE_ENV=production
# ALLOWED_ORIGINS=https://anfinances.example.com
```

Положи JSON-ключ как `backend/credentials.json`.

`credentials.json` и `.env` уже в `.gitignore` — они не уйдут в репо.

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
│   │   ├── routes/
│   │   │   ├── accounts.js     # GET / POST счета
│   │   │   ├── moneyflow.js    # CRUD транзакций + transfer
│   │   │   ├── budget.js       # CRUD бюджета + расчёт rollover
│   │   │   ├── rates.js        # курсы валют + обновление через API
│   │   │   ├── recurring.js    # CRUD плана минимума
│   │   │   ├── reference.js    # категории → подкатегории
│   │   │   └── summary.js      # агрегированные данные
│   │   ├── services/
│   │   │   └── sheets.js       # клиент Google Sheets API
│   │   └── index.js
│   ├── .env.example
│   └── package.json
│
└── frontend/
    ├── src/
    │   ├── api/index.js              # HTTP-клиент
    │   ├── constants.js              # UI-константы и утилиты
    │   ├── components/
    │   │   ├── Dashboard.jsx
    │   │   ├── Transactions.jsx
    │   │   ├── Budget.jsx
    │   │   ├── AddTransaction.jsx
    │   │   ├── EditTransaction.jsx
    │   │   └── AddAccount.jsx
    │   ├── App.jsx
    │   └── index.css                  # Design tokens (MD3)
    └── package.json
```

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Статус сервера |
| GET | `/api/accounts` | Список счетов |
| POST | `/api/accounts` | Добавить счёт |
| GET | `/api/moneyflow` | Все транзакции |
| POST | `/api/moneyflow` | Добавить одиночную транзакцию (генерируется `id`) |
| POST | `/api/moneyflow/transfer` | Атомарно создать пару строк перевода/конвертации (общий `pair_id`) |
| PUT | `/api/moneyflow/:id` | Обновить транзакцию (бэкенд сам пересчитывает `amount RUB`) |
| DELETE | `/api/moneyflow/:id?pair=true` | Удалить транзакцию или пару |
| GET | `/api/summary` | Net worth, балансы, runway, доходы/расходы месяца |
| GET | `/api/rates` | Курсы валют |
| POST | `/api/rates/update` | Обновить курсы через open.er-api.com |
| GET | `/api/recurring` | План минимум |
| POST | `/api/recurring` | Добавить или обновить строку плана |
| DELETE | `/api/recurring` | Удалить строку плана |
| GET | `/api/reference` | Категории и подкатегории |
| GET | `/api/budget?month=2026-05` | Бюджет за месяц (с расчётом `rollover_amount`) |
| POST | `/api/budget` | Сохранить лимит категории |
| DELETE | `/api/budget` | Удалить категорию из бюджета |

## Архитектурные решения

- **ID транзакций** — целые числа, генерируются как `max(id)+1`. Идут с 1.
- **Pair_id** — для пары строк перевода/конвертации обе строки получают одинаковый `pair_id`, равный наименьшему `id` пары. Одиночные транзакции — `pair_id` пустой.
- **Удаление строк** — физическое через `deleteDimension` (не `clearRange`), чтобы не оставались пустые строки.
- **Категории** — единственный источник правды лист `reference`. Фронт получает их через `getReference()`, не хардкодит.
- **Amount RUB** — всегда пересчитывается на бэкенде из `amount + currency` по текущим курсам. Фронт не отправляет это значение явно.
- **Runway** = `totalBalance / monthlyObligatory` (только обязательные траты из plan_min).
- **Кредитные лимиты** — отдельная колонка `credit_limit` в `accounts`. На дашборде показывается `доступно = лимит + текущий_баланс`.

## Шаблон таблицы

Публичный шаблон Google Sheets: _скоро_

## Деплой на VPS

Для продакшна:
- Установи `NODE_ENV=production` и `ALLOWED_ORIGINS=https://твой-домен` в `.env`
- Раздавай фронт через Nginx, бэкенд держи на pm2
- `credentials.json` НЕ кладёт в git — копируй на сервер вручную

Полная инструкция — _скоро_

## Лицензия

MIT — делай что хочешь, но звёздочку поставь 🌟
