> Этот документ фиксирует архитектурные решения для версии v1 (Python + PostgreSQL). Старая версия (Node.js + Google Sheets) сохраняется как git tag `v0-nodejs-sheets`.

---

## 1. Цели проекта

- **Личный финансовый трекер** для одного человека (приоритет)
- **Open-source** под MIT, чтобы другие могли self-host
- **Опциональный SaaS** на твоём хостинге для тех кому лень разворачивать

Из этих целей следует:

- Низкий порог входа для self-host (один `docker compose up`)
- Поддержка multi-user из коробки, но не обязательно
- Не должно требоваться сторонних сервисов (SMTP, Redis) для базовой работы

---

## 2. Stack

|Слой|Технология|
|---|---|
|Backend|Python 3.12+, FastAPI|
|ORM|SQLAlchemy 2.0 (async)|
|Migrations|Alembic|
|Validation|Pydantic v2|
|DB|PostgreSQL 16|
|Frontend|React 19, Vite, Recharts (без изменений)|
|Package manager|uv|
|Tests|pytest + httpx + pytest-asyncio|
|Deployment|docker-compose, nginx|

---

## 3. Структура backend-py

Domain-driven (feature folders):

```
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── docker/
│   └── Dockerfile
├── scripts/
│   ├── seed.py              # дефолтные категории, валюты
│   └── migrate_from_sheets.py
└── app/
    ├── main.py              # FastAPI app
    ├── config.py            # pydantic-settings
    ├── database.py          # async engine, session factory
    ├── core/
    │   ├── security.py      # password hashing, JWT
    │   ├── dependencies.py  # get_db, get_current_user, get_settings
    │   ├── exceptions.py    # custom exceptions + handlers
    │   ├── middleware.py    # CORS, logging, error handler
    │   └── pagination.py    # общая пагинация
    └── domains/
        ├── auth/
        │   ├── models.py        # User, RefreshToken, OAuthAccount,
        │   │                    # EmailVerificationToken, PasswordResetToken
        │   ├── schemas.py       # Pydantic
        │   ├── repository.py    # только работа с БД (см. §16 стандартов)
        │   ├── service.py       # AuthService (login, register, refresh)
        │   ├── routes.py        # /auth/*
        │   ├── providers/       # single_user, multi_user, oauth/google
        │   └── dependencies.py
        ├── accounts/
        │   ├── models.py
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py
        │   └── routes.py
        ├── categories/
        │   ├── models.py
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py
        │   ├── routes.py
        │   └── defaults.py      # дефолтный набор категорий
        ├── currencies/
        │   ├── models.py        # Currency + ExchangeRate
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py       # конвертация, refresh rates
        │   ├── routes.py
        │   └── providers/       # open-er-api клиент
        ├── transactions/
        │   ├── models.py        # Transaction + Transfer
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py
        │   └── routes.py
        ├── budgets/
        │   ├── models.py
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py       # rollover_amount calc
        │   └── routes.py
        ├── recurring/
        │   ├── models.py
        │   ├── schemas.py
        │   ├── repository.py
        │   ├── service.py
        │   └── routes.py
        ├── summary/
        │   ├── schemas.py
        │   ├── repository.py    # read-only агрегатные запросы
        │   ├── service.py       # dashboard, cashflow aggregates
        │   └── routes.py
        ├── users/               # профиль и валюты текущего юзера
        │   ├── schemas.py
        │   ├── repository.py    # читает User (auth) и UserCurrency
        │   ├── service.py
        │   └── routes.py
        ├── export/
        │   ├── schemas.py
        │   ├── repository.py    # bulk read-only выборки всех данных
        │   ├── service.py       # CSV/XLSX/JSON
        │   └── routes.py
        └── import_/
            ├── schemas.py
            ├── repository.py    # «пустота» аккаунта + bulk-вставка
            ├── service.py
            └── routes.py
```

---

## 4. Бизнес-логика — где живёт

**Слои: `router → service → repository → model`** (по §16 стандартов кода).
Каждый слой знает только о слое ниже. Обращаться к БД напрямую из роутера запрещено.

