# Телеграм-бот для anfinances — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Телеграм-бот, который принимает траты голосом и текстом, записывает их
в anfinances и отвечает на вопросы по данным.

**Architecture:** Отдельный Python-сервис в том же compose-стеке, что и сайт.
Один агент Claude с инструментами: инструменты ходят в anfinances по HTTP на
`backend:8000`, доступа к PostgreSQL у бота нет. Голос распознаётся через OpenAI
Whisper и файл сразу удаляется. Перед ботом закрываются два пункта фундамента.

**Tech Stack:** Python 3.13, uv, aiogram 3, anthropic SDK (`AsyncAnthropic`,
`tool_runner`), openai SDK (только распознавание), httpx, pydantic-settings,
pytest, ruff, mypy.

**Спеки:** [фундамент](../specs/2026-08-10-currency-foundation-design.md),
[бот](../specs/2026-08-10-telegram-bot-design.md).

## Global Constraints

- Python `>=3.13`; менеджер пакетов — `uv`.
- `ruff`: `line-length = 79`, `target-version = "py313"`. Код и тесты обязаны
  проходить `ruff check` и `ruff format --check`.
- `mypy` без ошибок. Аннотации типов обязательны во всех новых функциях.
- Комментарии и докстроки — на русском, как в остальном коде проекта.
- Деньги — только `Decimal`. `float` для денег запрещён.
- Модель Claude: `claude-opus-5`, `thinking={"type": "adaptive"}`,
  `output_config={"effort": "medium"}`. Модель не понижать.
- Бот не имеет доступа к PostgreSQL. Только HTTP к anfinances API.
- Голосовые файлы удаляются сразу после расшифровки, включая ветку с ошибкой.
- Секреты только через переменные окружения. В код и в git — никогда.
- Каждая задача заканчивается коммитом. Сообщения коммитов на русском, в стиле
  существующей истории: `feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`.
- Текущая голова Alembic — `d17d0credits02`. Новые миграции цепляются от неё.

---

# Часть A. Фундамент (до бота)

## Task 1: Инвариант знака в БД

Соглашение `balance = initial_balance + Σ amount` держится только на сервисном
слое. Бот будет создавать операции из распознанной речи, где ошибка разбора
вероятнее, чем ошибка в форме, — переносим инвариант в БД.

**Files:**
- Modify: `backend/app/domains/transactions/models.py:46-51` (`__table_args__`)
- Create: `backend/alembic/versions/20260810_1000_e18d0sign01_transaction_sign_invariant.py`
- Create: `backend/tests/test_transaction_sign_invariant.py`

**Interfaces:**
- Consumes: `TransactionKind` из `app.core.enums`; модель `Transaction`.
- Produces: четыре именованных ограничения на таблице `transactions` —
  `ck_transactions_amount_nonzero`, `ck_transactions_expense_negative`,
  `ck_transactions_income_positive`, `ck_transactions_sign_agreement`.

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_transaction_sign_invariant.py`:

```python
"""БД не принимает операцию с неверным знаком.

Соглашение знаков — Стратегия А: расход и кредитный платёж
отрицательны, доход положителен, знак amount_rub совпадает с amount.
Проверяем, что это держится на уровне БД, а не только в сервисе.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import TransactionKind
from app.domains.transactions.models import Transaction


def _tx(**overrides: object) -> Transaction:
    """Минимально валидная транзакция; поля перекрываются точечно."""
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "kind": TransactionKind.EXPENSE,
        "amount": Decimal("-100"),
        "currency_code": "RUB",
        "amount_rub": Decimal("-100"),
        "exchange_rate": Decimal("1"),
        "date": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Transaction(**defaults)


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        (
            "расход с плюсом",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "доход с минусом",
            {
                "kind": TransactionKind.INCOME,
                "amount": Decimal("-100"),
                "amount_rub": Decimal("-100"),
            },
        ),
        (
            "кредитный платёж с плюсом",
            {
                "kind": TransactionKind.CREDIT_PAYMENT,
                "amount": Decimal("100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "знаки amount и amount_rub разошлись",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("-100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "нулевая сумма",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("0"),
                "amount_rub": Decimal("0"),
            },
        ),
    ],
)
async def test_bad_sign_rejected(
    db_session, label: str, overrides: dict[str, object]
) -> None:
    db_session.add(_tx(**overrides))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_transfer_legs_allowed(db_session) -> None:
    """Ноги перевода знаком не ограничены — только согласованностью."""
    transfer_id = uuid.uuid4()
    db_session.add(
        _tx(
            kind=TransactionKind.TRANSFER,
            amount=Decimal("-500"),
            amount_rub=Decimal("-500"),
            transfer_id=transfer_id,
        )
    )
    db_session.add(
        _tx(
            kind=TransactionKind.TRANSFER,
            amount=Decimal("500"),
            amount_rub=Decimal("500"),
            transfer_id=transfer_id,
        )
    )
    await db_session.flush()


async def test_tiny_foreign_amount_allowed(db_session) -> None:
    """Мелкая сумма в слабой валюте не должна округляться в ноль."""
    db_session.add(
        _tx(
            currency_code="UZS",
            amount=Decimal("-1000"),
            amount_rub=Decimal("-7.2000"),
            exchange_rate=Decimal("0.0072"),
        )
    )
    await db_session.flush()
```

Если в `backend/tests/conftest.py` нет фикстуры `db_session`, добавить её туда:

```python
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.models import Base  # noqa: E402


@pytest.fixture
async def db_session() -> AsyncSession:
    """Сессия на чистой схеме, откатывается после теста."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/test_transaction_sign_invariant.py -v`
Expected: FAIL — все параметры `test_bad_sign_rejected` падают, потому что
`IntegrityError` не поднимается: ограничений ещё нет.

- [ ] **Step 3: Добавить ограничения в модель**

В `backend/app/domains/transactions/models.py` дополнить импорт SQLAlchemy
именем `CheckConstraint` и заменить `__table_args__` класса `Transaction`:

```python
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_transfer_id", "transfer_id"),
        # Соглашение знаков (Стратегия А) на уровне БД: сервис может
        # ошибиться, БД — нет. Ноги перевода под знаковые правила не
        # попадают: там знак задаётся направлением, а не типом.
        CheckConstraint(
            "amount <> 0",
            name="ck_transactions_amount_nonzero",
        ),
        CheckConstraint(
            "kind NOT IN ('expense', 'credit_payment') OR amount < 0",
            name="ck_transactions_expense_negative",
        ),
        CheckConstraint(
            "kind <> 'income' OR amount > 0",
            name="ck_transactions_income_positive",
        ),
        CheckConstraint(
            "(amount > 0 AND amount_rub > 0)"
            " OR (amount < 0 AND amount_rub < 0)",
            name="ck_transactions_sign_agreement",
        ),
    )
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd backend && uv run pytest tests/test_transaction_sign_invariant.py -v`
Expected: PASS — все параметры.

- [ ] **Step 5: Написать миграцию с предварительной проверкой данных**

Создать
`backend/alembic/versions/20260810_1000_e18d0sign01_transaction_sign_invariant.py`:

```python
"""transaction sign invariant

Revision ID: e18d0sign01
Revises: d17d0credits02
Create Date: 2026-08-10 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e18d0sign01"
down_revision: str | None = "d17d0credits02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = {
    "ck_transactions_amount_nonzero": "amount <> 0",
    "ck_transactions_expense_negative": (
        "kind NOT IN ('expense', 'credit_payment') OR amount < 0"
    ),
    "ck_transactions_income_positive": "kind <> 'income' OR amount > 0",
    "ck_transactions_sign_agreement": (
        "(amount > 0 AND amount_rub > 0)"
        " OR (amount < 0 AND amount_rub < 0)"
    ),
}


def upgrade() -> None:
    # Сначала убеждаемся, что текущие данные ограничениям удовлетворяют.
    # Иначе ALTER TABLE упадёт невнятно, посреди деплоя.
    conn = op.get_bind()
    for name, condition in _CONSTRAINTS.items():
        bad = conn.execute(
            sa.text(
                "SELECT count(*) FROM transactions "  # noqa: S608
                f"WHERE NOT ({condition})"
            )
        ).scalar_one()
        if bad:
            raise RuntimeError(
                f"Нельзя добавить {name}: {bad} строк(и) в transactions "
                "нарушают соглашение знаков. Почините данные и повторите."
            )

    for name, condition in _CONSTRAINTS.items():
        op.create_check_constraint(name, "transactions", condition)


def downgrade() -> None:
    for name in _CONSTRAINTS:
        op.drop_constraint(name, "transactions", type_="check")
```

- [ ] **Step 6: Проверить, что миграция применяется и откатывается**

Run: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: три команды завершаются без ошибок. Требуется поднятый PostgreSQL
(`docker compose up -d postgres`).

- [ ] **Step 7: Прогнать весь набор проверок**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q`
Expected: ruff чисто, mypy чисто, все тесты проходят (было 185 passed,
1 skipped — станет больше на число новых).

- [ ] **Step 8: Коммит**

```bash
git add backend/app/domains/transactions/models.py backend/alembic/versions/20260810_1000_e18d0sign01_transaction_sign_invariant.py backend/tests/test_transaction_sign_invariant.py backend/tests/conftest.py
git commit -m "feat(transactions): закрепить соглашение знаков в БД"
```

---

## Task 2: Периодическое обновление курсов

Курсы обновляются на старте, кнопкой и ручным эндпоинтом, но не по расписанию.
Контейнер живёт неделями с курсом дня запуска, и рублёвая оценка остатка в
иностранной валюте плывёт.

**Files:**
- Modify: `backend/app/config.py` (новая настройка)
- Create: `backend/app/domains/currencies/scheduler.py`
- Modify: `backend/app/main.py:92-112` (lifespan)
- Create: `backend/tests/test_currencies_scheduler.py`

**Interfaces:**
- Consumes: `CurrencyService.refresh_rates()`; `Settings`.
- Produces: `refresh_rates_periodically(sessionmaker, settings, interval_hours)`
  — корутина бесконечного цикла; `start_rate_refresh(app, settings)` —
  возвращает `asyncio.Task | None`.

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_currencies_scheduler.py`:

```python
"""Фоновое обновление курсов переживает сбои провайдера."""

import asyncio

import pytest

from app.domains.currencies.scheduler import (
    refresh_rates_periodically,
)


class _Recorder:
    """Считает вызовы; на первом бросает, чтобы проверить живучесть."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self._fail_first = fail_first

    async def __call__(self) -> None:
        self.calls += 1
        if self._fail_first and self.calls == 1:
            raise RuntimeError("провайдер недоступен")


async def test_refreshes_repeatedly() -> None:
    recorder = _Recorder()
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert recorder.calls >= 2


async def test_survives_provider_failure() -> None:
    recorder = _Recorder(fail_first=True)
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Первый вызов упал, но цикл продолжился.
    assert recorder.calls >= 2


async def test_cancellation_is_prompt() -> None:
    recorder = _Recorder()
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=3600)
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.done()
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/test_currencies_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domains.currencies.scheduler'`.

- [ ] **Step 3: Реализовать планировщик**

Создать `backend/app/domains/currencies/scheduler.py`:

```python
"""Фоновое обновление курсов валют.

Обновление на старте приложения и ручные вызовы остаются как были;
здесь добавляется только периодический прогон, чтобы долгоживущий
контейнер не работал с курсом дня своего запуска.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger("anfinances.currencies.scheduler")

__all__ = ["refresh_rates_periodically"]

Refresher = Callable[[], Awaitable[None]]


async def refresh_rates_periodically(
    refresh: Refresher,
    interval_seconds: float,
) -> None:
    """Вызывать ``refresh`` каждые ``interval_seconds`` секунд.

    Ошибка провайдера логируется и не прерывает цикл: отсутствие
    свежего курса — не повод останавливать обновление навсегда.
    Отмена задачи пробрасывается наружу без перехвата.
    """
    while True:
        try:
            await refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Periodic rates refresh failed", exc_info=True)
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd backend && uv run pytest tests/test_currencies_scheduler.py -v`
Expected: PASS — три теста.

- [ ] **Step 5: Добавить настройку интервала**

В `backend/app/config.py`, рядом с существующими настройками курсов
(`exchange_rate_api_url`, `exchange_rate_timeout_seconds`), добавить:

```python
    # 0 выключает периодическое обновление; обновление на старте
    # приложения при этом остаётся.
    exchange_rate_refresh_interval_hours: int = Field(default=6, ge=0)
```

- [ ] **Step 6: Подключить задачу в lifespan**

В `backend/app/main.py` внутри `lifespan`, сразу после существующего блока
`Currency rates refreshed on startup`, добавить запуск задачи, а перед
`await engine.dispose()` — её отмену:

```python
    rates_task: asyncio.Task[None] | None = None
    interval = settings.exchange_rate_refresh_interval_hours
    if interval > 0:

        async def _refresh() -> None:
            async with sessionmaker() as session:
                from app.domains.currencies.providers.er_api import (
                    ErApiRatesProvider,
                )
                from app.domains.currencies.repository import (
                    SqlCurrencyRepository,
                )
                from app.domains.currencies.service import CurrencyService

                svc = CurrencyService(
                    SqlCurrencyRepository(session),
                    ErApiRatesProvider(settings),
                )
                await svc.refresh_rates()
                await session.commit()

        rates_task = asyncio.create_task(
            refresh_rates_periodically(_refresh, interval * 3600)
        )
        logger.info("Periodic rates refresh every %sh", interval)

    yield

    if rates_task is not None:
        rates_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await rates_task

    await engine.dispose()
```

Добавить в начало файла импорты `asyncio`, `contextlib` и
`from app.domains.currencies.scheduler import refresh_rates_periodically`.
Существующий `yield` в `lifespan` заменяется показанным выше — второго
`yield` быть не должно.

