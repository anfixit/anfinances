# Прихожая для получателей — план работ

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Невиданное имя получателя ждёт подтверждения владелицы, а в справочник попадают только магазины и сервисы.

**Architecture:** Новая таблица `payee_candidates` в домене получателей. `PayeeService.ensure()` заменяется на `remember()`, который возвращает подтверждённого получателя или `None` и копит кандидата. Операция в обоих случаях сохраняет имя в `payee_name_snapshot`. Подтверждение кандидата создаёт получателя (или приклеивает к существующему), перевешивает ранее записанные операции и засевает память категории.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 (в тестах SQLite), React 18 + TanStack Query, vitest, pytest, uv, pnpm.

**Spec:** `docs/superpowers/specs/2026-11-27-payees-waiting-room-design.md`

## Global Constraints

- Имена сравниваются свёрнутыми: `payee_key()` (casefold + схлопывание пробелов), свёртка **в Python, не в SQL** — в SQLite `lower()` не трогает кириллицу.
- `payee_name_snapshot` на операции заполняется всегда, когда имя известно; связь на получателя — `ondelete="SET NULL"`. Ломать нельзя: на этом держится и разовая чистка, и выгрузка.
- Деньги — `Decimal`, суммы в схемах через существующий тип `Money` (18,4).
- Ответы API завёрнуты в `ApiResponse[...]`, как все маршруты проекта.
- Статусы кандидата — ровно два: `pending`, `rejected`.
- Команды: бэкенд — `cd backend && uv run pytest -q`, линтеры `uv run ruff check . && uv run mypy app scripts`; фронтенд — `cd frontend && pnpm vitest run`.
- Миграция называется по образцу соседей: `20261127_1800_e31d0payeecand01_payee_candidates.py`, `down_revision = "e30d0session01"`.

## Review Focus

Пять случаев, которые документ подразумевает, но прямо не описывает. Тест на каждый добавлен в задачу, которой принадлежит код.

1. Имя из одних пробелов или пустое — кандидата заводить нельзя (задача 2).
2. Два написания одного имени в одной выписке («OZON.RU» и «Ozon.ru») — один кандидат с `times_seen = 2`, а не два (задача 2).
3. Подтверждение кандидата, когда получатель с таким именем уже успел появиться — 409, а не второй получатель с тем же `name_key` (задача 3).
4. Удаление получателя, у которого есть операции, — имя остаётся на операциях, кандидат уходит в `rejected`, следующая выписка его не воскрешает (задача 3).
5. Имя длиной в предельные 200 символов (`TransactionCreate.payee`) — кандидат пишется и читается без обрезки (задача 1).

## Файлы

| Файл | За что отвечает |
|---|---|
| `backend/app/domains/payees/models.py` | + модель `PayeeCandidate` |
| `backend/alembic/versions/20261127_1800_e31d0payeecand01_payee_candidates.py` | таблица `payee_candidates` |
| `backend/app/domains/payees/repository.py` | + чтение/запись кандидатов, перевешивание операций по свёрнутому имени |
| `backend/app/domains/payees/service.py` | `remember()` вместо `ensure()`, `accept_candidate()`, `reject_candidate()`, `unreject_candidate()` |
| `backend/app/domains/payees/schemas.py` | `PayeeCandidateRead`, `CandidateAccept` |
| `backend/app/domains/payees/routes.py` | маршруты очереди, удаление `/payees/new` |
| `backend/app/domains/transactions/service.py` | вызовы `remember()` вместо `ensure()` |
| `backend/app/domains/ai/policy.py` | закрыть ИИ разбор очереди и `POST /payees` |
| `backend/app/domains/export/*`, `import_/service.py` | кандидаты в пакете, версия 3 |
| `frontend/src/features/payees/{payeesApi.ts,hooks.ts,PayeesPage.tsx}` | очередь, отклонённые, «Не магазин» у существующих |
| `frontend/src/features/summary/…` + `payees/routes.py` | строка «не разобрано: N имён на X ₽» |
| `bot/src/anfinances_bot/agent/{prompt.py,tools.py}`, `mcp_server/catalog.py` | подсказка «payee только для организаций», тулза читает очередь |