- **Routes** — только парсинг входа/выхода через Pydantic, вызов сервиса, возврат результата. HTTP-слой.
- **Services** — вся бизнес-логика и правила, не знают про HTTP. Зависят от `repository` через `Protocol`-интерфейс (для DI и подмены в тестах — §6.4 стандартов).
- **Repositories** — только работа с БД (запросы SQLAlchemy), никакой бизнес-логики. Принимают `AsyncSession`.
- **Models** — анемичные ORM-классы: структура + relationships.
- **Транзакции БД** — на уровне сервиса (`async with session.begin()` / `commit`), не в репозитории. Сессия SQLAlchemy выступает Unit-of-Work — отдельной абстракции UoW не вводим (YAGNI, §11).

Пример:

```python
# repository.py
class TransactionRepository(Protocol):
    async def add(self, tx: Transaction) -> Transaction: ...
    async def get_by_id(self, tx_id: UUID, user_id: UUID) -> Transaction | None: ...


class SqlTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tx: Transaction) -> Transaction:
        self._session.add(tx)
        await self._session.flush()  # commit — на уровне сервиса
        return tx

# service.py
class TransactionService:
    def __init__(
        self,
        repo: TransactionRepository,
        currency_service: CurrencyService,
    ) -> None:
        self._repo = repo
        self._currency = currency_service

    async def create(self, data: TransactionCreate) -> Transaction:
        amount_rub = await self._currency.convert(
            data.amount, data.currency_code, 'RUB',
        )
        tx = Transaction(**data.model_dump(), amount_rub=amount_rub)
        return await self._repo.add(tx)

# routes.py
@router.post('/transactions', response_model=ApiResponse[TransactionRead])
async def create_transaction(
    data: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
) -> ApiResponse[TransactionRead]:
    tx = await service.create(data)
    return ApiResponse(data=TransactionRead.model_validate(tx))
```

> Это уточняет ADR-002: доменно-ориентированная структура сохраняется (слои живут **внутри** папки домена), добавляется лишь внутридоменный слой `repository`. См. ADR-013.

---

## 5. Auth-стратегия

### 3 режима через `AUTH_MODE` в `.env`

|Режим|Регистрация|Email-верификация|Use case|
|---|---|---|---|
|`single_user`|Disabled|Не требуется|Self-host для одного человека|
|`multi_user_no_verify`|Open|Не требуется|Свой хостинг без SMTP|
|`multi_user`|Open|Обязательна|Публичный SaaS|

### Реализация

Один `AuthProvider` интерфейс, разные стратегии:

```
app/domains/auth/providers/
├── base.py              # AuthProvider abstract
├── single_user.py       # читает email/password из env
├── multi_user.py        # полноценная регистрация
└── oauth/
    └── google.py        # OAuth provider
```

### JWT + refresh tokens

- Access token: 15 минут, в `Authorization: Bearer` header
- Refresh token: 30 дней, в БД, можно revoke
- `POST /auth/refresh` обменивает refresh на новый access + новый refresh (rotation)
- `POST /auth/logout` помечает refresh token как revoked

### OAuth roadmap

- **MVP**: email/password
- **v1.1**: Google OAuth
- **v1.2+**: GitHub, VK, Yandex, OK (по запросу)

Архитектурно расширяемо через `oauth_accounts` таблицу.

### Защита

- Юзер в single-mode не может удалить себя (DELETE /users/me возвращает 403)
- В multi-mode self-deletion работает с soft-delete + каскадной архивацией данных

---

## 6. Модель данных (14 таблиц)

### Общие правила

- **UUID** primary keys везде (`uuid_generate_v4()`)
- **Soft delete** через `is_archived` (не `DELETE FROM`)
- **Money** — `numeric(18, 4)` (точное десятичное)
- **Timestamps** — `timestamp with time zone` (UTC внутри, конверсия по `users.timezone`)
- **Триггер** `updated_at` автоматически обновляется
- **Multi-tenancy** — `user_id` во всех user-owned таблицах + индекс на `(user_id, ...)`

### Tables

#### `users`

```
id              UUID PK
email           string UNIQUE NOT NULL
hashed_password string NOT NULL
name            string nullable
timezone        string default 'Europe/Moscow'
default_currency string(3) default 'RUB'
locale          string default 'ru'
is_active       boolean default true
is_verified     boolean default false
created_at      timestamptz
updated_at      timestamptz
```

#### `accounts`

```
id              UUID PK
user_id         UUID FK→users.id NOT NULL
name            string NOT NULL
type            enum('card','cash','card_credit','savings','investment')
currency_code   string(3) FK→currencies.code
initial_balance numeric(18,4) default 0
credit_limit    numeric(18,4) nullable
color           string nullable
sort_order      integer default 0
comments        text nullable
is_archived     boolean default false
created_at, updated_at

UNIQUE (user_id, name) WHERE is_archived = false
INDEX (user_id)
```