- [ ] **Step 7: Прогнать весь набор проверок**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q`
Expected: всё чисто, все тесты проходят.

- [ ] **Step 8: Коммит**

```bash
git add backend/app/config.py backend/app/main.py backend/app/domains/currencies/scheduler.py backend/tests/test_currencies_scheduler.py
git commit -m "feat(currencies): обновлять курсы по расписанию"
```

---

# Часть B. Бэкенд под бота

## Task 3: Эндпоинт «возраст денег»

Четвёртое правило ВНБ — жить на доход предыдущего месяца — в виде числа.
Ни таблиц, ни миграций: расчёт по существующим операциям.

**Files:**
- Modify: `backend/app/domains/summary/schemas.py`
- Modify: `backend/app/domains/summary/repository.py`
- Modify: `backend/app/domains/summary/service.py`
- Modify: `backend/app/domains/summary/routes.py`
- Create: `backend/tests/test_summary_money_age.py`

**Interfaces:**
- Consumes: `SummaryRepository.cashflow(user_id, date_from, date_to)` —
  возвращает `tuple[Decimal, Decimal]` (доход, расход; расход отрицателен);
  `month_bounds_utc`, `_shift_month` из `app.core.datetime`.
- Produces: `MoneyAgeResult` со свойствами `previous_month: str`,
  `current_month: str`, `previous_month_income_rub: Decimal`,
  `current_month_expense_rub: Decimal`, `coverage: Decimal | None`,
  `is_covered: bool`; метод `SummaryService.money_age(user_id, timezone_name)`;
  роут `GET /summary/money-age`.

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_summary_money_age.py`:

```python
"""Расчёт «возраста денег» — четвёртое правило ВНБ."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.domains.summary.service import SummaryService


class _StubRepo:
    """Отдаёт заранее заданные пары (доход, расход) по вызовам."""

    def __init__(self, pairs: list[tuple[Decimal, Decimal]]) -> None:
        self._pairs = pairs
        self.calls: list[tuple[datetime, datetime]] = []

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[Decimal, Decimal]:
        self.calls.append((date_from, date_to))
        return self._pairs[len(self.calls) - 1]


def _service(pairs: list[tuple[Decimal, Decimal]]) -> SummaryService:
    return SummaryService(_StubRepo(pairs), currencies=None)


async def test_covered_when_last_income_exceeds_current_expense() -> None:
    service = _service(
        [
            (Decimal("100000"), Decimal("0")),  # прошлый месяц: доход
            (Decimal("0"), Decimal("-60000")),  # текущий: расход
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.previous_month == "2026-07"
    assert result.current_month == "2026-08"
    assert result.previous_month_income_rub == Decimal("100000")
    assert result.current_month_expense_rub == Decimal("60000")
    assert result.coverage is not None
    assert round(result.coverage, 4) == Decimal("1.6667")
    assert result.is_covered is True


async def test_not_covered() -> None:
    service = _service(
        [
            (Decimal("50000"), Decimal("0")),
            (Decimal("0"), Decimal("-80000")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.is_covered is False


async def test_no_expenses_yet_gives_none_coverage() -> None:
    service = _service(
        [
            (Decimal("50000"), Decimal("0")),
            (Decimal("0"), Decimal("0")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert result.coverage is None
    # Нет трат — правило формально соблюдено.
    assert result.is_covered is True


async def test_no_income_last_month_is_not_covered() -> None:
    service = _service(
        [
            (Decimal("0"), Decimal("0")),
            (Decimal("0"), Decimal("-1000")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.coverage == Decimal("0")
    assert result.is_covered is False


async def test_january_looks_back_to_december() -> None:
    service = _service(
        [
            (Decimal("10"), Decimal("0")),
            (Decimal("0"), Decimal("-5")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 1, 15, tzinfo=UTC),
    )
    assert result.previous_month == "2025-12"
    assert result.current_month == "2026-01"
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/test_summary_money_age.py -v`
Expected: FAIL — `AttributeError: 'SummaryService' object has no attribute 'money_age'`.

- [ ] **Step 3: Добавить схему**

В `backend/app/domains/summary/schemas.py` добавить в `__all__` имя
`"MoneyAgeResult"` и класс:

```python
class MoneyAgeResult(BaseModel):
    """Насколько текущие траты покрыты доходом прошлого месяца.

    Четвёртое правило ВНБ: жить на доход предыдущего месяца.
    ``coverage`` — доля: 1.0 значит ровно покрыто, больше — запас.
    ``None`` — трат в текущем месяце ещё не было.
    """

    previous_month: str
    current_month: str
    previous_month_income_rub: Decimal
    current_month_expense_rub: Decimal
    coverage: Decimal | None
    is_covered: bool
```

- [ ] **Step 4: Добавить метод в сервис**

В `backend/app/domains/summary/service.py` добавить импорты
`from datetime import UTC, date, datetime` (дополнив существующий),
`from app.core.datetime import month_bounds_utc` (уже есть) и
`MoneyAgeResult` из схем, затем метод:

```python
    async def money_age(
        self,
        user_id: uuid.UUID,
        timezone_name: str = DEFAULT_TIMEZONE,
        now: datetime | None = None,
    ) -> MoneyAgeResult:
        """Доход прошлого месяца против расходов текущего."""
        moment = (now or datetime.now(UTC)).astimezone(
            ZoneInfo(timezone_name)
        )
        current = date(moment.year, moment.month, 1)
        previous = _shift_month(current, -1)

        prev_start, prev_end = month_bounds_utc(previous, timezone_name)
        income, _ = await self._repo.cashflow(
            user_id, prev_start, prev_end
        )

        cur_start, cur_end = month_bounds_utc(current, timezone_name)
        _, expense = await self._repo.cashflow(
            user_id, cur_start, cur_end
        )
        expense_abs = abs(expense)

        coverage = (
            None if expense_abs == 0 else income / expense_abs
        )
        return MoneyAgeResult(
            previous_month=previous.strftime("%Y-%m"),
            current_month=current.strftime("%Y-%m"),
            previous_month_income_rub=income,
            current_month_expense_rub=expense_abs,
            coverage=coverage,
            is_covered=coverage is None or coverage >= 1,
        )


def _shift_month(value: date, offset: int) -> date:
    """Сдвинуть первое число месяца на ``offset`` месяцев."""
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)
```

Добавить `from zoneinfo import ZoneInfo` в импорты модуля.

- [ ] **Step 5: Прогнать тест и убедиться, что он проходит**

Run: `cd backend && uv run pytest tests/test_summary_money_age.py -v`
Expected: PASS — пять тестов.

- [ ] **Step 6: Добавить роут**

В `backend/app/domains/summary/routes.py` дополнить импорт схем именем
`MoneyAgeResult` и добавить:

```python
@router.get("/money-age", response_model=ApiResponse[MoneyAgeResult])
async def money_age(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[MoneyAgeResult]:
    result = await service.money_age(user.id, user.timezone)
    return ApiResponse(data=result)
```

- [ ] **Step 7: Прогнать весь набор проверок**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q`
Expected: всё чисто, все тесты проходят.

- [ ] **Step 8: Коммит**

```bash
git add backend/app/domains/summary/ backend/tests/test_summary_money_age.py
git commit -m "feat(summary): добавить расчёт возраста денег"
```

---

# Часть C. Бот

## Task 4: Скелет сервиса и конфигурация

**Files:**
- Create: `bot/pyproject.toml`
- Create: `bot/src/anfinances_bot/__init__.py`
- Create: `bot/src/anfinances_bot/config.py`
- Create: `bot/tests/__init__.py`
- Create: `bot/tests/conftest.py`
- Create: `bot/tests/test_config.py`
- Modify: `.github/workflows/deploy.yml` (новая job проверок бота)

**Interfaces:**
- Produces: `BotSettings` с полями `telegram_bot_token: SecretStr`,
  `telegram_allowed_user_ids: frozenset[int]`, `anthropic_api_key: SecretStr`,
  `openai_api_key: SecretStr`, `anfinances_base_url: str`,
  `single_user_email: str`, `single_user_password: SecretStr`,
  `bot_default_account_name: str`, `bot_quiet_hours: tuple[int, int]`,
  `bot_budget_meeting_day: int`, `speech_model: str`;
  функция `get_bot_settings() -> BotSettings` (кэшируется).

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_config.py`:

```python
"""Разбор настроек бота из окружения."""

import pytest
from pydantic import ValidationError

from anfinances_bot.config import BotSettings


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_ALLOWED_USER_IDS": "111",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
        "SINGLE_USER_EMAIL": "me@example.com",
        "SINGLE_USER_PASSWORD": "very-long-password-value",
        "BOT_DEFAULT_ACCOUNTS": "RUB=Альфа",
    }
    base.update(overrides)
    return base


def test_parses_single_allowed_id(monkeypatch) -> None:
    for key, value in _env().items():
        monkeypatch.setenv(key, value)
    settings = BotSettings()
    assert settings.telegram_allowed_user_ids == frozenset({111})


def test_parses_comma_separated_ids(monkeypatch) -> None:
    for key, value in _env(
        TELEGRAM_ALLOWED_USER_IDS="111, 222,333"
    ).items():
        monkeypatch.setenv(key, value)
    settings = BotSettings()
    assert settings.telegram_allowed_user_ids == frozenset(
        {111, 222, 333}
    )


def test_empty_allowlist_is_rejected(monkeypatch) -> None:
    """Пустой белый список открыл бы бота всему интернету."""
    for key, value in _env(TELEGRAM_ALLOWED_USER_IDS="").items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        BotSettings()


def test_quiet_hours_default_and_parse(monkeypatch) -> None:
    for key, value in _env().items():
        monkeypatch.setenv(key, value)
    assert BotSettings().bot_quiet_hours == (23, 9)

    monkeypatch.setenv("BOT_QUIET_HOURS", "0-7")
    assert BotSettings().bot_quiet_hours == (0, 7)


def test_bad_quiet_hours_rejected(monkeypatch) -> None:
    for key, value in _env(BOT_QUIET_HOURS="25-9").items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        BotSettings()


def test_secrets_are_not_in_repr(monkeypatch) -> None:
    for key, value in _env().items():
        monkeypatch.setenv(key, value)
    text = repr(BotSettings())
    assert "sk-ant-test" not in text
    assert "very-long-password-value" not in text
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_config.py -v`
Expected: FAIL — проект ещё не создан.

- [ ] **Step 3: Создать проект**

Создать `bot/pyproject.toml`:

```toml
[project]
name = "anfinances-bot"
version = "0.1.0"
description = "anfinances — телеграм-бот: ввод трат голосом и текстом."
requires-python = ">=3.13"
license = "AGPL-3.0-or-later"

dependencies = [
    "aiogram>=3.15.0",
    "anthropic>=0.69.0",
    "openai>=1.60.0",
    "httpx>=0.28.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "respx>=0.22.0",
]

[tool.uv]
package = false

[tool.ruff]
line-length = 79
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "S", "C4", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]

[tool.mypy]
python_version = "3.13"
strict = true
mypy_path = "src"

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

Создать пустые `bot/src/anfinances_bot/__init__.py` и `bot/tests/__init__.py`.

Создать `bot/tests/conftest.py`:

```python
"""Общие фикстуры тестов бота."""

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Настройки кэшируются — сбрасываем между тестами."""
    from anfinances_bot.config import get_bot_settings

    get_bot_settings.cache_clear()
```

- [ ] **Step 4: Реализовать конфигурацию**

Создать `bot/src/anfinances_bot/config.py`:

```python
"""Настройки бота — только из переменных окружения.

Секреты в код не попадают никогда; всё приходит из .env, который
раскладывает деплой из GitHub Secrets.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["BotSettings", "get_bot_settings"]


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: SecretStr
    telegram_allowed_user_ids: frozenset[int]

    anthropic_api_key: SecretStr
    openai_api_key: SecretStr
    speech_model: str = "whisper-1"

    # Внутри compose-сети сайт доступен по имени сервиса.
    anfinances_base_url: str = "http://backend:8000/api/v1"
    single_user_email: str
    single_user_password: SecretStr

    bot_default_account_name: str
    bot_quiet_hours: tuple[int, int] = (23, 9)
    bot_budget_meeting_day: int = Field(default=1, ge=1, le=28)

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> object:
        """Принять "111, 222" — так его удобнее держать в секрете."""
        if not isinstance(value, str):
            return value
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return frozenset(int(p) for p in parts)

    @field_validator("telegram_allowed_user_ids")
    @classmethod
    def _reject_empty(cls, value: frozenset[int]) -> frozenset[int]:
        """Пустой список открыл бы финансы любому, кто найдёт бота."""
        if not value:
            raise ValueError(
                "TELEGRAM_ALLOWED_USER_IDS не может быть пустым."
            )
        return value

    @field_validator("bot_quiet_hours", mode="before")
    @classmethod
    def _parse_quiet_hours(cls, value: object) -> object:
        """Принять "23-9" — час начала и час конца тишины."""
        if not isinstance(value, str):
            return value
        try:
            start_s, end_s = value.split("-")
            start, end = int(start_s), int(end_s)
        except ValueError as exc:
            raise ValueError(
                "BOT_QUIET_HOURS должен быть вида 23-9."
            ) from exc
        if not (0 <= start <= 23 and 0 <= end <= 23):
            raise ValueError("Часы тишины должны быть в диапазоне 0..23.")
        return (start, end)


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
```

- [ ] **Step 5: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_config.py -v`
Expected: PASS — шесть тестов.

- [ ] **Step 6: Добавить проверки бота в CI**

В `.github/workflows/deploy.yml` добавить job по образцу существующей
backend-джобы:

```yaml
  bot-checks:
    name: Bot — lint, types, tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Ruff
        working-directory: bot
        run: uv run ruff check . && uv run ruff format --check .
      - name: Mypy
        working-directory: bot
        run: uv run mypy src
      - name: Pytest
        working-directory: bot
        run: uv run pytest -q
```

- [ ] **Step 7: Прогнать полный набор проверок бота**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
Expected: всё чисто, шесть тестов проходят.

- [ ] **Step 8: Коммит**

```bash
git add bot/ .github/workflows/deploy.yml
git commit -m "feat(bot): создать сервис и конфигурацию"
```

---

## Task 5: Клиент anfinances

**Files:**
- Create: `bot/src/anfinances_bot/anfinances/__init__.py`
- Create: `bot/src/anfinances_bot/anfinances/schemas.py`
- Create: `bot/src/anfinances_bot/anfinances/client.py`
- Create: `bot/tests/test_anfinances_client.py`

**Interfaces:**
- Consumes: `BotSettings`.
- Produces: `AnfinancesClient(settings)` с методами
  `login() -> None`, `request(method, path, **kwargs) -> dict`,
  `me() -> UserProfile`, `accounts() -> list[AccountRead]`,
  `categories() -> list[CategoryRead]`.
  Схемы: `UserProfile(id: str, email: str, timezone: str,
  default_currency: str)`, `AccountRead(id: str, name: str,
  currency_code: str, current_balance: Decimal | None)`,
  `CategoryRead(id: str, name: str, kind: str, parent_id: str | None)`.
- Исключение `AnfinancesUnavailableError` — сеть недоступна или 5xx.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_anfinances_client.py`:

```python
"""Клиент anfinances: логин, перелогин, ошибки."""

import httpx
import pytest
import respx

from anfinances_bot.anfinances.client import (
    AnfinancesClient,
    AnfinancesUnavailableError,
)
from anfinances_bot.config import BotSettings

BASE = "http://backend:8000/api/v1"


def _settings(monkeypatch) -> BotSettings:
    for key, value in {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_ALLOWED_USER_IDS": "111",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
        "SINGLE_USER_EMAIL": "me@example.com",
        "SINGLE_USER_PASSWORD": "very-long-password-value",
        "BOT_DEFAULT_ACCOUNTS": "RUB=Альфа",
    }.items():
        monkeypatch.setenv(key, value)
    return BotSettings()


@respx.mock
async def test_logs_in_before_first_request(monkeypatch) -> None:
    login = respx.post(f"{BASE}/auth/login").mock(
        return_value=httpx.Response(
            200, json={"data": {"access_token": "tok-1"}}
        )
    )
    accounts = respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AnfinancesClient(_settings(monkeypatch))
    await client.accounts()

    assert login.called
    assert accounts.called
    sent = accounts.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok-1"
    await client.aclose()


@respx.mock
async def test_relogins_once_on_401(monkeypatch) -> None:
    tokens = iter(["tok-old", "tok-new"])
    respx.post(f"{BASE}/auth/login").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"data": {"access_token": next(tokens)}}
        )
    )
    responses = iter(
        [
            httpx.Response(401, json={"detail": "expired"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    route = respx.get(f"{BASE}/accounts").mock(
        side_effect=lambda request: next(responses)
    )

    client = AnfinancesClient(_settings(monkeypatch))
    await client.accounts()

    assert route.call_count == 2
    assert (
        route.calls[1].request.headers["authorization"]
        == "Bearer tok-new"
    )
    await client.aclose()


@respx.mock
async def test_server_error_raises_unavailable(monkeypatch) -> None:
    respx.post(f"{BASE}/auth/login").mock(
        return_value=httpx.Response(
            200, json={"data": {"access_token": "tok"}}
        )
    )
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(503, text="down")
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesUnavailableError):
        await client.accounts()
    await client.aclose()


@respx.mock
async def test_network_error_raises_unavailable(monkeypatch) -> None:
    respx.post(f"{BASE}/auth/login").mock(
        side_effect=httpx.ConnectError("нет сети")
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesUnavailableError):
        await client.accounts()
    await client.aclose()


@respx.mock
async def test_parses_accounts(monkeypatch) -> None:
    respx.post(f"{BASE}/auth/login").mock(
        return_value=httpx.Response(
            200, json={"data": {"access_token": "tok"}}
        )
    )
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "a-1",
                        "name": "Альфа",
                        "currency_code": "RUB",
                        "current_balance": "1500.0000",
                    }
                ]
            },
        )
    )

    client = AnfinancesClient(_settings(monkeypatch))
    accounts = await client.accounts()
    assert accounts[0].name == "Альфа"
    assert accounts[0].currency_code == "RUB"
    await client.aclose()
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_anfinances_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.anfinances'`.

- [ ] **Step 3: Написать схемы**

Создать `bot/src/anfinances_bot/anfinances/__init__.py` (пустой) и
`bot/src/anfinances_bot/anfinances/schemas.py`:

```python
"""Модели ответов anfinances API — только те поля, что нужны боту."""

from decimal import Decimal

from pydantic import BaseModel

__all__ = ["AccountRead", "CategoryRead", "UserProfile"]


class UserProfile(BaseModel):
    id: str
    email: str
    timezone: str
    default_currency: str


class AccountRead(BaseModel):
    id: str
    name: str
    currency_code: str
    current_balance: Decimal | None = None


class CategoryRead(BaseModel):
    id: str
    name: str
    kind: str
    parent_id: str | None = None
```

- [ ] **Step 4: Реализовать клиент**

Создать `bot/src/anfinances_bot/anfinances/client.py`:

```python
"""HTTP-клиент к anfinances.

Бот — обычный потребитель публичного API: входит теми же учётными
данными единственного пользователя и не имеет доступа к базе.
Токен живёт 15 минут, поэтому по первой 401 клиент молча
перелогинивается и повторяет запрос ровно один раз.
"""

import logging
from typing import Any

import httpx

from anfinances_bot.anfinances.schemas import (
    AccountRead,
    CategoryRead,
    UserProfile,
)
from anfinances_bot.config import BotSettings

logger = logging.getLogger("anfinances_bot.client")

__all__ = ["AnfinancesClient", "AnfinancesError", "AnfinancesUnavailableError"]


class AnfinancesError(RuntimeError):
    """Ошибка обращения к anfinances."""


class AnfinancesUnavailableError(AnfinancesError):
    """Сайт недоступен: сеть, таймаут или 5xx."""


class AnfinancesClient:
    def __init__(self, settings: BotSettings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._http = httpx.AsyncClient(
            base_url=settings.anfinances_base_url,
            timeout=httpx.Timeout(15.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def login(self) -> None:
        payload = {
            "email": self._settings.single_user_email,
            "password": (
                self._settings.single_user_password.get_secret_value()
            ),
        }
        try:
            response = await self._http.post("/auth/login", json=payload)
        except httpx.HTTPError as exc:
            raise AnfinancesUnavailableError(str(exc)) from exc
        if response.status_code >= 500:
            raise AnfinancesUnavailableError(f"login {response.status_code}")
        if response.status_code != 200:
            raise AnfinancesError(
                "Не удалось войти в anfinances: проверьте "
                "SINGLE_USER_EMAIL и SINGLE_USER_PASSWORD."
            )
        self._token = response.json()["data"]["access_token"]

    async def request(
        self, method: str, path: str, **kwargs: Any
    ) -> Any:
        """Выполнить запрос, при 401 перелогиниться и повторить."""
        if self._token is None:
            await self.login()

        response = await self._send(method, path, **kwargs)
        if response.status_code == 401:
            await self.login()
            response = await self._send(method, path, **kwargs)

        if response.status_code >= 500:
            raise AnfinancesUnavailableError(
                f"{method} {path} → {response.status_code}"
            )
        if response.status_code >= 400:
            raise AnfinancesError(_error_text(response))
        if response.status_code == 204 or not response.content:
            return None
        return response.json().get("data")

    async def _send(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            return await self._http.request(
                method, path, headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise AnfinancesUnavailableError(str(exc)) from exc

    async def me(self) -> UserProfile:
        return UserProfile.model_validate(
            await self.request("GET", "/auth/me")
        )

    async def accounts(self) -> list[AccountRead]:
        rows = await self.request("GET", "/accounts")
        return [AccountRead.model_validate(row) for row in rows]

    async def categories(self) -> list[CategoryRead]:
        rows = await self.request("GET", "/categories")
        return [CategoryRead.model_validate(row) for row in rows]


def _error_text(response: httpx.Response) -> str:
    """Достать человеческий текст ошибки из ответа API."""
    try:
        body = response.json()
    except ValueError:
        return f"Ошибка {response.status_code}"
    for key in ("detail", "message", "error"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return f"Ошибка {response.status_code}"
```

- [ ] **Step 5: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_anfinances_client.py -v`
Expected: PASS — пять тестов.

- [ ] **Step 6: Прогнать полный набор проверок**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
Expected: всё чисто.

- [ ] **Step 7: Коммит**

```bash
git add bot/src/anfinances_bot/anfinances/ bot/tests/test_anfinances_client.py
git commit -m "feat(bot): добавить клиент anfinances API"
```

---

## Task 6: Белый список и приём сообщений

**Files:**
- Create: `bot/src/anfinances_bot/telegram/__init__.py`
- Create: `bot/src/anfinances_bot/telegram/access.py`
- Create: `bot/tests/test_access.py`

**Interfaces:**
- Consumes: `BotSettings.telegram_allowed_user_ids`.
- Produces: `AllowlistMiddleware(allowed: frozenset[int])` — `BaseMiddleware`
  aiogram; пропускает событие дальше только для разрешённых ID, иначе отвечает
  отказом и возвращает `None`, не вызывая обработчик.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_access.py`:

```python
"""Белый список: чужие не доходят до обработчика."""

from dataclasses import dataclass, field
from typing import Any

from anfinances_bot.telegram.access import AllowlistMiddleware


@dataclass
class _User:
    id: int


@dataclass
class _Event:
    from_user: _User
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.answers.append(text)


async def _handler(event: Any, data: dict[str, Any]) -> str:
    return "обработано"


async def test_allowed_user_passes() -> None:
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=_User(id=111))
    result = await middleware(_handler, event, {})
    assert result == "обработано"
    assert event.answers == []


async def test_foreign_user_blocked() -> None:
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=_User(id=999))
    result = await middleware(_handler, event, {})
    assert result is None
    assert len(event.answers) == 1


async def test_event_without_user_blocked() -> None:
    """Без отправителя пропускать нельзя — это не личный чат."""
    middleware = AllowlistMiddleware(frozenset({111}))
    event = _Event(from_user=None)  # type: ignore[arg-type]
    result = await middleware(_handler, event, {})
    assert result is None
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_access.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.telegram'`.

- [ ] **Step 3: Реализовать middleware**

Создать `bot/src/anfinances_bot/telegram/__init__.py` (пустой) и
`bot/src/anfinances_bot/telegram/access.py`:

```python
"""Белый список Telegram-ID.

Юзернейм бота угадывается. Без этой проверки любой, кто набредёт на
бота, сможет читать финансы и писать операции. Отсечка происходит
до распознавания речи и до обращения к модели — чужой запрос не
стоит ни копейки и ничего не раскрывает.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

logger = logging.getLogger("anfinances_bot.access")

__all__ = ["AllowlistMiddleware"]

_DENIED = "Этот бот личный. Доступ только у владельца."


class AllowlistMiddleware(BaseMiddleware):
    def __init__(self, allowed: frozenset[int]) -> None:
        self._allowed = allowed

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id in self._allowed:
            return await handler(event, data)

        logger.warning("Отклонён доступ, telegram_id=%s", user_id)
        answer = getattr(event, "answer", None)
        if answer is not None:
            await answer(_DENIED)
        return None
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_access.py -v`
Expected: PASS — три теста.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/telegram/ bot/tests/test_access.py
git commit -m "feat(bot): ограничить доступ белым списком"
```

---

## Task 7: Разрешение счёта

Реализация решения Р-6 из спека: пять шагов, первое сработавшее правило
выигрывает.

**Files:**
- Create: `bot/src/anfinances_bot/resolve/__init__.py`
- Create: `bot/src/anfinances_bot/resolve/accounts.py`
- Create: `bot/tests/test_account_resolution.py`

**Interfaces:**
- Consumes: `AccountRead` из `anfinances_bot.anfinances.schemas`.
- Produces: `resolve_account(accounts, *, named, currency_code,
  history_account_id, default_name) -> AccountResolution`, где
  `AccountResolution` — датакласс с полями `account: AccountRead | None`
  и `candidates: list[AccountRead]`. Если `account is None`, вызывающий
  показывает кнопки из `candidates`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_account_resolution.py`:

```python
"""Пять шагов разрешения счёта (решение Р-6)."""

from decimal import Decimal

from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.resolve.accounts import resolve_account

ALFA = AccountRead(
    id="a-1",
    name="Альфа",
    currency_code="RUB",
    current_balance=Decimal("100"),
)
SBER = AccountRead(
    id="a-2",
    name="Сбер карта",
    currency_code="RUB",
    current_balance=Decimal("200"),
)
CASH_UZS = AccountRead(
    id="a-3",
    name="Наличные сумы",
    currency_code="UZS",
    current_balance=Decimal("500000"),
)
ALL = [ALFA, SBER, CASH_UZS]


def test_step1_named_account_wins() -> None:
    result = resolve_account(
        ALL,
        named="сбер",
        currency_code="RUB",
        history_account_id="a-1",
        default_name="Альфа",
    )
    assert result.account == SBER


def test_step1_matching_is_case_insensitive() -> None:
    result = resolve_account(
        ALL,
        named="АЛЬФА",
        currency_code=None,
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_step2_single_account_in_currency() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="UZS",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == CASH_UZS


def test_step3_history_decides() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="RUB",
        history_account_id="a-2",
        default_name="Альфа",
    )
    assert result.account == SBER


def test_step4_default_account() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="RUB",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_step5_buttons_when_nothing_helps() -> None:
    """Валюта не совпадает с умолчанием, истории нет, счетов много."""
    eur_a = AccountRead(id="e-1", name="EUR A", currency_code="EUR")
    eur_b = AccountRead(id="e-2", name="EUR B", currency_code="EUR")
    result = resolve_account(
        [*ALL, eur_a, eur_b],
        named=None,
        currency_code="EUR",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account is None
    assert result.candidates == [eur_a, eur_b]


def test_history_ignored_if_currency_mismatches() -> None:
    """Подсказка из истории не должна ломать валюту операции."""
    result = resolve_account(
        ALL,
        named=None,
        currency_code="UZS",
        history_account_id="a-1",
        default_name="Альфа",
    )
    assert result.account == CASH_UZS


def test_unknown_default_name_falls_to_buttons() -> None:
    eur_a = AccountRead(id="e-1", name="EUR A", currency_code="EUR")
    eur_b = AccountRead(id="e-2", name="EUR B", currency_code="EUR")
    result = resolve_account(
        [eur_a, eur_b],
        named=None,
        currency_code="EUR",
        history_account_id=None,
        default_name="Нет такого счёта",
    )
    assert result.account is None
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_account_resolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.resolve'`.

- [ ] **Step 3: Реализовать разрешение**

Создать `bot/src/anfinances_bot/resolve/__init__.py` (пустой) и
`bot/src/anfinances_bot/resolve/accounts.py`:

```python
"""Выбор счёта для операции (решение Р-6).

Цена ошибки со счётом выше, чем с категорией: неправильная категория
портит отчёт и это заметно, неправильный счёт разводит баланс с
реальностью и обнаруживается через неделю. Поэтому когда уверенности
нет — спрашиваем кнопками, а не угадываем.
"""

from dataclasses import dataclass

from anfinances_bot.anfinances.schemas import AccountRead

__all__ = ["AccountResolution", "resolve_account"]


@dataclass(frozen=True)
class AccountResolution:
    """Либо счёт выбран, либо надо показать ``candidates`` кнопками."""

    account: AccountRead | None
    candidates: list[AccountRead]


def resolve_account(
    accounts: list[AccountRead],
    *,
    named: str | None,
    currency_code: str | None,
    history_account_id: str | None,
    default_name: str,
) -> AccountResolution:
    """Разрешить счёт по пяти правилам сверху вниз."""
    # 1. Счёт назван во фразе.
    if named:
        needle = named.casefold()
        for account in accounts:
            if needle in account.name.casefold():
                return AccountResolution(account, [])

    in_currency = [
        a
        for a in accounts
        if currency_code is None or a.currency_code == currency_code
    ]

    # 2. В этой валюте счёт ровно один.
    if len(in_currency) == 1:
        return AccountResolution(in_currency[0], [])

    # 3. История по категории указывает на счёт нужной валюты.
    if history_account_id is not None:
        for account in in_currency:
            if account.id == history_account_id:
                return AccountResolution(account, [])

    # 4. Счёт по умолчанию, если он этой же валюты.
    needle = default_name.casefold()
    for account in in_currency:
        if account.name.casefold() == needle:
            return AccountResolution(account, [])

    # 5. Ничего не помогло — пусть выберет пользователь.
    return AccountResolution(None, in_currency)
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_account_resolution.py -v`
Expected: PASS — восемь тестов.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/resolve/ bot/tests/test_account_resolution.py
git commit -m "feat(bot): разрешать счёт по пяти правилам"
```

---

## Task 8: Дерево категорий

Реализация решения Р-7: дерево путями в контекст и подсказка из истории.

**Files:**
- Create: `bot/src/anfinances_bot/resolve/categories.py`
- Create: `bot/tests/test_category_resolution.py`

**Interfaces:**
- Consumes: `CategoryRead`.
- Produces: `build_category_paths(categories, kind) -> list[CategoryPath]`,
  где `CategoryPath` — датакласс `(id: str, path: str)` и `path` имеет вид
  `"Еда → Кофейни"`; `find_category_by_path(paths, path) -> CategoryPath | None`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_category_resolution.py`:

```python
"""Дерево категорий путями (решение Р-7)."""

from anfinances_bot.anfinances.schemas import CategoryRead
from anfinances_bot.resolve.categories import (
    build_category_paths,
    find_category_by_path,
)

FOOD = CategoryRead(id="c-1", name="Еда", kind="expense")
COFFEE = CategoryRead(
    id="c-2", name="Кофейни", kind="expense", parent_id="c-1"
)
GROCERIES = CategoryRead(
    id="c-3", name="Продукты", kind="expense", parent_id="c-1"
)
SALARY = CategoryRead(id="c-4", name="Зарплата", kind="income")
ALL = [FOOD, COFFEE, GROCERIES, SALARY]


def test_builds_parent_and_child_paths() -> None:
    paths = build_category_paths(ALL, kind="expense")
    rendered = {p.path for p in paths}
    assert rendered == {
        "Еда",
        "Еда → Кофейни",
        "Еда → Продукты",
    }


def test_filters_by_kind() -> None:
    paths = build_category_paths(ALL, kind="income")
    assert [p.path for p in paths] == ["Зарплата"]


def test_paths_are_sorted() -> None:
    paths = build_category_paths(ALL, kind="expense")
    assert [p.path for p in paths] == sorted(p.path for p in paths)


def test_find_by_exact_path() -> None:
    paths = build_category_paths(ALL, kind="expense")
    found = find_category_by_path(paths, "Еда → Кофейни")
    assert found is not None
    assert found.id == "c-2"


def test_find_is_case_and_space_insensitive() -> None:
    paths = build_category_paths(ALL, kind="expense")
    found = find_category_by_path(paths, "еда→кофейни")
    assert found is not None
    assert found.id == "c-2"


def test_find_unknown_returns_none() -> None:
    paths = build_category_paths(ALL, kind="expense")
    assert find_category_by_path(paths, "Транспорт") is None


def test_orphan_child_keeps_own_name() -> None:
    """Родителя нет в наборе — не теряем категорию совсем."""
    orphan = CategoryRead(
        id="c-9", name="Такси", kind="expense", parent_id="нет-такого"
    )
    paths = build_category_paths([orphan], kind="expense")
    assert [p.path for p in paths] == ["Такси"]
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_category_resolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.resolve.categories'`.

- [ ] **Step 3: Реализовать построение путей**

Создать `bot/src/anfinances_bot/resolve/categories.py`:

```python
"""Дерево категорий в виде путей (решение Р-7).

Плоский список имён теряет структуру: «Кофейни» без «Еда» ничего не
говорит ни модели, ни пользователю. Пути вида «Еда → Кофейни» решают
и это, и показ в карточке операции.
"""

from dataclasses import dataclass

from anfinances_bot.anfinances.schemas import CategoryRead

__all__ = [
    "CategoryPath",
    "build_category_paths",
    "find_category_by_path",
]

SEPARATOR = " → "


@dataclass(frozen=True)
class CategoryPath:
    id: str
    path: str


def build_category_paths(
    categories: list[CategoryRead], kind: str
) -> list[CategoryPath]:
    """Построить отсортированные пути для категорий нужного типа."""
    by_id = {c.id: c for c in categories}
    paths: list[CategoryPath] = []
    for category in categories:
        if category.kind != kind:
            continue
        parent = (
            by_id.get(category.parent_id)
            if category.parent_id is not None
            else None
        )
        path = (
            f"{parent.name}{SEPARATOR}{category.name}"
            if parent is not None
            else category.name
        )
        paths.append(CategoryPath(id=category.id, path=path))
    paths.sort(key=lambda p: p.path)
    return paths


def find_category_by_path(
    paths: list[CategoryPath], path: str
) -> CategoryPath | None:
    """Найти категорию по пути, игнорируя регистр и пробелы."""
    needle = _normalize(path)
    for candidate in paths:
        if _normalize(candidate.path) == needle:
            return candidate
    return None


def _normalize(value: str) -> str:
    return value.casefold().replace(" ", "")
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_category_resolution.py -v`
Expected: PASS — семь тестов.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/resolve/categories.py bot/tests/test_category_resolution.py
git commit -m "feat(bot): собирать дерево категорий путями"
```

---

## Task 9: Инструменты агента

**Files:**
- Create: `bot/src/anfinances_bot/agent/__init__.py`
- Create: `bot/src/anfinances_bot/agent/tools.py`
- Create: `bot/tests/test_tools.py`

**Interfaces:**
- Consumes: `AnfinancesClient`, `resolve_account`, `build_category_paths`,
  `find_category_by_path`.
- Produces: `ToolBox(client, default_account_name)` с атрибутом `tools` —
  список инструментов для `tool_runner`, и с атрибутом `last_created_id: str | None`
  (идентификатор последней созданной операции, нужен для карточки).
  Методы, оборачиваемые в инструменты: `create_expense`, `create_income`,
  `create_transfer`, `list_accounts`, `get_capital`, `get_by_category`,
  `get_budget`, `list_transactions`, `get_credits`, `get_money_age`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_tools.py`:

```python
"""Инструменты агента: запись и чтение через API."""

from decimal import Decimal
from typing import Any

import pytest

from anfinances_bot.agent.tools import ToolBox
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._accounts = [
            AccountRead(id="a-1", name="Альфа", currency_code="RUB"),
            AccountRead(
                id="a-3", name="Наличные сумы", currency_code="UZS"
            ),
        ]
        self._categories = [
            CategoryRead(id="c-1", name="Еда", kind="expense"),
            CategoryRead(
                id="c-2",
                name="Кофейни",
                kind="expense",
                parent_id="c-1",
            ),
        ]

    async def accounts(self) -> list[AccountRead]:
        return self._accounts

    async def categories(self) -> list[CategoryRead]:
        return self._categories

    async def request(
        self, method: str, path: str, **kwargs: Any
    ) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "POST" and path == "/transactions":
            return {"id": "tx-1"}
        return []


def _toolbox() -> tuple[ToolBox, _FakeClient]:
    client = _FakeClient()
    return ToolBox(client, default_account_name="Альфа"), client


async def test_expense_is_sent_with_positive_amount() -> None:
    """API принимает положительную сумму; знак ставит бэкенд."""
    box, client = _toolbox()
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/transactions")
    body = kwargs["json"]
    assert Decimal(body["amount"]) == Decimal("300")
    assert body["kind"] == "expense"
    assert body["account_id"] == "a-1"
    assert body["category_id"] == "c-2"


async def test_expense_records_created_id() -> None:
    box, _ = _toolbox()
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
    )
    assert box.last_created_id == "tx-1"


async def test_unknown_category_is_reported_not_guessed() -> None:
    box, _ = _toolbox()
    result = await box.create_expense(
        amount="300",
        category_path="Такого нет",
        account_name="Альфа",
    )
    assert "не найдена" in result.casefold()


async def test_ambiguous_account_asks_instead_of_writing() -> None:
    box, client = _toolbox()
    result = await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name=None,
        currency_code="EUR",
    )
    assert "уточнить" in result.casefold()
    assert client.calls == []


async def test_transfer_requires_both_amounts() -> None:
    """Решение Р-9: вторую сумму досчитывать нельзя."""
    box, client = _toolbox()
    with pytest.raises(ValueError):
        await box.create_transfer(
            from_account_name="Альфа",
            to_account_name="Наличные сумы",
            amount_from="20000",
            amount_to=None,  # type: ignore[arg-type]
        )
    assert client.calls == []


async def test_transfer_posts_both_amounts() -> None:
    box, client = _toolbox()
    await box.create_transfer(
        from_account_name="Альфа",
        to_account_name="Наличные сумы",
        amount_from="20000",
        amount_to="2800000",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/transfers")
    assert kwargs["json"]["amount_from"] == "20000"
    assert kwargs["json"]["amount_to"] == "2800000"
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.agent'`.

- [ ] **Step 3: Реализовать инструменты**

Создать `bot/src/anfinances_bot/agent/__init__.py` (пустой) и
`bot/src/anfinances_bot/agent/tools.py`:

```python
"""Инструменты агента.

Каждый инструмент — тонкая обёртка над HTTP-вызовом anfinances.
Инструментов на удаление счетов, категорий и кредитов, на правку
настроек, валют и начального баланса здесь нет — это осознанная
граница полномочий бота.
"""

from datetime import date
from typing import Any, Protocol

from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead
from anfinances_bot.resolve.accounts import resolve_account
from anfinances_bot.resolve.categories import (
    build_category_paths,
    find_category_by_path,
)

__all__ = ["ToolBox"]


class _Client(Protocol):
    async def accounts(self) -> list[AccountRead]: ...
    async def categories(self) -> list[CategoryRead]: ...
    async def request(
        self, method: str, path: str, **kwargs: Any
    ) -> Any: ...


class ToolBox:
    def __init__(
        self, client: _Client, default_account_name: str
    ) -> None:
        self._client = client
        self._default_account_name = default_account_name
        self.last_created_id: str | None = None
        self.pending_accounts: list[AccountRead] = []

    async def _ordinary(
        self,
        kind: str,
        amount: str,
        category_path: str,
        account_name: str | None,
        currency_code: str | None,
        when: str | None,
        comment: str | None,
    ) -> str:
        accounts = await self._client.accounts()
        categories = await self._client.categories()

        paths = build_category_paths(categories, kind=kind)
        category = find_category_by_path(paths, category_path)
        if category is None:
            available = ", ".join(p.path for p in paths[:20])
            return (
                f"Категория «{category_path}» не найдена. "
                f"Доступные: {available}"
            )

        resolution = resolve_account(
            accounts,
            named=account_name,
            currency_code=currency_code,
            history_account_id=None,
            default_name=self._default_account_name,
        )
        if resolution.account is None:
            self.pending_accounts = resolution.candidates
            names = ", ".join(a.name for a in resolution.candidates)
            return (
                "Надо уточнить счёт у пользователя. "
                f"Варианты: {names}"
            )

        body = {
            "account_id": resolution.account.id,
            "kind": kind,
            "amount": str(amount),
            "date": (when or date.today().isoformat()),
            "category_id": category.id,
        }
        if comment:
            body["comment"] = comment

        created = await self._client.request(
            "POST", "/transactions", json=body
        )
        self.last_created_id = created["id"]
        return (
            f"Записано: {category.path} — {amount}, "
            f"{resolution.account.name}"
        )

    async def create_expense(
        self,
        amount: str,
        category_path: str,
        account_name: str | None = None,
        currency_code: str | None = None,
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Записать расход. Сумма всегда положительная."""
        return await self._ordinary(
            "expense",
            amount,
            category_path,
            account_name,
            currency_code,
            when,
            comment,
        )

    async def create_income(
        self,
        amount: str,
        category_path: str,
        account_name: str | None = None,
        currency_code: str | None = None,
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Записать доход. Сумма всегда положительная."""
        return await self._ordinary(
            "income",
            amount,
            category_path,
            account_name,
            currency_code,
            when,
            comment,
        )

    async def create_transfer(
        self,
        from_account_name: str,
        to_account_name: str,
        amount_from: str,
        amount_to: str,
        when: str | None = None,
        fee_amount: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Перевод между счетами.

        Обе суммы обязательны: именно пара реальных сумм фиксирует
        фактический курс пользователя (решение Р-9). Досчитывать
        вторую по рыночному курсу нельзя.
        """
        if not amount_from or not amount_to:
            raise ValueError(
                "Нужны обе суммы: сколько ушло и сколько пришло."
            )
        accounts = await self._client.accounts()
        source = _by_name(accounts, from_account_name)
        target = _by_name(accounts, to_account_name)
        if source is None or target is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"

        body: dict[str, Any] = {
            "from_account_id": source.id,
            "to_account_id": target.id,
            "amount_from": str(amount_from),
            "amount_to": str(amount_to),
            "date": (when or date.today().isoformat()),
        }
        if fee_amount:
            body["fee_amount"] = str(fee_amount)
        if comment:
            body["comment"] = comment

        await self._client.request("POST", "/transfers", json=body)
        return (
            f"Перевод записан: {source.name} → {target.name}, "
            f"{amount_from} → {amount_to}"
        )

    async def list_accounts(self) -> str:
        """Список счетов с остатками."""
        accounts = await self._client.accounts()
        return "\n".join(
            f"{a.name}: {a.current_balance} {a.currency_code}"
            for a in accounts
        )

    async def get_capital(self) -> str:
        """Капитал: остатки по счетам и итог в рублях."""
        data = await self._client.request("GET", "/summary/dashboard")
        return str(data)

    async def get_by_category(self, month: str) -> str:
        """Расходы по категориям за месяц YYYY-MM."""
        data = await self._client.request(
            "GET", "/summary/by-category", params={"month": month}
        )
        return str(data)

    async def get_budget(self, month: str) -> str:
        """Бюджет за месяц YYYY-MM."""
        data = await self._client.request(
            "GET", "/budgets", params={"month": month}
        )
        return str(data)

    async def list_transactions(
        self, limit: int = 20, category_id: str | None = None
    ) -> str:
        """Последние операции; помогает угадать категорию по истории."""
        params: dict[str, Any] = {"limit": limit}
        if category_id:
            params["category_id"] = category_id
        data = await self._client.request(
            "GET", "/transactions", params=params
        )
        return str(data)

    async def get_credits(self) -> str:
        """Кредиты и графики платежей."""
        data = await self._client.request("GET", "/credits")
        return str(data)

    async def get_money_age(self) -> str:
        """Покрыты ли текущие траты доходом прошлого месяца."""
        data = await self._client.request("GET", "/summary/money-age")
        return str(data)


def _by_name(
    accounts: list[AccountRead], name: str
) -> AccountRead | None:
    needle = name.casefold()
    for account in accounts:
        if needle in account.name.casefold():
            return account
    return None
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_tools.py -v`
Expected: PASS — шесть тестов.

- [ ] **Step 5: Собрать список инструментов для агента**

Дописать в конец `ToolBox.__init__` сборку `self.tools`. Декоратор
`beta_async_tool` берёт имя, описание и схему параметров из сигнатуры и
докстроки метода, поэтому докстроки выше — часть контракта, а не украшение:

```python
from anthropic import beta_async_tool
```

и в конце `__init__`:

```python
        # Схемы инструментов выводятся из сигнатур и докстрок методов.
        self.tools = [
            beta_async_tool(method)
            for method in (
                self.create_expense,
                self.create_income,
                self.create_transfer,
                self.list_accounts,
                self.get_capital,
                self.get_by_category,
                self.get_budget,
                self.list_transactions,
                self.get_credits,
                self.get_money_age,
            )
        ]
```

Дописать тест в `bot/tests/test_tools.py`:

```python
def test_toolbox_exposes_all_tools() -> None:
    box, _ = _toolbox()
    assert len(box.tools) == 10
```

- [ ] **Step 6: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_tools.py -v`
Expected: PASS — семь тестов.

- [ ] **Step 7: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/agent/ bot/tests/test_tools.py
git commit -m "feat(bot): добавить инструменты записи и чтения"
```

---

## Task 10: Системный промпт и кэшируемый префикс

**Files:**
- Create: `bot/src/anfinances_bot/agent/prompt.py`
- Create: `bot/tests/test_prompt.py`

**Interfaces:**
- Consumes: `AccountRead`, `CategoryRead`, `build_category_paths`.
- Produces: `SYSTEM_PROMPT: str`; `build_system_blocks(accounts, categories,
  timezone_name) -> list[dict]` — список блоков для параметра `system`
  запроса, где последний блок помечен `cache_control`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_prompt.py`:

```python
"""Сборка системного промпта и точки кэширования."""

from anfinances_bot.agent.prompt import (
    SYSTEM_PROMPT,
    build_system_blocks,
)
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead

ACCOUNTS = [
    AccountRead(id="a-1", name="Альфа", currency_code="RUB"),
    AccountRead(id="a-3", name="Наличные сумы", currency_code="UZS"),
]
CATEGORIES = [
    CategoryRead(id="c-1", name="Еда", kind="expense"),
    CategoryRead(
        id="c-2", name="Кофейни", kind="expense", parent_id="c-1"
    ),
]


def test_last_block_is_cached() -> None:
    blocks = build_system_blocks(
        ACCOUNTS, CATEGORIES, "Europe/Moscow"
    )
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in b for b in blocks[:-1])


def test_accounts_and_paths_present() -> None:
    blocks = build_system_blocks(
        ACCOUNTS, CATEGORIES, "Europe/Moscow"
    )
    text = "\n".join(b["text"] for b in blocks)
    assert "Альфа (RUB)" in text
    assert "Наличные сумы (UZS)" in text
    assert "Еда → Кофейни" in text


def test_timezone_present() -> None:
    blocks = build_system_blocks(
        ACCOUNTS, CATEGORIES, "Asia/Tashkent"
    )
    text = "\n".join(b["text"] for b in blocks)
    assert "Asia/Tashkent" in text


def test_prompt_states_transfer_rule() -> None:
    """Решение Р-9 должно быть в промпте дословно по смыслу."""
    assert "обе" in SYSTEM_PROMPT.casefold()
    assert "курс" in SYSTEM_PROMPT.casefold()


def test_no_timestamp_in_cached_prefix() -> None:
    """Волатильное в кэшируемом префиксе обнуляло бы кэш."""
    first = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    second = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    assert first == second
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.agent.prompt'`.

- [ ] **Step 3: Реализовать промпт**

Создать `bot/src/anfinances_bot/agent/prompt.py`:

```python
"""Системный промпт и кэшируемый префикс.

В префикс идёт только стабильное: инструкция, счета, дерево
категорий. Ничего волатильного — время, идентификаторы запроса,
текущая фраза — сюда попадать не должно, иначе кэш обнуляется на
каждом обращении.
"""

from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead
from anfinances_bot.resolve.categories import build_category_paths

__all__ = ["SYSTEM_PROMPT", "build_system_blocks"]

SYSTEM_PROMPT = """\
Ты — финансовый помощник в личном телеграм-боте. Пользователь \
наговаривает или пишет траты, ты записываешь их в anfinances \
инструментами и отвечаешь на вопросы по данным.

Как записывать:
- Сумма всегда положительная — знак проставит сервер по типу операции.
- Категорию выбирай листом дерева, когда лист подходит, и родителем, \
когда конкретнее сказать нечего. Используй только пути из списка ниже.
- Если формулировка незнакомая, посмотри инструментом прошлые \
операции: повтори собственную классификацию пользователя, а не \
общепринятую.
- Дату «вчера», «в пятницу» переводи в YYYY-MM-DD по таймзоне ниже.

Когда переспрашивать (и только тогда):
- Перевод между счетами в разных валютах без второй суммы. Тебе нужны \
обе фактические суммы: сколько ушло и сколько пришло. Досчитывать \
вторую по рыночному курсу запрещено — именно пара реальных сумм \
фиксирует настоящий курс пользователя.
- Счёт неоднозначен и инструмент вернул просьбу уточнить.
- Ты разрываешься между двумя категориями.
- Сумма или тип операции неоднозначны.

Отдельно: если операция задним числом и валюта не рублёвая — \
предупреди, что курс взят текущий, история курсов не хранится.

Отвечай коротко и по делу. Числа бери из инструментов, а не из \
общих соображений. Не выдумывай суммы и остатки.\
"""


def build_system_blocks(
    accounts: list[AccountRead],
    categories: list[CategoryRead],
    timezone_name: str,
) -> list[dict[str, object]]:
    """Собрать блоки system; последний помечен для кэширования."""
    account_lines = "\n".join(
        f"- {a.name} ({a.currency_code})" for a in accounts
    )
    expense = build_category_paths(categories, kind="expense")
    income = build_category_paths(categories, kind="income")
    expense_lines = "\n".join(f"- {p.path}" for p in expense)
    income_lines = "\n".join(f"- {p.path}" for p in income)

    context = (
        f"Таймзона пользователя: {timezone_name}\n\n"
        f"Счета:\n{account_lines}\n\n"
        f"Категории расходов:\n{expense_lines}\n\n"
        f"Категории доходов:\n{income_lines}"
    )

    return [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": context,
            "cache_control": {"type": "ephemeral"},
        },
    ]
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_prompt.py -v`
Expected: PASS — пять тестов.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/agent/prompt.py bot/tests/test_prompt.py
git commit -m "feat(bot): собрать системный промпт с кэшируемым префиксом"
```

---

## Task 11: Агентный цикл

**Files:**
- Create: `bot/src/anfinances_bot/agent/runner.py`
- Create: `bot/tests/test_runner.py`

**Interfaces:**
- Consumes: `ToolBox`, `build_system_blocks`.
- Produces: `AgentRunner(anthropic_client, toolbox)` с методом
  `run(text, accounts, categories, timezone_name) -> AgentReply`, где
  `AgentReply` — датакласс `(text: str, created_transaction_id: str | None,
  pending_accounts: list[AccountRead])`.
- Исключение `AgentUnavailable` — модель недоступна.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_runner.py`:

```python
"""Агентный цикл: параметры запроса и обработка отказов."""

from typing import Any

import pytest

from anfinances_bot.agent.runner import AgentRunner, AgentUnavailable


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]
        self.stop_reason = "end_turn"


class _FakeRunner:
    def __init__(self, message: _Message) -> None:
        self._message = message

    def __aiter__(self) -> "_FakeRunner":
        self._done = False
        return self

    async def __anext__(self) -> _Message:
        if self._done:
            raise StopAsyncIteration
        self._done = True
        return self._message


class _FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def tool_runner(self, **kwargs: Any) -> _FakeRunner:
        self.kwargs = kwargs
        return _FakeRunner(_Message("Записала: Еда → Кофейни"))


class _FakeBeta:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


class _FakeAnthropic:
    def __init__(self) -> None:
        self.beta = _FakeBeta()


class _FailingAnthropic:
    class _Messages:
        def tool_runner(self, **kwargs: Any) -> Any:
            raise RuntimeError("модель недоступна")

    class _Beta:
        def __init__(self) -> None:
            self.messages = _FailingAnthropic._Messages()

    def __init__(self) -> None:
        self.beta = _FailingAnthropic._Beta()


class _FakeToolBox:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self.last_created_id: str | None = "tx-1"
        self.pending_accounts: list[Any] = []


async def test_uses_opus_with_adaptive_thinking() -> None:
    anthropic = _FakeAnthropic()
    runner = AgentRunner(anthropic, _FakeToolBox())
    await runner.run("кофе 300", [], [], "Europe/Moscow")

    kwargs = anthropic.beta.messages.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "medium"}


async def test_returns_text_and_created_id() -> None:
    runner = AgentRunner(_FakeAnthropic(), _FakeToolBox())
    reply = await runner.run("кофе 300", [], [], "Europe/Moscow")
    assert "Кофейни" in reply.text
    assert reply.created_transaction_id == "tx-1"


async def test_model_failure_raises_agent_unavailable() -> None:
    runner = AgentRunner(_FailingAnthropic(), _FakeToolBox())
    with pytest.raises(AgentUnavailable):
        await runner.run("кофе 300", [], [], "Europe/Moscow")


async def test_system_blocks_are_passed() -> None:
    anthropic = _FakeAnthropic()
    runner = AgentRunner(anthropic, _FakeToolBox())
    await runner.run("кофе 300", [], [], "Asia/Tashkent")
    system = anthropic.beta.messages.kwargs["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.agent.runner'`.