---

### Task 1: таблица кандидатов

**Files:**
- Modify: `backend/app/domains/payees/models.py`
- Create: `backend/alembic/versions/20261127_1800_e31d0payeecand01_payee_candidates.py`
- Modify: `backend/app/domains/payees/repository.py`
- Test: `backend/tests/test_payee_candidates.py`

**Interfaces:**
- Consumes: `payee_key()` из `payees/service.py`.
- Produces: `PayeeCandidate(user_id, name, name_key, status, times_seen, first_seen_at, last_seen_at)`; `PayeeRepository.get_candidate(user_id, name_key) -> PayeeCandidate | None`, `add_candidate(candidate) -> PayeeCandidate`, `list_candidates(user_id, status) -> list[PayeeCandidate]`.

- [ ] **Шаг 1: Написать падающий тест**

```python
async def test_candidate_is_unique_by_folded_name(db_session): ...
# добавить кандидата «OZON.RU», затем искать get_candidate(user, payee_key("ozon.ru")) — находится он же
async def test_candidate_keeps_a_200_character_name(db_session): ...
# имя из 200 символов сохраняется и читается целиком (Review Focus 5)
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `cd backend && uv run pytest tests/test_payee_candidates.py -q`
Expected: FAIL, `PayeeCandidate` не существует.

- [ ] **Шаг 3: Модель `PayeeCandidate` в `payees/models.py`**

Уникальный индекс `uq_payee_candidate_user_name_key` по `(user_id, name_key)`, индекс по `user_id`. `name` — `String` без ограничения длины, как у `Payee`. `status` — `String`, значения `pending`/`rejected`, server_default `'pending'`. `times_seen` — `Integer`, server_default `'1'`. `first_seen_at`/`last_seen_at` — `DateTime(timezone=True)`.

- [ ] **Шаг 4: Миграция**

`alembic revision` с ревизией `e31d0payeecand01`, `down_revision = "e30d0session01"`, создание таблицы и обоих индексов, `downgrade` — `drop_table`.

- [ ] **Шаг 5: Методы репозитория**

`get_candidate`, `add_candidate`, `list_candidates` в `SqlPayeeRepository` и в протоколе `PayeeRepository`.

- [ ] **Шаг 6: Тесты зелёные**

Run: `cd backend && uv run pytest tests/test_payee_candidates.py -q` → PASS.
Run: `cd backend && uv run alembic upgrade head` на пустой базе → проходит.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/domains/payees backend/alembic/versions backend/tests/test_payee_candidates.py
git commit -m "feat(payees): таблица кандидатов"
```

---

### Task 2: имя больше не попадает в справочник само

**Files:**
- Modify: `backend/app/domains/payees/service.py`
- Modify: `backend/app/domains/transactions/service.py:193-237,255-275`
- Test: `backend/tests/test_payee_candidates.py`, `backend/tests/test_payees.py`

**Interfaces:**
- Produces: `PayeeService.remember(user_id: uuid.UUID, name: str) -> tuple[Payee | None, str]` — подтверждённый получатель или `None`, и очищенное имя для снимка. `ensure()` удаляется целиком, чтобы ни один вызов не остался на старом поведении.

- [ ] **Шаг 1: Написать падающие тесты**

```python
async def test_unknown_name_does_not_create_a_payee(...)
# после записи операции: payee_id is None, payee_name_snapshot == "Злата", в справочнике пусто, кандидат один
async def test_two_spellings_in_one_statement_make_one_candidate(...)
# «OZON.RU» и «Ozon.ru» → один кандидат, times_seen == 2 (Review Focus 2)
async def test_blank_payee_name_creates_nothing(...)
# payee="   " → ни получателя, ни кандидата, snapshot пустой (Review Focus 1)
async def test_confirmed_payee_still_resolves(...)
# у подтверждённого получателя операция по-прежнему получает payee_id и память категории
async def test_rejected_name_does_not_come_back(...)
# имя со статусом rejected: кандидат не создаётся заново и times_seen не растёт
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd backend && uv run pytest tests/test_payee_candidates.py tests/test_payees.py -q`