#### `currencies` (глобальный справочник)

```
code            string(3) PK  -- ISO 4217
name            string NOT NULL
symbol          string
decimals        integer default 2
```

Сидится миграцией: RUB, USD, UZS, THB, EUR, GBP, KZT, BYN, TRY...

#### `user_currencies` (опционально — какие валюты активны для юзера)

```
id              UUID PK
user_id         UUID FK
currency_code   string(3) FK→currencies.code
is_default      boolean default false
sort_order      integer

UNIQUE (user_id, currency_code)
```

#### `exchange_rates` (только текущий курс)

```
id              UUID PK
base_code       string(3) FK
quote_code      string(3) FK
rate            numeric(18,8)
fetched_at      timestamptz

UNIQUE (base_code, quote_code)
```

История курсов запекается в `transactions.exchange_rate`.

#### `categories`

```
id              UUID PK
user_id         UUID FK NOT NULL
parent_id       UUID FK→categories.id nullable
name            string NOT NULL
icon            string nullable
kind            enum('expense','income','transfer')
is_archived     boolean default false
sort_order      integer
created_at, updated_at

UNIQUE (user_id, parent_id, name) WHERE is_archived = false
INDEX (user_id)
```

Дефолтный набор копируется при регистрации юзера. Список дефолтов — в `domains/categories/defaults.py`.

#### `transfers` (группирующий узел)

```
id              UUID PK
user_id         UUID FK
created_at      timestamptz
```

#### `transactions`

```
id              UUID PK
user_id         UUID FK NOT NULL
transfer_id     UUID FK→transfers.id nullable
date            timestamptz NOT NULL
kind            enum('expense','income','transfer')
required        enum('required','optional') nullable
amount          numeric(18,4) NOT NULL
currency_code   string(3) FK NOT NULL  -- = accounts.currency_code (валидация)
amount_rub      numeric(18,4) NOT NULL  -- денормализация
exchange_rate   numeric(18,8) NOT NULL  -- запекается на момент создания
account_id      UUID FK→accounts.id NOT NULL
category_id     UUID FK→categories.id nullable  -- NULL для transfer
comment         text nullable
created_at, updated_at

INDEX (user_id, date DESC)
INDEX (account_id)
INDEX (category_id)
INDEX (transfer_id)
```

Перевод/конвертация — две строки в transactions с одним `transfer_id`. Комиссия — третья строка без `transfer_id`.

#### `budgets`

```
id              UUID PK
user_id         UUID FK NOT NULL
month           date NOT NULL  -- первое число месяца
category_id     UUID FK NOT NULL
planned         numeric(18,4) NOT NULL
notes           text nullable
rollover        boolean default false
created_at, updated_at

UNIQUE (user_id, month, category_id)
INDEX (user_id, month)
```

`rollover_amount` не хранится — считается на лету в сервисе.

#### `recurring_expenses` (plan_min)

```
id              UUID PK
user_id         UUID FK NOT NULL
required        enum('required','optional')
category_id     UUID FK NOT NULL
name            string NOT NULL  -- бывшая subcategory
monthly_amount  numeric(18,4)
currency_code   string(3) FK
amount_rub      numeric(18,4)
comments        text nullable
is_archived     boolean default false
created_at, updated_at

INDEX (user_id)
```

#### `refresh_tokens`

```
id              UUID PK
user_id         UUID FK ON DELETE CASCADE
token_hash      string UNIQUE NOT NULL
expires_at      timestamptz NOT NULL
revoked_at      timestamptz nullable
user_agent      string nullable
ip_address      string nullable
created_at      timestamptz

INDEX (token_hash)
INDEX (user_id, revoked_at)
```

#### `oauth_accounts`

```
id              UUID PK
user_id         UUID FK
provider        enum('google','github','vk','yandex','odnoklassniki')
provider_user_id string NOT NULL
email           string
access_token    string nullable
refresh_token   string nullable
created_at, updated_at

UNIQUE (provider, provider_user_id)
```

#### `email_verification_tokens` (только для multi_user режима)

```
id              UUID PK
user_id         UUID FK ON DELETE CASCADE
token_hash      string UNIQUE
expires_at      timestamptz
created_at      timestamptz
```