- [ ] **Step 3: Реализовать цикл**

Создать `bot/src/anfinances_bot/agent/runner.py`:

```python
"""Агентный цикл поверх tool_runner.

Один агент с инструментами вместо режимов: он сам решает, что
вызвать. Фраза «потратила 300 на кофе, а сколько осталось»
обрабатывается за один заход — запись, чтение, связный ответ.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from anfinances_bot.agent.prompt import build_system_blocks
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead

logger = logging.getLogger("anfinances_bot.agent")

__all__ = ["AgentReply", "AgentRunner", "AgentUnavailable"]

MODEL = "claude-opus-5"
MAX_TOKENS = 8000


class AgentUnavailable(RuntimeError):
    """Модель недоступна или ответила ошибкой."""


@dataclass
class AgentReply:
    text: str
    created_transaction_id: str | None = None
    pending_accounts: list[AccountRead] = field(default_factory=list)


class _ToolBox(Protocol):
    tools: list[Any]
    last_created_id: str | None
    pending_accounts: list[AccountRead]


class AgentRunner:
    def __init__(self, anthropic: Any, toolbox: _ToolBox) -> None:
        self._anthropic = anthropic
        self._toolbox = toolbox

    async def run(
        self,
        text: str,
        accounts: list[AccountRead],
        categories: list[CategoryRead],
        timezone_name: str,
    ) -> AgentReply:
        self._toolbox.last_created_id = None
        self._toolbox.pending_accounts = []

        system = build_system_blocks(
            accounts, categories, timezone_name
        )
        try:
            runner = self._anthropic.beta.messages.tool_runner(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=system,
                tools=self._toolbox.tools,
                messages=[{"role": "user", "content": text}],
            )
            parts: list[str] = []
            async for message in runner:
                for block in message.content:
                    if getattr(block, "type", None) == "text":
                        parts.append(block.text)
        except Exception as exc:
            logger.error("Agent run failed", exc_info=True)
            raise AgentUnavailable(str(exc)) from exc

        return AgentReply(
            text="\n".join(p for p in parts if p).strip(),
            created_transaction_id=self._toolbox.last_created_id,
            pending_accounts=list(self._toolbox.pending_accounts),
        )
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_runner.py -v`
Expected: PASS — четыре теста.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/agent/runner.py bot/tests/test_runner.py
git commit -m "feat(bot): подключить агентный цикл с инструментами"
```

---

## Task 12: Карточка операции и кнопки

**Files:**
- Create: `bot/src/anfinances_bot/telegram/keyboards.py`
- Create: `bot/tests/test_keyboards.py`

**Interfaces:**
- Consumes: `AccountRead`.
- Produces: `transaction_card(transaction_id) -> InlineKeyboardMarkup`
  с кнопками `Исправить` (`callback_data="fix:<id>"`) и `Удалить`
  (`callback_data="del:<id>"`); `account_choice(accounts) ->
  InlineKeyboardMarkup` с кнопками `acc:<id>`;
  `parse_callback(data) -> tuple[str, str]`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_keyboards.py`:

```python
"""Клавиатуры: карточка операции и выбор счёта."""

import pytest

from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.telegram.keyboards import (
    account_choice,
    parse_callback,
    transaction_card,
)


def test_card_has_fix_and_delete() -> None:
    markup = transaction_card("tx-1")
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["fix:tx-1", "del:tx-1"]


def test_account_choice_lists_all() -> None:
    accounts = [
        AccountRead(id="a-1", name="Альфа", currency_code="RUB"),
        AccountRead(id="a-2", name="Сбер", currency_code="RUB"),
    ]
    markup = account_choice(accounts)
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["acc:a-1", "acc:a-2"]


def test_parse_callback_splits_action_and_id() -> None:
    assert parse_callback("fix:tx-1") == ("fix", "tx-1")
    assert parse_callback("acc:a-9") == ("acc", "a-9")


def test_parse_callback_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_callback("мусор")
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_keyboards.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать клавиатуры**

Создать `bot/src/anfinances_bot/telegram/keyboards.py`:

```python
"""Инлайн-клавиатуры бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anfinances_bot.anfinances.schemas import AccountRead

__all__ = ["account_choice", "parse_callback", "transaction_card"]


def transaction_card(transaction_id: str) -> InlineKeyboardMarkup:
    """Кнопки под карточкой созданной операции."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Исправить",
                    callback_data=f"fix:{transaction_id}",
                ),
                InlineKeyboardButton(
                    text="Удалить",
                    callback_data=f"del:{transaction_id}",
                ),
            ]
        ]
    )


def account_choice(
    accounts: list[AccountRead],
) -> InlineKeyboardMarkup:
    """Ряд кнопок со счетами — шаг 5 разрешения счёта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=account.name,
                    callback_data=f"acc:{account.id}",
                )
            ]
            for account in accounts
        ]
    )


def parse_callback(data: str) -> tuple[str, str]:
    """Разобрать ``действие:идентификатор``."""
    action, separator, value = data.partition(":")
    if not separator or not value:
        raise ValueError(f"Неразбираемый callback_data: {data!r}")
    return action, value
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_keyboards.py -v`
Expected: PASS — четыре теста.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/telegram/keyboards.py bot/tests/test_keyboards.py
git commit -m "feat(bot): добавить карточку операции и выбор счёта"
```

---

## Task 13: Распознавание голосовых

**Files:**
- Create: `bot/src/anfinances_bot/speech.py`
- Create: `bot/tests/test_speech.py`

**Interfaces:**
- Consumes: `BotSettings.openai_api_key`, `BotSettings.speech_model`.
- Produces: `transcribe(openai_client, audio_path, model) -> str`;
  исключение `SpeechUnavailable`. Функция **всегда** удаляет файл,
  включая ветку с ошибкой.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_speech.py`:

```python
"""Распознавание речи: файл удаляется всегда."""

from pathlib import Path
from typing import Any

import pytest

from anfinances_bot.speech import SpeechUnavailable, transcribe


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


class _Transcriptions:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> _Result:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return _Result("потратила триста рублей на кофе")


class _Audio:
    def __init__(self, error: Exception | None = None) -> None:
        self.transcriptions = _Transcriptions(error)


class _FakeOpenAI:
    def __init__(self, error: Exception | None = None) -> None:
        self.audio = _Audio(error)


def _audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "voice.ogg"
    path.write_bytes(b"fake-ogg")
    return path


async def test_returns_text_and_removes_file(tmp_path: Path) -> None:
    path = _audio_file(tmp_path)
    text = await transcribe(_FakeOpenAI(), path, "whisper-1")
    assert "кофе" in text
    assert not path.exists()


async def test_removes_file_on_failure(tmp_path: Path) -> None:
    path = _audio_file(tmp_path)
    client = _FakeOpenAI(RuntimeError("недоступно"))
    with pytest.raises(SpeechUnavailable):
        await transcribe(client, path, "whisper-1")
    assert not path.exists()


async def test_asks_russian(tmp_path: Path) -> None:
    path = _audio_file(tmp_path)
    client = _FakeOpenAI()
    await transcribe(client, path, "whisper-1")
    assert client.audio.transcriptions.kwargs["language"] == "ru"


async def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SpeechUnavailable):
        await transcribe(
            _FakeOpenAI(), tmp_path / "нет.ogg", "whisper-1"
        )
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_speech.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.speech'`.

- [ ] **Step 3: Реализовать распознавание**

Создать `bot/src/anfinances_bot/speech.py`:

```python
"""Распознавание голосовых через OpenAI Whisper.

Аудио уходит на распознавание, возвращается текст, файл удаляется
немедленно — и в успешной ветке, и в ветке с ошибкой. На сервере
голосовых не остаётся.
"""

import contextlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("anfinances_bot.speech")

__all__ = ["SpeechUnavailable", "transcribe"]


class SpeechUnavailable(RuntimeError):
    """Не удалось расшифровать голосовое."""


async def transcribe(
    openai_client: Any, audio_path: Path, model: str
) -> str:
    """Расшифровать файл и удалить его, что бы ни случилось."""
    try:
        if not audio_path.exists():
            raise SpeechUnavailable(f"Нет файла {audio_path}")
        try:
            with audio_path.open("rb") as handle:
                result = (
                    await openai_client.audio.transcriptions.create(
                        model=model,
                        file=handle,
                        language="ru",
                    )
                )
        except SpeechUnavailable:
            raise
        except Exception as exc:
            logger.warning("Transcription failed", exc_info=True)
            raise SpeechUnavailable(str(exc)) from exc
        return str(result.text)
    finally:
        with contextlib.suppress(OSError):
            audio_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_speech.py -v`
Expected: PASS — четыре теста.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/speech.py bot/tests/test_speech.py
git commit -m "feat(bot): распознавать голосовые и удалять файлы"
```

---

## Task 14: Проактивные сценарии

**Files:**
- Create: `bot/src/anfinances_bot/proactive.py`
- Create: `bot/tests/test_proactive.py`

**Interfaces:**
- Consumes: `BotSettings.bot_quiet_hours`, `BotSettings.bot_budget_meeting_day`.
- Produces: `is_quiet(now, quiet_hours) -> bool`;
  `should_remind(last_transaction_at, last_reminder_at, now) -> bool`;
  `should_hold_meeting(now, day, last_meeting_at) -> bool`;
  `should_warn_overspend(category_id, month, already_warned) -> bool`.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_proactive.py`:

```python
"""Тормоза проактивных сценариев."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from anfinances_bot.proactive import (
    is_quiet,
    should_hold_meeting,
    should_remind,
    should_warn_overspend,
)

MSK = ZoneInfo("Europe/Moscow")


def _at(hour: int, day: int = 10) -> datetime:
    return datetime(2026, 8, day, hour, 0, tzinfo=MSK)


def test_quiet_window_wraps_midnight() -> None:
    assert is_quiet(_at(23), (23, 9)) is True
    assert is_quiet(_at(3), (23, 9)) is True
    assert is_quiet(_at(8), (23, 9)) is True
    assert is_quiet(_at(9), (23, 9)) is False
    assert is_quiet(_at(15), (23, 9)) is False


def test_quiet_window_without_wrap() -> None:
    assert is_quiet(_at(2), (1, 5)) is True
    assert is_quiet(_at(6), (1, 5)) is False


def test_reminder_after_two_days_of_silence() -> None:
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(days=3),
            last_reminder_at=None,
            now=now,
        )
        is True
    )


def test_no_reminder_if_recent_transaction() -> None:
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(hours=5),
            last_reminder_at=None,
            now=now,
        )
        is False
    )


def test_no_repeat_reminder_within_two_days() -> None:
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(days=5),
            last_reminder_at=now - timedelta(hours=6),
            now=now,
        )
        is False
    )


def test_meeting_on_configured_day_once() -> None:
    now = _at(12, day=1)
    assert should_hold_meeting(now, day=1, last_meeting_at=None) is True
    assert (
        should_hold_meeting(now, day=1, last_meeting_at=now)
        is False
    )


def test_no_meeting_on_other_days() -> None:
    assert (
        should_hold_meeting(_at(12, day=2), day=1, last_meeting_at=None)
        is False
    )


def test_meeting_next_month_allowed() -> None:
    previous = datetime(2026, 7, 1, 12, tzinfo=MSK)
    now = datetime(2026, 8, 1, 12, tzinfo=MSK)
    assert (
        should_hold_meeting(now, day=1, last_meeting_at=previous)
        is True
    )


def test_overspend_warned_once_per_category_per_month() -> None:
    warned: set[tuple[str, str]] = set()
    assert should_warn_overspend("c-1", "2026-08", warned) is True
    warned.add(("c-1", "2026-08"))
    assert should_warn_overspend("c-1", "2026-08", warned) is False
    assert should_warn_overspend("c-1", "2026-09", warned) is True
    assert should_warn_overspend("c-2", "2026-08", warned) is True
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_proactive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.proactive'`.

- [ ] **Step 3: Реализовать правила**

Создать `bot/src/anfinances_bot/proactive.py`:

```python
"""Правила проактивных сообщений.

Бот пишет первым в трёх случаях, и у каждого свой тормоз, иначе он
превращается в спам. Здесь только решения «пора или нет» — сама
отправка живёт в обработчиках.
"""

from datetime import datetime, timedelta

__all__ = [
    "is_quiet",
    "should_hold_meeting",
    "should_remind",
    "should_warn_overspend",
]

REMINDER_SILENCE = timedelta(days=2)


def is_quiet(now: datetime, quiet_hours: tuple[int, int]) -> bool:
    """Попадает ли момент в часы тишины (окно может идти через полночь)."""
    start, end = quiet_hours
    hour = now.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def should_remind(
    last_transaction_at: datetime | None,
    last_reminder_at: datetime | None,
    now: datetime,
) -> bool:
    """Напомнить, если операций не было двое суток и мы молчали."""
    if last_reminder_at is not None:
        if now - last_reminder_at < REMINDER_SILENCE:
            return False
    if last_transaction_at is None:
        return True
    return now - last_transaction_at >= REMINDER_SILENCE


def should_hold_meeting(
    now: datetime, day: int, last_meeting_at: datetime | None
) -> bool:
    """Бюджетное совещание — раз в месяц, в назначенный день."""
    if now.day != day:
        return False
    if last_meeting_at is None:
        return True
    return (last_meeting_at.year, last_meeting_at.month) != (
        now.year,
        now.month,
    )


def should_warn_overspend(
    category_id: str,
    month: str,
    already_warned: set[tuple[str, str]],
) -> bool:
    """Не чаще одного предупреждения на категорию за месяц."""
    return (category_id, month) not in already_warned
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_proactive.py -v`
Expected: PASS — девять тестов.