- [ ] **Шаг 3: Заменить `ensure()` на `remember()`**

Пустое или пробельное имя → `(None, "")` и никаких записей. Есть подтверждённый — `(payee, payee.name)`. Есть `rejected` — `(None, cleaned)`, кандидат не трогается. Иначе — завести или обновить кандидата (`times_seen += 1`, `last_seen_at`) и вернуть `(None, cleaned)`.

- [ ] **Шаг 4: Поправить вызовы в `transactions/service.py`**

Обе точки (создание и правка операции) берут из `remember()` пару и пишут `payee_id = payee.id if payee else None`, `payee_name_snapshot = name or None`. Память категории пишется только для подтверждённых — как сейчас.

- [ ] **Шаг 5: Тесты зелёные + линтеры**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run mypy app scripts`

- [ ] **Шаг 6: Коммит**

```bash
git commit -am "feat(payees): невиданное имя ждёт подтверждения"
```

---

### Task 3: разбор очереди

**Files:**
- Modify: `backend/app/domains/payees/{service,repository,schemas,routes}.py`
- Test: `backend/tests/test_payee_candidates.py`

**Interfaces:**
- Consumes: `remember()` из задачи 2, `PayeeRepository.list_candidates`.
- Produces:
  - `PayeeRepository.reassign_orphans(user_id, name_key, payee_id) -> tuple[int, uuid.UUID | None]` — число перевешенных операций и категория самой свежей из них (ею засевается память); перевешивает операции с пустым `payee_id`, чей `payee_name_snapshot` сворачивается в `name_key`. Свёртка в Python: выбрать операции пользователя с `payee_id IS NULL` и непустым снимком, отобрать совпадающие, обновить разом.
  - `PayeeService.accept_candidate(candidate_id, user_id, payee_id: uuid.UUID | None) -> Payee`
  - `PayeeService.reject_candidate(candidate_id, user_id) -> None`
  - `PayeeService.unreject_candidate(candidate_id, user_id) -> None`
  - `PayeeRepository.candidate_totals(user_id, name_keys) -> dict[str, Decimal]` — сумма трат по осиротевшим операциям каждого имени (свёртка снимков в Python, одним проходом на весь список).
  - Маршруты: `GET /payees/candidates?status=pending|rejected`, `POST /payees/candidates/{id}/accept` (тело `{"payee_id": null | "<uuid>"}`), `POST /payees/candidates/{id}/reject`, `POST /payees/candidates/{id}/unreject`. `GET /payees/new` удаляется вместе с `list_new_payees` и `NEW_PAYEE_WINDOW`.

- [ ] **Шаг 1: Написать падающие тесты**

```python
async def test_accept_moves_earlier_operations(...)
# три операции по «Аптека Вита» без получателя → accept → у всех трёх payee_id нового получателя
async def test_accept_seeds_the_category_hint(...)
# last_category_id равен категории самой свежей перевешенной операции
async def test_accept_into_an_existing_payee_creates_nothing(...)
# accept с payee_id существующего: операции ушли к нему, новых получателей нет
async def test_accept_is_refused_when_the_name_is_already_taken(...)
# получателя с тем же name_key создали вручную → 409 (Review Focus 3)
async def test_candidate_carries_the_total_of_its_orphan_operations(...)
# две операции по «Аптека Вита» на 300 и 200 → amount == 500, очередь отсортирована по убыванию
async def test_marketplace_candidate_gets_varied_categories(...)
async def test_reject_hides_the_name_and_unreject_returns_it(...)
async def test_deleting_a_payee_rejects_the_name(...)
# у получателя две операции → delete → имя на операциях осталось, кандидат rejected,
# повторная запись того же имени не создаёт ни получателя, ни pending-кандидата (Review Focus 4)
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd backend && uv run pytest tests/test_payee_candidates.py -q`

- [ ] **Шаг 3: Реализовать сервис и репозиторий**

`accept_candidate` без `payee_id`: проверить, что `name_key` свободен (иначе `AlreadyExistsError`), создать получателя с `varied_categories = is_marketplace(name)`, перевесить операции, засеять `last_category_id` категорией самой свежей перевешенной операции (для маркетплейса — не засевать), удалить кандидата. С `payee_id`: перевесить на указанного, кандидата удалить, память не трогать. `delete_payee` дополнительно заводит `rejected`-кандидата с именем удалённого.

- [ ] **Шаг 4: Маршруты и схемы**

`PayeeCandidateRead(id, name, times_seen, amount: Decimal, first_seen_at, last_seen_at, status)`, `CandidateAccept(payee_id: uuid.UUID | None = None)`. Ответы — в `ApiResponse`. `amount` считается на лету через `candidate_totals` и в таблице не хранится: имя разбирают один раз, а лишнее поле пришлось бы держать в согласии с операциями. Очередь отдаётся отсортированной по `amount` по убыванию — крупное разбирают первым.

- [ ] **Шаг 5: Тесты зелёные + линтеры**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run mypy app scripts`