#### `password_reset_tokens`

```
id              UUID PK
user_id         UUID FK ON DELETE CASCADE
token_hash      string UNIQUE
expires_at      timestamptz
used_at         timestamptz nullable
created_at      timestamptz
```

---

## 7. API дизайн

### Принципы

- Префикс `/api/v1/` (версионирование с первого дня)
- REST: ресурсы → существительные, действия → HTTP-методы
- `PATCH` для частичного обновления (не `PUT`)
- `DELETE` = soft-delete (архивирование), `POST /:id/restore` для восстановления
- `/me` вместо `/users/{id}` для текущего юзера
- ISO 8601 для дат (`2026-05-25T10:30:00Z`)
- Decimal как строка в JSON (`"1234.5600"`)
- Единый конверт ответа `ApiResponse{data, meta}` на успехе, `ErrorResponse{code, message, details}` на ошибке (§24 стандартов)
- Пагинация для списков (cursor-based для transactions), мета — в `meta`

### Endpoints

```
# Auth
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password
GET    /api/v1/auth/me

# OAuth (v1.1+)
GET    /api/v1/auth/oauth/{provider}
GET    /api/v1/auth/oauth/{provider}/callback

# Users
PATCH  /api/v1/users/me
DELETE /api/v1/users/me  # 403 в single_mode

# Accounts
GET    /api/v1/accounts
POST   /api/v1/accounts
GET    /api/v1/accounts/{id}
PATCH  /api/v1/accounts/{id}
DELETE /api/v1/accounts/{id}
POST   /api/v1/accounts/{id}/restore

# Categories
GET    /api/v1/categories
POST   /api/v1/categories
GET    /api/v1/categories/{id}
PATCH  /api/v1/categories/{id}
DELETE /api/v1/categories/{id}

# Transactions
GET    /api/v1/transactions?limit=20&cursor=...&from=...&to=...&type=...&category=...
POST   /api/v1/transactions
GET    /api/v1/transactions/{id}
PATCH  /api/v1/transactions/{id}
DELETE /api/v1/transactions/{id}

# Transfers
POST   /api/v1/transfers
GET    /api/v1/transfers/{id}
PATCH  /api/v1/transfers/{id}
DELETE /api/v1/transfers/{id}

# Budgets
GET    /api/v1/budgets?month=2026-05
POST   /api/v1/budgets
PATCH  /api/v1/budgets/{id}
DELETE /api/v1/budgets/{id}
POST   /api/v1/budgets/import

# Recurring
GET    /api/v1/recurring
POST   /api/v1/recurring
PATCH  /api/v1/recurring/{id}
DELETE /api/v1/recurring/{id}
POST   /api/v1/recurring/generate-from-categories

# Currencies
GET    /api/v1/currencies
GET    /api/v1/currencies/rates
POST   /api/v1/currencies/rates/refresh
GET    /api/v1/users/me/currencies
PUT    /api/v1/users/me/currencies

# Summary
GET    /api/v1/summary/dashboard
GET    /api/v1/summary/cashflow?from=...&to=...
GET    /api/v1/summary/by-category?month=2026-05

# Export
GET    /api/v1/export/transactions.csv
GET    /api/v1/export/transactions.xlsx
GET    /api/v1/export/all.json

# Import
POST   /api/v1/import/transactions
POST   /api/v1/import/all
```

### Response format

Единый формат по §24 стандартов. Успех всегда завёрнут в `data`/`meta`, ошибка — плоский объект.

**Успех** (`ApiResponse`, Generic):

```json
// один объект
{ "data": { "id": "…", "amount": "1234.5600" }, "meta": {} }

// список с пагинацией
{
  "data": [ { "id": "…" }, { "id": "…" } ],
  "meta": { "page": 1, "per_page": 20, "total": 42, "total_pages": 3 }
}
```

**Ошибка** (`ErrorResponse`, без обёртки):

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Ошибка валидации входных данных.",
  "details": [
    { "field": "amount", "message": "Должно быть больше 0." }
  ]
}
```

Стандартные коды (UPPER_SNAKE): `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `ALREADY_EXISTS` (например duplicate email), `INTERNAL_ERROR`. См. ADR-014.

---

## 8. Money handling

- **DB**: `numeric(18, 4)` — 18 цифр всего, 4 после запятой
- **Python**: `decimal.Decimal`
- **JSON**: строка `"1234.5600"`
- **Pydantic**: `Decimal` с настройкой сериализации в строку