- [ ] **Step 5: Прогнать полный набор проверок и закоммитить**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`

```bash
git add bot/src/anfinances_bot/proactive.py bot/tests/test_proactive.py
git commit -m "feat(bot): добавить правила проактивных сообщений"
```

---

## Task 15: Обработчики, точка входа и деплой

Сборка всего вместе плюс контейнер и выкладка.

**Files:**
- Create: `bot/src/anfinances_bot/telegram/handlers.py`
- Create: `bot/src/anfinances_bot/main.py`
- Create: `bot/Dockerfile`
- Modify: `docker-compose.deploy.yml`
- Modify: `.github/workflows/deploy.yml`
- Create: `bot/tests/test_handlers.py`

**Interfaces:**
- Consumes: всё из задач 4–14.
- Produces: `build_dispatcher(deps) -> Dispatcher`; `async def main() -> None`;
  `AppDeps` — датакласс с полями `client`, `anthropic`, `openai`, `toolbox`,
  `runner`, `settings`, `profile`.
- Обработчик текста отвечает карточкой при созданной операции, кнопками счетов
  при `pending_accounts`, текстом в остальных случаях.

- [ ] **Step 1: Написать падающий тест**

Создать `bot/tests/test_handlers.py`:

```python
"""Обработчик текста: карточка, кнопки, отказы."""

from dataclasses import dataclass, field
from typing import Any

from anfinances_bot.agent.runner import AgentReply, AgentUnavailable
from anfinances_bot.anfinances.client import AnfinancesUnavailableError
from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.telegram.handlers import handle_user_text


@dataclass
class _Sent:
    text: str
    markup: Any = None


@dataclass
class _Message:
    text: str
    sent: list[_Sent] = field(default_factory=list)

    async def answer(
        self, text: str, reply_markup: Any = None
    ) -> None:
        self.sent.append(_Sent(text, reply_markup))


class _Deps:
    def __init__(self, reply: Any) -> None:
        self._reply = reply

    async def resolve(self, text: str) -> AgentReply:
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


async def test_created_transaction_gets_card() -> None:
    message = _Message("кофе 300")
    deps = _Deps(
        AgentReply(
            text="Записала: Еда → Кофейни — 300 ₽",
            created_transaction_id="tx-1",
        )
    )
    await handle_user_text(message, deps)
    assert "Кофейни" in message.sent[0].text
    assert message.sent[0].markup is not None


async def test_pending_accounts_get_buttons() -> None:
    message = _Message("потратила 20 евро")
    deps = _Deps(
        AgentReply(
            text="С какого счёта?",
            pending_accounts=[
                AccountRead(id="e-1", name="EUR A", currency_code="EUR")
            ],
        )
    )
    await handle_user_text(message, deps)
    assert message.sent[0].markup is not None


async def test_plain_answer_has_no_markup() -> None:
    message = _Message("сколько осталось")
    deps = _Deps(AgentReply(text="Всего 15 000 ₽"))
    await handle_user_text(message, deps)
    assert message.sent[0].markup is None


async def test_site_down_is_reported_honestly() -> None:
    message = _Message("кофе 300")
    deps = _Deps(AnfinancesUnavailableError("нет сети"))
    await handle_user_text(message, deps)
    assert "не смогла записать" in message.sent[0].text.casefold()


async def test_model_down_suggests_web() -> None:
    message = _Message("кофе 300")
    deps = _Deps(AgentUnavailable("недоступна"))
    await handle_user_text(message, deps)
    assert "через сайт" in message.sent[0].text.casefold()
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd bot && uv run pytest tests/test_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'anfinances_bot.telegram.handlers'`.

- [ ] **Step 3: Реализовать обработчик**

Создать `bot/src/anfinances_bot/telegram/handlers.py`:

```python
"""Обработчики сообщений.

Ни один сбой не должен приводить к тихой потере операции: если
записать не удалось, бот говорит об этом прямо, а не делает вид,
что всё прошло.
"""

import logging
from typing import Any, Protocol

from anfinances_bot.agent.runner import AgentReply, AgentUnavailable
from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.telegram.keyboards import (
    account_choice,
    transaction_card,
)

logger = logging.getLogger("anfinances_bot.handlers")

__all__ = ["handle_user_text"]

SITE_DOWN = (
    "Не смогла записать: anfinances сейчас недоступен. "
    "Повтори через пару минут — я ничего не потеряла и не записала."
)
MODEL_DOWN = (
    "Не смогла разобрать фразу: модель недоступна. "
    "Запиши, пожалуйста, через сайт."
)


class _Deps(Protocol):
    async def resolve(self, text: str) -> AgentReply: ...


async def handle_user_text(message: Any, deps: _Deps) -> None:
    try:
        reply = await deps.resolve(message.text)
    except AnfinancesUnavailableError:
        logger.warning("anfinances недоступен", exc_info=True)
        await message.answer(SITE_DOWN)
        return
    except AgentUnavailable:
        logger.warning("модель недоступна", exc_info=True)
        await message.answer(MODEL_DOWN)
        return
    except AnfinancesError as exc:
        await message.answer(f"Не получилось: {exc}")
        return

    if reply.created_transaction_id is not None:
        await message.answer(
            reply.text,
            reply_markup=transaction_card(
                reply.created_transaction_id
            ),
        )
        return

    if reply.pending_accounts:
        await message.answer(
            reply.text or "С какого счёта?",
            reply_markup=account_choice(reply.pending_accounts),
        )
        return

    await message.answer(reply.text or "Не поняла, повтори иначе.")


async def handle_user_voice(
    message: Any, deps: _Deps, transcriber: Any
) -> None:
    """Расшифровать голосовое и обработать как текст."""
    try:
        text = await transcriber(message)
    except SpeechUnavailable:
        logger.warning("расшифровка не удалась", exc_info=True)
        await message.answer(SPEECH_DOWN)
        return

    await message.answer(f"Услышала: {text}")
    message.text = text
    await handle_user_text(message, deps)
```

Добавить импорт `from anfinances_bot.speech import SpeechUnavailable`,
константу и пополнить `__all__`:

```python
SPEECH_DOWN = (
    "Не смогла разобрать голосовое. Напиши, пожалуйста, текстом."
)

__all__ = ["handle_user_text", "handle_user_voice"]
```

Дописать тест в `bot/tests/test_handlers.py`:

```python
async def test_voice_failure_asks_for_text() -> None:
    from anfinances_bot.speech import SpeechUnavailable
    from anfinances_bot.telegram.handlers import handle_user_voice

    message = _Message("")

    async def _failing(_: Any) -> str:
        raise SpeechUnavailable("нет сети")

    await handle_user_voice(message, _Deps(AgentReply(text="")), _failing)
    assert "текстом" in message.sent[0].text.casefold()


async def test_voice_success_goes_through_text_path() -> None:
    from anfinances_bot.telegram.handlers import handle_user_voice

    message = _Message("")
    deps = _Deps(
        AgentReply(text="Записала", created_transaction_id="tx-1")
    )

    async def _ok(_: Any) -> str:
        return "кофе 300"

    await handle_user_voice(message, deps, _ok)
    assert "Услышала" in message.sent[0].text
    assert message.sent[1].markup is not None