- [ ] **Шаг 6: Коммит**

```bash
git commit -am "feat(payees): очередь разбора — подтвердить, отклонить, вернуть"
```

---

### Task 4: строка «не разобрано»

**Files:**
- Modify: `backend/app/domains/payees/{repository,schemas,routes}.py`
- Modify: `frontend/src/features/payees/{payeesApi.ts,hooks.ts}` (типы ответа), `frontend/src/features/summary/DashboardPage.tsx` (отчёт по получателям рисуется здесь, `useSpendingByPayee` на строке 111)
- Test: `backend/tests/test_payees.py`, `frontend/src/features/summary/DashboardPage.test.tsx`

**Interfaces:**
- Produces: в ответе `GET /payees/spending` появляются `unsorted_names: int` и `unsorted_amount: Decimal` — число неразобранных имён и сумма трат по ним за тот же период (операции с `payee_id IS NULL` и непустым снимком).

- [ ] **Шаг 1: Тест** — `test_spending_counts_unsorted_names_separately`: две операции по неподтверждённым именам не попадают в строки отчёта, но дают `unsorted_names == 2` и сумму.
- [ ] **Шаг 2: Убедиться, что падает.** Run: `cd backend && uv run pytest tests/test_payees.py -q`
- [ ] **Шаг 3: Считать в том же запросе периода, что и отчёт.**
- [ ] **Шаг 4: Тесты зелёные.** Run: `cd backend && uv run pytest -q`
- [ ] **Шаг 5: Тест и строка на дашборде** — под таблицей «кому уходят деньги» строка «не разобрано: N имён на X ₽» со ссылкой на `/payees`; при `unsorted_names == 0` строки нет. Run: `cd frontend && pnpm vitest run DashboardPage`
- [ ] **Шаг 6: Коммит** — `feat(payees): в отчёте видно, сколько не разобрано`

---

### Task 5: экран

**Files:**
- Modify: `frontend/src/features/payees/{payeesApi.ts,hooks.ts,PayeesPage.tsx,payees.css}`
- Modify: `frontend/src/features/transactions/TransactionSheet.tsx` (убрать `useNewPayees`)
- Test: `frontend/src/features/payees/PayeesPage.test.tsx`

**Interfaces:**
- Consumes: маршруты из задач 3 и 4.
- Produces: `listCandidates(status)`, `acceptCandidate(id, payeeId?)`, `rejectCandidate(id)`, `unrejectCandidate(id)` в `payeesApi.ts`; хуки `useCandidates`, `useAcceptCandidate`, `useRejectCandidate`, `useUnrejectCandidate`. `listNewPayees`/`useNewPayees` удаляются.