```python
class TransactionRead(BaseModel):
    amount: Decimal
    model_config = ConfigDict(
        json_encoders={Decimal: str}
    )
```

**На фронте**:

- Отображение через `Intl.NumberFormat` (форматирование, не вычисления)
- Вычисления (если необходимы) — через `decimal.js` (3KB)
- Большинство экранов **только отображают**, вычисления делает бэк

---

## 9. Decisions (ADR)

### ADR-001: Почему SQLAlchemy 2.0, не SQLModel/Tortoise

**Контекст:** нужен ORM для async FastAPI.

**Решение:** SQLAlchemy 2.0.

**Обоснование:**

- Самая большая экосистема в Python (85% FastAPI-проектов)
- Лучше всех материалов и примеров
- Чистое разделение: SQLAlchemy для БД, Pydantic для API
- Async/await native в 2.0
- Знакомо контрибьюторам open-source

**Отвергнуто:**

- SQLModel — слишком жёсткая связка БД и API, плохо для сложных запросов
- Tortoise — меньше экосистема, миграции через Aerich слабее Alembic

### ADR-002: Domain-driven structure

**Контекст:** проект растёт, фич много, нужна организация кода.

**Решение:** папки по фичам (domains/accounts, domains/transactions...).

**Обоснование:**

- Вся логика одной фичи в одной папке
- Легко удалить/добавить фичу
- Меньше когнитивная нагрузка

**Отвергнуто:**

- Layered (models/routes/services отдельно) — при росте проекта файлы расползаются по слоям

### ADR-003: PostgreSQL, не SQLite

**Контекст:** база данных для self-host и SaaS.

**Решение:** PostgreSQL 16.

**Обоснование:**

- Decimal-арифметика точная
- Полная поддержка async через asyncpg
- Enum типы, JSON, timezone-aware timestamps
- Row Level Security для multi-tenancy в перспективе
- Стандарт для production SaaS

**Отвергнуто:**

- SQLite — нет concurrent writes, проблемы с типами Decimal, проблемы с timezone

### ADR-004: Decimal в БД, Decimal в Python, string в JSON

**Контекст:** деньги нельзя терять в точности.

**Решение:** `numeric(18,4)` ↔ `Decimal` ↔ `"1234.5600"` в JSON.

**Обоснование:**

- Float ломается на 0.1 + 0.2
- Integer-копейки требуют постоянного деления на 100
- Decimal-строки — стандарт для финансовых API (Stripe, PayPal)
- Frontend парсит/форматирует, не вычисляет

### ADR-005: 3 auth-режима через AUTH_MODE

**Контекст:** open-source self-host + SaaS требуют разной auth-логики.

**Решение:** один код, переключение поведения через `AUTH_MODE` в env.

**Обоснование:**

- `single_user` — для домашнего self-host без SMTP
- `multi_user_no_verify` — для приватного multi-user без email-инфраструктуры
- `multi_user` — для публичного SaaS с email-верификацией

### ADR-006: Категории — копия дефолтов при регистрации

**Контекст:** нужно дать новому юзеру разумный начальный набор.

**Решение:** при регистрации копируется дефолтный список из `domains/categories/defaults.py`.

**Отвергнуто:**

- Системные категории + override — слишком сложно (нужны миграции дефолтов, overrides на скрытие)

### ADR-007: Transfers как отдельная таблица

**Контекст:** перевод/конвертация = пара транзакций, нужна группировка.

**Решение:** таблица `transfers` (только id и user_id) + `transactions.transfer_id` FK.

**Отвергнуто:**

- `pair_id` колонка с id первой транзакции — менее чисто семантически, нельзя расширять метаданными

### ADR-008: Money — String в JSON

**Контекст:** JSON не имеет Decimal-типа.

**Решение:** `"1234.5600"` строкой.

**Отвергнуто:**

- Float — потеря точности
- Integer-копейки — постоянные конверсии на фронте

### ADR-009: Валюта привязана к аккаунту

**Контекст:** банковские карты однозначно одновалютные.

**Решение:** `accounts.currency_code` обязательное поле, `transactions.currency_code` должно совпадать.

**Отвергнуто:**

- Мультивалютные аккаунты (PayPal-style) — overkill для банковских карт

### ADR-010: Soft-delete везде

**Решение:** `is_archived boolean` во всех user-data таблицах вместо `DELETE`.