```

- [ ] **Step 4: Прогнать тест и убедиться, что он проходит**

Run: `cd bot && uv run pytest tests/test_handlers.py -v`
Expected: PASS — семь тестов.

- [ ] **Step 5: Написать точку входа**

Создать `bot/src/anfinances_bot/main.py`:

```python
"""Точка входа бота."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from anfinances_bot.agent.runner import AgentRunner
from anfinances_bot.agent.tools import ToolBox
from anfinances_bot.anfinances.client import AnfinancesClient
from anfinances_bot.config import get_bot_settings
from anfinances_bot.telegram.access import AllowlistMiddleware
from anfinances_bot.telegram.handlers import handle_user_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("anfinances_bot")


class _Deps:
    def __init__(self, client, runner, profile) -> None:  # type: ignore[no-untyped-def]
        self._client = client
        self._runner = runner
        self._profile = profile

    async def resolve(self, text: str):  # type: ignore[no-untyped-def]
        accounts = await self._client.accounts()
        categories = await self._client.categories()
        return await self._runner.run(
            text, accounts, categories, self._profile.timezone
        )


async def main() -> None:
    settings = get_bot_settings()
    client = AnfinancesClient(settings)

    profile = await client.me()
    accounts = await client.accounts()

    # Счёт по умолчанию задан именем: UUID пережил бы не всякое
    # восстановление из бэкапа (ADR-020 перегенерирует идентификаторы).
    needle = settings.bot_default_account_name.casefold()
    if not any(a.name.casefold() == needle for a in accounts):
        available = ", ".join(a.name for a in accounts)
        logger.error(
            "Счёт по умолчанию «%s» не найден. Доступные: %s",
            settings.bot_default_account_name,
            available,
        )
        sys.exit(1)

    toolbox = ToolBox(client, settings.bot_default_account_name)
    runner = AgentRunner(
        AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        ),
        toolbox,
    )
    AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

    deps = _Deps(client, runner, profile)
    dispatcher = Dispatcher()
    dispatcher.message.middleware(
        AllowlistMiddleware(settings.telegram_allowed_user_ids)
    )
    dispatcher.callback_query.middleware(
        AllowlistMiddleware(settings.telegram_allowed_user_ids)
    )

    @dispatcher.message(F.text)
    async def _on_text(message):  # type: ignore[no-untyped-def]
        await handle_user_text(message, deps)

    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    speech = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value()
    )

    async def _download_and_transcribe(message) -> str:  # type: ignore[no-untyped-def]
        """Скачать голосовое во временный файл и расшифровать."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "voice.ogg"
            await bot.download(message.voice, destination=path)
            return await transcribe(speech, path, settings.speech_model)

    @dispatcher.message(F.voice)
    async def _on_voice(message):  # type: ignore[no-untyped-def]
        await handle_user_voice(
            message, deps, _download_and_transcribe
        )

    proactive = asyncio.create_task(
        run_proactive_loop(bot, deps, settings, profile.timezone)
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        proactive.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await proactive
        await client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Дополнить импорты `main.py`:

```python
import contextlib
import tempfile
from pathlib import Path

from anfinances_bot.proactive_loop import run_proactive_loop
from anfinances_bot.speech import transcribe
from anfinances_bot.telegram.handlers import (
    handle_user_text,
    handle_user_voice,
)
```

- [ ] **Step 5b: Написать цикл проактивных сообщений**

Создать `bot/src/anfinances_bot/proactive_loop.py`:

```python
"""Фоновый цикл проактивных сообщений.

Решения «пора или нет» живут в ``proactive``; здесь только отправка
и расписание. Первый адресат — единственный разрешённый Telegram-ID:
в личных чатах идентификатор пользователя совпадает с чатом, поэтому
хранить состояние не нужно.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from anfinances_bot.config import BotSettings
from anfinances_bot.proactive import (
    is_quiet,
    should_hold_meeting,
    should_remind,
)

logger = logging.getLogger("anfinances_bot.proactive")

__all__ = ["run_proactive_loop"]

TICK_SECONDS = 900.0

REMINDER = (
    "Пару дней ничего не записывали. Если траты были — наговорите "
    "их сейчас, пока помните."
)


async def run_proactive_loop(
    bot: Any,
    deps: Any,
    settings: BotSettings,
    timezone_name: str,
) -> None:
    """Раз в 15 минут проверять, не пора ли написать первым."""
    chat_id = next(iter(settings.telegram_allowed_user_ids))
    zone = ZoneInfo(timezone_name)
    last_reminder: datetime | None = None
    last_meeting: datetime | None = None

    while True:
        try:
            now = datetime.now(UTC).astimezone(zone)
            if not is_quiet(now, settings.bot_quiet_hours):
                if should_hold_meeting(
                    now, settings.bot_budget_meeting_day, last_meeting
                ):
                    reply = await deps.resolve(
                        "Проведи бюджетное совещание: итоги месяца, "
                        "что выбилось из плана, и предложи разложить "
                        "деньги на следующий месяц. Коротко."
                    )
                    await bot.send_message(chat_id, reply.text)
                    last_meeting = now
                elif should_remind(
                    await _last_transaction_at(deps),
                    last_reminder,
                    now,
                ):
                    await bot.send_message(chat_id, REMINDER)
                    last_reminder = now
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Проактивный цикл споткнулся", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)


async def _last_transaction_at(deps: Any) -> datetime | None:
    """Дата последней операции; None — если история пуста."""
    with contextlib.suppress(Exception):
        rows = await deps.client.request(
            "GET", "/transactions", params={"limit": 1}
        )
        if rows:
            return datetime.fromisoformat(rows[0]["date"])
    return None
```

Класс `_Deps` в `main.py` дополнить публичным атрибутом `client`, чтобы
`_last_transaction_at` мог им пользоваться:

```python
        self.client = client
```

- [ ] **Step 6: Написать Dockerfile**

Создать `bot/Dockerfile`:

```dockerfile
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
ENV PYTHONPATH=/app/src

CMD ["uv", "run", "--no-dev", "python", "-m", "anfinances_bot.main"]
```

- [ ] **Step 7: Добавить сервис в compose**

В `docker-compose.deploy.yml`, после сервиса `backend`, добавить:

```yaml
  bot:
    image: ${IMAGE_BOT}
    container_name: anfinances-bot
    restart: always
    depends_on:
      - backend
    environment:
      # Бот ходит в сайт по внутренней сети; наружу не публикуется.
      ANFINANCES_BASE_URL: http://backend:8000/api/v1
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN_FINANCE:?set it}
      TELEGRAM_ALLOWED_USER_IDS: ${TELEGRAM_ALLOWED_USER_IDS:?set it}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:?set it}
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set it}
      SINGLE_USER_EMAIL: ${SINGLE_USER_EMAIL:?set it}
      SINGLE_USER_PASSWORD: ${SINGLE_USER_PASSWORD:?set it}
      BOT_DEFAULT_ACCOUNTS: ${BOT_DEFAULT_ACCOUNTS:?set it}
      BOT_QUIET_HOURS: ${BOT_QUIET_HOURS:-23-9}
      BOT_BUDGET_MEETING_DAY: ${BOT_BUDGET_MEETING_DAY:-1}
```

- [ ] **Step 8: Дополнить деплой сборкой образа бота**

В `.github/workflows/deploy.yml` продублировать существующую job сборки
backend-образа для бота: контекст `bot`, тег образа `IMAGE_BOT`. В шаге,
который раскладывает `.env` на сервере по SSH, добавить строки для семи
новых переменных из таблицы выше, взяв значения из `secrets.*`.

- [ ] **Step 9: Проверить сборку образа локально**

Run: `docker build -t anfinances-bot:test bot/`
Expected: образ собирается без ошибок.

- [ ] **Step 10: Прогнать полный набор проверок**

Run: `cd bot && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
Expected: всё чисто, все тесты бота проходят.

- [ ] **Step 11: Коммит**

```bash
git add bot/ docker-compose.deploy.yml .github/workflows/deploy.yml
git commit -m "feat(bot): собрать обработчики, точку входа и деплой"
```

---

# Часть D. Независимая задача

## Task 16: Освободить порт 443, починить www

Не зависит от бота, делается в любой момент.

**Files:**
- Modify: `caddy/Caddyfile`
- Modify: `docker-compose.deploy.yml` (публикация портов caddy)
- Modify: `docs/deployment.md`

**Interfaces:** нет программных интерфейсов; изменения конфигурационные.

- [ ] **Step 1: Выяснить, кто держит порты на сервере**

На немецком сервере выполнить и сохранить вывод:

```bash
ss -tlnp 'sport = :80 or sport = :443'
```

Если в выводе есть `nginx` — он остаётся, и Caddy забирает только 443
(вариант A ниже). Если только `docker-proxy` — nginx не нужен, Caddy
забирает оба порта (вариант B).

- [ ] **Step 2: Обновить Caddyfile**

Заменить глобальный блок и добавить обработку `www`:

```caddyfile
{
	email {$ACME_EMAIL}
	http_port 80
}

anfinances.ru {
	encode zstd gzip
	header Strict-Transport-Security "max-age=31536000; includeSubDomains"
	reverse_proxy frontend:80
}

www.anfinances.ru {
	redir https://anfinances.ru{uri} permanent
}
```

Строка `https_port 8443` удаляется — Caddy возвращается на 443 по
умолчанию. Блок `tls { issuer acme { disable_tlsalpn_challenge } }`
удаляется вместе с ней: он был нужен, только пока 443 занимал VPN.
Личный email заменён на переменную `ACME_EMAIL` — это закрывает часть
пункта 11.4 роадмапа.

- [ ] **Step 3: Обновить публикацию портов**

В `docker-compose.deploy.yml` в сервисе `caddy` заменить блок `ports`.

Вариант A (nginx остаётся):

```yaml
    ports:
      - "127.0.0.1:8080:80"
      - "443:443"
```

Вариант B (nginx уходит):

```yaml
    ports:
      - "80:80"
      - "443:443"
```

Добавить в `environment` сервиса `caddy`:

```yaml
    environment:
      ACME_EMAIL: ${ACME_EMAIL:?set ACME_EMAIL in .env}
```

- [ ] **Step 4: Обновить DNS**

В панели DNS заменить A-запись `www.anfinances.ru` с `5.101.153.18`
на `188.68.49.26`.

- [ ] **Step 5: Задеплоить и проверить**

После деплоя выполнить и убедиться, что все три ответа успешны:

```bash
curl -sI https://anfinances.ru/ | head -1 && curl -sI https://www.anfinances.ru/ | head -1 && curl -s https://anfinances.ru/ | grep -oE 'assets/index-[^"]+\.js'
```

Expected: апекс отдаёт `HTTP/2 200`, `www` отдаёт `HTTP/2 301` с
редиректом на апекс, имя бандла выводится.

- [ ] **Step 6: Обновить документацию**

В `docs/deployment.md` убрать упоминания порта `8443` из команд проверки
и адресов, добавить `ACME_EMAIL` в список переменных окружения.

- [ ] **Step 7: Коммит**

```bash
git add caddy/Caddyfile docker-compose.deploy.yml docs/deployment.md
git commit -m "fix(deploy): вернуть сайт на 443 и починить www"
```

---

## Task 16b: Капитал должен учитывать кредиты

**Приоритет: до того, как владелец заведёт кредит в разделе «Кредиты».**

**Files:**
- Modify: `backend/app/domains/summary/repository.py`
- Modify: `backend/app/domains/summary/service.py`
- Modify: `backend/app/domains/summary/schemas.py`
- Create: `backend/tests/test_summary_capital_with_credits.py`

**Interfaces:**
- Consumes: `Credit.principal_balance`, `Credit.currency_code`,
  `Credit.is_archived`; `CurrencyService.rate_to_rub`.
- Produces: `SummaryRepository.active_credits(user_id) -> list[Credit]`;
  поле `total_credit_debt_rub: Decimal` в `DashboardResult`;
  `total_capital_rub` начинает вычитать долг.

**Почему.** `dashboard()` считает капитал только по счетам — кредиты в него не
входят (проверено: в `summary/service.py` нет ни одного обращения к домену
credits). Пока долг заведён счётом с отрицательным балансом, итог верен. Как
только владелец перенесёт кредит в раздел «Кредиты» и отправит счёт в архив,
капитал подскочит на сумму долга и покажет его богаче, чем он есть.

Разбивку «активы / обязательства / доступно» отдельными строками делает AF-007;
здесь задача уже — чтобы итоговое число не врало.

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_summary_capital_with_credits.py`:

```python
"""Капитал уменьшается на остаток долга по кредитам."""

import uuid
from decimal import Decimal
from typing import Any, cast

from app.domains.summary.service import SummaryService


class _Account:
    def __init__(
        self, name: str, currency: str, initial: Decimal
    ) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.currency_code = currency
        self.initial_balance = initial


class _Credit:
    def __init__(self, currency: str, balance: Decimal) -> None:
        self.currency_code = currency
        self.principal_balance = balance


class _Repo:
    def __init__(
        self, accounts: list[_Account], credits: list[_Credit]
    ) -> None:
        self._accounts = accounts
        self._credits = credits

    async def active_accounts(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._accounts)

    async def balances_by_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]:
        return {}

    async def active_credits(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._credits)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return {"RUB": Decimal(1), "UZS": Decimal("0.0072")}[code]


def _service(
    accounts: list[_Account], credits: list[_Credit]
) -> SummaryService:
    return SummaryService(
        cast(Any, _Repo(accounts, credits)), cast(Any, _Currencies())
    )


async def test_debt_reduces_capital() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("100000"))],
        [_Credit("RUB", Decimal("280650.24"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal("280650.24")
    assert result.total_capital_rub == Decimal("-180650.24")


async def test_no_credits_leaves_capital_unchanged() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("1000"))], []
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal(0)
    assert result.total_capital_rub == Decimal("1000")


async def test_foreign_currency_debt_is_converted() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("1000"))],
        [_Credit("UZS", Decimal("100000"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal("720.0000")
    assert result.total_capital_rub == Decimal("280.0000")
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/test_summary_capital_with_credits.py -v`
Expected: FAIL — у `DashboardResult` нет поля `total_credit_debt_rub`.

- [ ] **Step 3: Добавить чтение кредитов в репозиторий**

В `backend/app/domains/summary/repository.py` дополнить протокол
`SummaryRepository` методом и реализовать его в `SqlSummaryRepository`:

```python
    async def active_credits(self, user_id: uuid.UUID) -> list[Credit]:
        result = await self._session.execute(
            select(Credit).where(
                Credit.user_id == user_id,
                Credit.is_archived.is_(False),
            )
        )
        return list(result.scalars().all())
```

Импорт: `from app.domains.credits.models import Credit`.

- [ ] **Step 4: Добавить поле в схему**

В `backend/app/domains/summary/schemas.py`, в `DashboardResult`:

```python
    total_credit_debt_rub: Decimal
```

- [ ] **Step 5: Вычесть долг в сервисе**

В `dashboard()`, перед формированием `DashboardResult`:

```python
        # Кредиты — обязательства, а не счета. Без них итог показывал
        # бы владельца богаче, чем он есть, ровно на сумму долга.
        debt = Decimal(0)
        for credit in await self._repo.active_credits(user_id):
            try:
                rate = await self._currencies.rate_to_rub(
                    credit.currency_code
                )
            except NotFoundError:
                missing_rate_currencies.add(credit.currency_code)
            else:
                debt += credit.principal_balance * rate
```

и в возвращаемом объекте: `total_capital_rub=total - debt`,
`total_credit_debt_rub=debt`.

- [ ] **Step 6: Прогнать тест и убедиться, что он проходит**

Run: `cd backend && uv run pytest tests/test_summary_capital_with_credits.py -v`
Expected: PASS — три теста.

- [ ] **Step 7: Прогнать весь набор проверок**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q`
Expected: всё чисто. Существующие тесты дашборда могут потребовать
добавления нового поля — поправить их.

- [ ] **Step 8: Коммит**

```bash
git add backend/app/domains/summary/ backend/tests/test_summary_capital_with_credits.py
git commit -m "fix(summary): вычитать долг по кредитам из капитала"
```

---

## Task 17: Причесать внешний вид сайта

**Приоритет: самый низкий.** Делать в последнюю очередь, после всего
остального. Не блокирует ничего.

**Files:**
- Modify: `frontend/src/index.css:286-310` (блок `.nav`)
- Возможно: `frontend/src/app/Layout.tsx` (подписи пунктов меню)

**Interfaces:** нет программных интерфейсов; изменения стилевые.

**Симптом (со скриншота владельца).** Пункт «План-минимум» не помещается
в одну строку и переносится. Из-за этого вся полоса навигации становится
выше, а подписи остальных пунктов оказываются прижаты к верху своих
растянутых коробок — выравнивание выглядит съехавшим.

**Причина, уже найденная.** В `.nav` задано `display: flex` без
`align-items`, то есть действует значение по умолчанию `stretch`:
элементы растягиваются по высоте самого высокого. При этом у `.nav a`
нет `white-space: nowrap`, поэтому длинная подпись переносится и
задаёт эту высоту.

- [ ] **Step 1: Написать тест на вёрстку**

Добавить в `frontend/src/app/Layout.test.tsx` (создать файл, если его нет)
проверку, что все пункты меню отрисованы и подпись не разорвана:

```tsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { Layout } from "./Layout"

describe("Layout", () => {
  it("рисует пункт «План-минимум» одной подписью", () => {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    )
    expect(screen.getByText("План-минимум")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Прогнать тест и убедиться, что он падает или проходит**

Run: `cd frontend && pnpm exec vitest run src/app/Layout.test.tsx`
Expected: тест зелёный — он фиксирует наличие пункта; сам перенос строки
проверяется глазами, поэтому основная проверка визуальная (шаг 5).

- [ ] **Step 3: Починить стили**

В `frontend/src/index.css` заменить блоки `.nav` и `.nav a`:

```css
.nav {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav a {
  color: color-mix(in srgb, var(--on-app-bar) 80%, transparent);
  text-decoration: none;
  padding: 8px 16px;
  border-radius: var(--shape-full);
  font-weight: 500;
  white-space: nowrap;
  transition:
    background var(--spring),
    color var(--emphasized);
}
```

Добавлены две строки: `align-items: center` в контейнер и
`white-space: nowrap` в ссылку.

- [ ] **Step 4: Прогнать проверки фронтенда**

Run: `cd frontend && pnpm exec tsc -b && pnpm exec eslint . && pnpm exec vitest run && pnpm build`
Expected: всё чисто.

- [ ] **Step 5: Проверить глазами**

Открыть сайт на широком экране и на узком. Убедиться, что подписи
пунктов не переносятся, полоса навигации одной высоты, подписи по центру
по вертикали. На узком экране должно оставаться прежнее поведение —
мобильное меню, оно скрывает `.nav--desktop`.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/index.css frontend/src/app/Layout.test.tsx
git commit -m "fix(frontend): выровнять полосу навигации"
```

**Отдельно, если владелец захочет.** Общая ревизия внешнего вида
(«выглядит не очень») — это уже не одна правка, а самостоятельный
подпроект с разбором каждого экрана. Его стоит открывать отдельным
спеком, а не добавлять сюда.

---

# Порядок и зависимости

```
Task 1 ─┐
Task 2 ─┴─→ (фундамент готов)
Task 3 ────→ нужен боту для get_money_age

Task 4 → Task 5 → Task 6
              ├─→ Task 7 ─┐
              ├─→ Task 8 ─┤
              └─→ Task 9 ←┘ (нужны 5, 7, 8)
                      ↓
                  Task 10 → Task 11
                      ↓
        Task 12, Task 13, Task 14 (параллельно)
                      ↓
                  Task 15 (нужны 3, 9–14)

Task 16 — независима, в любой момент
```

Задачи 7, 8, 12, 13, 14 между собой не связаны и могут идти параллельно.
Задача 15 требует всех предыдущих из части C и задачу 3.