- [ ] **Шаг 1: Тест** — очередь из двух кандидатов: видно имя, число встреч и сумма; «В справочник» зовёт `acceptCandidate` с `payee_id: null`; «Не магазин» зовёт `rejectCandidate`; пустая очередь — блока нет.
- [ ] **Шаг 2: Убедиться, что падает.** Run: `cd frontend && pnpm vitest run PayeesPage`
- [ ] **Шаг 3: Блок очереди** вместо «Новые за месяц»: заголовок с числом имён, сортировка по сумме, в строке — выбор «это тот же, что…» со списком получателей.
- [ ] **Шаг 4: Свёрнутый список «Не магазины (N)»** с кнопкой «вернуть в очередь»; у существующих записей справочника — кнопка «Не магазин».
- [ ] **Шаг 5: Тесты зелёные.** Run: `cd frontend && pnpm vitest run`
- [ ] **Шаг 6: Коммит** — `feat(frontend): очередь разбора получателей`

---

### Task 6: бэкап и права ИИ

**Files:**
- Modify: `backend/app/domains/export/{schemas.py,service.py}`, `backend/app/domains/import_/service.py`
- Modify: `backend/app/domains/ai/policy.py`
- Test: `backend/tests/` — файлы выгрузки и прав (рядом с существующими)

**Interfaces:**
- Produces: `ExportBundle.payee_candidates: list[ExportPayeeCandidate] = []`, `BACKUP_VERSION = 3`.

- [ ] **Шаг 1: Тесты** — выгрузка и восстановление возвращают отклонённые имена; пакет версии 2 восстанавливается со пустым списком кандидатов; ИИ получает отказ на `POST /payees`, `accept`, `reject`, `unreject` и по-прежнему читает `GET /payees/candidates`.
- [ ] **Шаг 2: Убедиться, что падают.** Run: `cd backend && uv run pytest -q -k "export or policy"`
- [ ] **Шаг 3: Кандидаты в пакет,** версия 3, `_check_integrity` учитывает новый список. `restore_all` создаёт кандидатов напрямую — мимо прихожей, как и получателей.
- [ ] **Шаг 4: Правила в `policy.py`** рядом с правилом про `/merge/`, с коротким объяснением, как у соседей.
- [ ] **Шаг 5: Тесты зелёные.** Run: `cd backend && uv run pytest -q`
- [ ] **Шаг 6: Коммит** — `feat(payees): кандидаты в бэкапе, разбор закрыт для ИИ`

---

### Task 7: бот и MCP

**Files:**
- Modify: `bot/src/anfinances_bot/agent/prompt.py:106`, `bot/src/anfinances_bot/agent/tools.py:209,237,515`
- Modify: `bot/src/anfinances_bot/mcp_server/catalog.py:121`
- Test: `bot/tests/`

**Interfaces:**
- Consumes: `GET /payees/candidates`.
- Produces: тулза `list_payee_candidates` вместо `list_new_payees`.

- [ ] **Шаг 1: Тест** — тулза ходит в `/payees/candidates` и отдаёт имена с числом встреч.
- [ ] **Шаг 2: Убедиться, что падает.** Run: `cd bot && uv run --with tzdata pytest -q`
- [ ] **Шаг 3: Подсказка:** payee заполняется только для организаций; перевод человеку — payee пустой, имя в описание. Поправить во всех трёх местах, где это написано.
- [ ] **Шаг 4: Переименовать тулзу** в каталоге MCP и в наборе агента.
- [ ] **Шаг 5: Тесты зелёные.** Run: `cd bot && uv run --with tzdata pytest -q`
- [ ] **Шаг 6: Коммит** — `feat(bot): payee только для организаций`

---

## После всех задач

- [ ] `cd backend && uv run alembic upgrade head && uv run pytest -q`
- [ ] `cd frontend && pnpm vitest run && pnpm build`
- [ ] `cd bot && uv run --with tzdata pytest -q`
- [ ] Проверить руками на локальном стенде (`.claude/launch.json`, профиль `frontend-dev`): завести операцию с новым именем, разобрать очередь, вернуть отклонённое.
- [ ] Выкатка обычным порядком: пуш в main, прогон по хэшу коммита, миграция проходит до `up -d`.