**Обоснование:**

- Целостность истории (нельзя удалить аккаунт с транзакциями)
- Возможность восстановить
- Foreign keys остаются валидны

**Исключения:** `refresh_tokens`, `email_verification_tokens`, `password_reset_tokens` — удаляются физически (это не данные юзера).

### ADR-011: OAuth — только Google в MVP

**Решение:** в MVP — email/password. В v1.1 — Google OAuth. Остальные провайдеры — по запросу.

**Обоснование:**

- Каждый OAuth провайдер = регистрация приложения в developer console
- Для self-host каждый self-hoster должен делать это сам — барьер
- Google — самый массовый
- Архитектурно расширяемо через `oauth_accounts`

### ADR-012: REST с /api/v1/ префиксом

**Решение:** новый правильный REST API, не копия Node.js-эндпоинтов.

**Обоснование:**

- Node.js API накопил неконсистентности
- Версионирование с первого дня даёт возможность breaking changes без слома клиентов
- Стандартные REST-конвенции упрощают понимание

**Цена:** фронтенд нужно переписать (новые URLs, новый формат дат, новый auth flow).

### ADR-013: Слой repository (router → service → repository → model)

**Контекст:** §16 стандартов кода требует выделенный слой доступа к БД и запрещает обращение к БД из роутера. Изначальная редакция §4 («thin routes + service», сервис работает с сессией напрямую) этому противоречила.

**Решение:** вводим внутридоменный слой `repository.py`. Сервис зависит от репозитория через `Protocol`-интерфейс; репозиторий принимает `AsyncSession` и содержит только запросы.

**Обоснование:**

- Соответствие стандартам кода (они приоритетны над этим документом — см. ADR-016)
- Тестируемость: сервис юнит-тестируется на фейковом in-memory репозитории без поднятия Postgres (важно для TDD)
- Migration-readiness: репозиторий — тот шов, который удешевил переход Sheets → Postgres и удешевит будущие замены
- Паттерн из базы знаний (Персиваль/Грегори, «Паттерны разработки на Python»)

**Границы:** не противоречит ADR-002 — доменные папки сохраняются, слои живут **внутри** домена. Отдельный Unit-of-Work не вводим: сессия SQLAlchemy сама им является, транзакции держим в сервисе (YAGNI).

**Отвергнуто:**

- Сервис с прямым доступом к сессии — нарушает §16, хуже тестируется.

### ADR-014: Единый формат ответа API (§24 стандартов)

**Контекст:** §24 стандартов задаёт конверт `ApiResponse{data, meta}` на успехе и плоский `ErrorResponse{code, message, details[]}` на ошибке. Изначальная редакция §7 использовала вложенный `{"error": {…}}` с кодами в lower_snake — конфликт.

**Решение:** принимаем формат §24 целиком. Коды ошибок — UPPER_SNAKE. На успехе всё заворачивается в `data`/`meta`, пагинация — в `meta`.

**Обоснование:**

- Соответствие стандартам кода (приоритет — ADR-016)
- Клиент не угадывает структуру: успех всегда `resp.data`, мета всегда `resp.meta`
- Единый предсказуемый контракт упрощает фронт и автотесты

**Отвергнуто:**

- Вложенный `{"error": {…}}` без конверта на успехе — асимметрично и расходится со стандартом.

### ADR-015: Argon2id для паролей, PyJWT для токенов

**Контекст:** §8.1 стандартов предписывает Argon2id (`argon2-cffi`, параметры `time_cost=2`, `memory_cost=65536`). В скелете шага 1 ошибочно заложены `passlib[bcrypt]` и `python-jose`.

**Решение:** пароли — Argon2id через `argon2-cffi`. JWT — `PyJWT`.

**Обоснование:**

- Argon2id — текущая рекомендация OWASP, memory-hard; 64 МБ на хеш при редком логине незаметны на 4 ГБ RAM
- `python-jose` фактически заброшен (есть незакрытые CVE), `PyJWT` поддерживается активно
- §8.3 не навязывает библиотеку JWT — выбор в рамках стандарта

**Отвергнуто:**

- `passlib[bcrypt]` — bcrypt разрешён §8.1, но Argon2id предпочтительнее; passlib также почти не развивается.

### ADR-016: Стандарты кода приоритетнее ARCHITECTURE.md при конфликте

**Контекст:** два источника правды (этот документ и «Стандарты написания Python-кода») местами расходились.

**Решение:** при конфликте побеждают стандарты кода. Этот документ приводится к ним. Зафиксированные следствия: repository-слой (ADR-013), формат ответа §24 (ADR-014), Argon2id/PyJWT (ADR-015), а также `SecretStr` для секретов (§3.3) и лимит строки 79 символов (§1.1).

---

### ADR-017: Отдельный домен `users` для профиля и валют

**Контекст:** управление профилем текущего юзера (имя, часовой пояс, валюта по умолчанию, локаль) и его набором активных валют не относится к аутентификации (`auth` отвечает за регистрацию/вход/токены).

**Решение:** выделен домен `users` с эндпоинтами `/users/me/*`. Его repository читает чужие модели — `User` из `auth` и `UserCurrency` из `currencies` — как `transactions` читает `accounts`/`categories`. `PATCH /users/me` меняет только безопасные поля (имя, часовой пояс, валюта по умолчанию, локаль), но не email/пароль. Часовой пояс валидируется через `zoneinfo`, валюта — по справочнику.

---

### ADR-018: Тонкий read-only repository в домене `export`

**Контекст:** для выгрузки и бэкапа нужны все строки юзера, включая архивные, без пагинации. Доменные репозитории отдают только активные/постраничные данные, поэтому «читать через чужие repository» (как планировалось в §3) недостаточно.

**Решение:** у `export` есть собственный repository с bulk-выборками (читает чужие модели). Это согласуется с ADR-016 (repository-слой обязателен; сервис не ходит в БД напрямую). Файлы-выгрузки возвращаются как `Response` с `Content-Disposition` — ожидаемое исключение из формата `ApiResponse` (§24) для скачивания. XLSX делается через `openpyxl` (единственная новая прикладная зависимость).

---

### ADR-019: Полный бэкап `all.json` — собственный стабильный формат

**Контекст:** `GET /export/all.json` должен давать бэкап, который не ломается при изменении Read-схем API.

**Решение:** домен `export` определяет собственные «сырые» схемы строк (`ExportBundle`, `version=1`) — независимо от Read-схем доменов. Деньги сериализуются строками, даты — ISO. Поле `version` зарезервировано под миграции формата бэкапа.

---

### ADR-020: Импорт только в пустой аккаунт + перегенерация UUID

**Контекст:** `POST /import/all` восстанавливает бэкап. Слияние по чужим UUID рискованно (конфликты, частичные состояния). При регистрации создаются 99 дефолтных категорий, поэтому «пустой» аккаунт не может означать «совсем без категорий».

**Решение:** импорт разрешён, только если у юзера нет финансовых данных (счетов, транзакций, переводов, бюджетов, плана-минимума). Категории и валюты юзера — конфиг: перед заливкой бэкапа они очищаются. При восстановлении все UUID перегенерируются, а ссылки (`parent_id`, `account_id`, `category_id`, `transfer_id`) ремапятся — чтобы не было конфликта первичных ключей при заливке в ту же БД. Проверяются наличие валют в справочнике и целостность ссылок бэкапа. Профильные настройки восстанавливаются (имя, пояс, валюта, локаль); email/пароль не трогаются. Весь импорт — в одной транзакции (commit только при полном успехе). `POST /import/transactions` прогоняет каждую запись через `TransactionService` (те же правила: знак, `amount_rub`, валидация).

---

### ADR-021: Мягкое удаление юзера (`DELETE /users/me`)

**Контекст:** удаление аккаунта в multi-mode не должно физически терять данные сразу.

**Решение:** `DELETE /users/me` ставит `is_active=False` (мягко). В режиме `single_user` запрещён (403) — единственный юзер не должен заблокировать сам себя. Полная каскадная архивация связанных данных отложена.

---

### ADR-022: Перенос остатка бюджета — кумулятивно, без рекурсии

**Контекст:** «конвертный» перенос остатка по категории должен переживать пропуски месяцев и не зависеть от глубины истории.

**Решение:** остаток = Σ(planned) − Σ(spent) по всем предыдущим месяцам для данной категории (накопительно, перерасход уходит в минус). Без рекурсии по месяцам. `spent` матчится по точному `category_id` (родительские бюджеты не вбирают траты по подкатегориям). Бюджеты — только для расходных категорий; planned — в рублях.

---

### ADR-023: Авто-оценка плана-минимума по 3 месяцам

**Контекст:** `POST /recurring/generate-from-categories` должен предлагать суммы регулярных обязательных трат.

**Решение:** для каждой обязательной расходной категории берётся средний `amount_rub` по последним трём полным месяцам; категории с уже существующим планом и нерасходные пропускаются. `DELETE /recurring/{id}` — архивирование (`is_archived`).

---

## 10. Roadmap

### MVP (v1.0)

- [x] Backend на FastAPI с domain структурой
- [x] PostgreSQL + Alembic
- [x] Auth: 3 режима, email/password
- [x] Все фичи которые есть сейчас в Node.js версии
- [x] Docker + docker-compose
- [x] CSV/XLSX/JSON export и import (бэкап/восстановление)
- [ ] Frontend перепиленный под новый API
- [ ] Базовая документация для self-host
- [ ] Деплой (VPS/cloud.ru, nginx, cron на обновление курсов)

Миграция данных из Google Sheets не делается — старт с чистой БД
(решение зафиксировано в ходе разработки).

### v1.1

- Google OAuth login
- Email-верификация (для multi_user режима)
- Password reset

### v1.2

- Дополнительные OAuth: GitHub, VK, Yandex, OK
- Universal CSV import банковских выписок (свои парсеры под форматы банков)

### v2.0

- Tags на транзакции
- Банковские CSV-парсеры (Тинькофф, Сбер, Альфа, ...)
- Двусторонняя синхронизация с Google Sheets (опционально)
- Аналитика: тренды, прогнозы, сравнение периодов
- Mobile-friendly PWA / iOS / Android app (далеко в перспективе)

---

## 11. Что НЕ делаем (по принципу YAGNI)

- Микросервисы — монолит хватит для долгого времени
- gRPC — REST достаточно
- GraphQL — REST проще и понятнее для CRUD
- Event sourcing — overkill для финансового трекера
- Redis в MVP — in-memory cache в Python хватит
- Celery / background workers в MVP — нет долгих задач кроме export, его можно делать синхронно
- WebSockets — нет real-time требований
- Микросервис auth — встроенный auth достаточно
- Kubernetes — docker-compose хватит до многих сотен юзеров

Если что-то понадобится — добавим миграцией.

---

## 12. Параллельная разработка

**Старая версия (Node.js + Sheets)** продолжает работать как сейчас — для твоего личного учёта.

**Новая версия (Python + Postgres)** разрабатывается в `backend-py/` рядом, без давления "надо завтра". Когда всё готово и протестировано — `scripts/migrate_from_sheets.py` переносит данные.

После полной миграции:

1. Git tag `v0-nodejs-sheets`
2. Удалить `backend/` (старый Node.js)
3. Переименовать `backend-py/` → `backend/`
4. Обновить README, docker-compose
5. Опубликовать как v1.0

---

## 13. Open-source requirements

- README с быстрым стартом (`docker compose up`)
- `.env.example` с понятными комментариями
- ARCHITECTURE.md (этот документ)
- CONTRIBUTING.md
- LICENSE (MIT)
- CHANGELOG.md
- GitHub Actions: tests + Docker image build
- Issue templates
- Demo screenshots в README

### ADR-024: Refresh-токен в HttpOnly-cookie

**Контекст:** фронту нужно безопасно хранить refresh; localStorage
уязвим к XSS.

**Решение:** access — в памяти JS; refresh — в cookie
(`HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`,
`Max-Age=refresh_token_expire_days`). Сервис auth остаётся
HTTP-агностичным (ADR-013): cookie ставит/чистит/читает только слой
`routes`. Тело ответа login/register/refresh — `AccessToken` (без
refresh). `/refresh` и `/logout` читают refresh из cookie. CSRF:
`SameSite=Lax` закрывает базовый кейс для self-host; double-submit
CSRF-токен откладываем до публичного SaaS. `cookie_secure` — env-флаг
(false только для локального http-dev).

**Отвергнуто:** refresh в теле + localStorage (XSS-риск).

### ADR-025: Публичный GET /config для фронта

**Контекст:** один образ работает в 3 режимах `AUTH_MODE`; фронт
должен знать режим до логина (показывать ли регистрацию).

**Решение:** публичный (без auth) `GET /api/v1/config` → `{auth_mode}`,
отдельный мини-домен `config`. Только несекретные поля.

**Отвергнуто:** build-time флаг на фронте — ломает «один образ под
любой режим» для self-host.
