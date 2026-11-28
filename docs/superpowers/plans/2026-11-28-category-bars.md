# Полосы вместо кольца в «Расходах по категориям» — план работ

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** заменить кольцевую диаграмму в карточке «Расходы по
категориям» на ранжированные горизонтальные полосы внутри таблицы, со
всеми категориями и итогом вверху карточки.

**Architecture:** правка одного компонента. Данные берутся из того же
хука `useByCategory`; `catRows` (уже отсортированный по убыванию
массив `{key, name, value}`) становится единственным источником для
карточки. Ширина полосы — процент от самой большой суммы, считается в
разметке инлайновым `style`. Кольцо, его палитра и обрезка до восьми
секторов удаляются.

**Tech Stack:** React 18, TypeScript, свой CSS, vitest + jsdom +
@testing-library/react. Новых зависимостей нет; Recharts остаётся в
проекте для других карточек.

**Spec:** `docs/superpowers/specs/2026-11-28-category-bars-design.md`

## Global Constraints

- Суммы показываются только через `formatMoney(value, "RUB")`;
  складываются только через `sumMoney` (`readonly Money[] -> number`).
  Дробная арифметика допустима лишь для ширины полосы в процентах.
- Ни одного литерального цвета в коде: только токены из
  `frontend/src/index.css`. Цвет полосы — `var(--expense)`.
- Карточка не заводит категориальную палитру: все полосы одного цвета.
- Разделитель пути категории — `CATEGORY_PATH_SEP` (`" → "`), имя
  берётся существующей функцией `catName`.
- Пустой месяц показывает ровно текст «За этот месяц расходов нет.»
- Полоса — оформление, не данные: несёт `aria-hidden="true"`.

## Review Focus

- **Все суммы нулевые** (например, месяц без трат, но с категориями в
  ответе): делителем станет 0 и ширина выйдет `NaN`. Ожидается ветка
  «За этот месяц расходов нет.» — её держит существующий фильтр
  `value > 0`, и это нужно закрепить тестом.
- **Отрицательная сумма по категории** (возврат больше трат):
  строка не показывается и в итог не входит, иначе доли дадут больше
  ста процентов.
- **Итог и строки расходятся:** итог должен считаться по показанным
  строкам, а не по всем элементам ответа, иначе сумма долей не 100%.
- **Больше восьми категорий:** показываются все, «Прочее» не
  появляется ни в каком виде.
- **Категория не нашлась в активном списке** (архивная): `catName`
  даёт «Категория», и две такие строки должны отрисоваться обе —
  ключ строки берётся из `category_id`, а не из имени.

---

### Task 1: Полосы, все категории, итог вверху

**Files:**
- Modify: `frontend/src/features/summary/DashboardPage.tsx`
  (данные — строки 158–189; разметка карточки — строки 523–605)
- Modify: `frontend/src/features/summary/summary.css`
- Test: `frontend/src/features/summary/CategoryBars.test.tsx` (создать)

Имя файла теста выбрано не `DashboardPage.test.tsx`: такой файл
создаёт ветка `claude/anfinances-sync-ab44e8` (PR #3), и два
одноимённых новых файла дали бы конфликт при слиянии.

**Interfaces:**
- Consumes: `catRows: {key: string, name: string, value: number}[]`
  — уже существует, отсортирован по убыванию, отфильтрован `value > 0`.
  `formatMoney`, `sumMoney` из `@/lib/money`.
- Produces: классы CSS `cat-list`, `cat-row`, `cat-bar`,
  `cat-bar-fill`, `cat-sum`, `cat-share`, `cat-head`, `cat-head-total`.
  Имена перечислены здесь, потому что тест цепляется к
  `.cat-bar-fill`. Становятся неиспользуемыми: `PIE_COLORS`,
  `PIE_LIMIT`, `pieHead`, `pieTail`, `pieData`, `.swatch`,
  `.swatch--rest`, `.swatch--empty`, `.chart-box--tall` — их убирает
  Task 2.

- [ ] **Step 1: Написать падающий тест**

Файл `frontend/src/features/summary/CategoryBars.test.tsx`. Моки
хуков — как в `DashboardPage.test.tsx` на ветке PR #3: все хуки
обзора отдают `{ data: undefined, isPending: true }`, кроме
`useByCategory` и `useCategories`.

```tsx
// @vitest-environment jsdom
// Хелпер: Category целиком, в тесте важны только id/name/parent_id.
function cat(id: string, name: string, parentId: string | null): Category {
  return {
    id, name, parent_id: parentId,
    kind: "expense", icon: null, sort_order: 0, is_archived: false,
    created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
  }
}

// Десять категорий: больше прежнего предела в восемь.
// 1000…100, итог 5500, самая большая — 18,2%, самая мелкая — 1,8%.
it("показывает все категории, а не восемь и «Прочее»", () => {
  expect(screen.getByText("Категория 10")).toBeInTheDocument()
  expect(screen.queryByText(/Прочее/)).not.toBeInTheDocument()
})

it("полоса самой большой категории — во всю дорожку, вдвое меньшей — вполовину", () => {
  const fills = document.querySelectorAll<HTMLElement>(".cat-bar-fill")
  expect(fills).toHaveLength(10)
  // Сравниваем числом, а не строкой: "60.0%" от toFixed(1) и
  // нормализация CSSOM — не то, что проверяет этот тест.
  expect(parseFloat(fills[0]!.style.width)).toBeCloseTo(100)
  expect(parseFloat(fills[4]!.style.width)).toBeCloseTo(60) // 600 из 1000
})

it("итог стоит вверху карточки, строки «Итого» внизу нет", () => {
  expect(screen.getByText(/За месяц/)).toBeInTheDocument()
  expect(screen.getByText(/5\s?500/)).toBeInTheDocument()
  expect(screen.queryByText("Итого")).not.toBeInTheDocument()
})

it("доля считается от показанных строк", () => {
  expect(screen.getByText("18.2%")).toBeInTheDocument()
  expect(screen.getByText("1.8%")).toBeInTheDocument()
})

it("отрицательная сумма не показывается и в итог не входит", () => {
  // к тем же десяти добавлена категория с «-50.00»
  expect(document.querySelectorAll(".cat-bar-fill")).toHaveLength(10)
  expect(screen.getByText(/5\s?500/)).toBeInTheDocument()
})

it("когда все суммы нулевые — текст про отсутствие расходов", () => {
  expect(screen.getByText("За этот месяц расходов нет.")).toBeInTheDocument()
  expect(document.querySelectorAll(".cat-bar-fill")).toHaveLength(0)
})

it("длинный путь категории выводится целиком", () => {
  expect(
    screen.getByText("Очень длинный родитель → И подкатегория подлиннее"),
  ).toBeInTheDocument()
})

it("две архивные категории дают две строки", () => {
  // два category_id, которых нет в списке категорий
  expect(screen.getAllByText("Категория")).toHaveLength(2)
})
```

- [ ] **Step 2: Прогнать тест и убедиться, что падает**

Run: `cd frontend && pnpm vitest run src/features/summary/CategoryBars.test.tsx`
Expected: FAIL — `.cat-bar-fill` не найден, «Итого» на месте.

- [ ] **Step 3: Переписать данные карточки в `DashboardPage.tsx`**

Удалить `PIE_LIMIT`, `pieHead`, `pieTail`, `pieData` (строки 172–185).
Заменить `catTotal` (строка 189) на сумму показанных строк:
`const catTotal = sumMoney(catRows.map((d) => String(d.value)))`.
Добавить `const catMax = catRows[0]?.value ?? 0` — массив уже
отсортирован по убыванию, искать максимум отдельно не нужно.

- [ ] **Step 4: Переписать разметку карточки в `DashboardPage.tsx`**

Условие показа — `catRows.length > 0` вместо `pieData.length > 0`;
ветка «расходов нет» — `catRows.length === 0`. Вместо
`<div className="chart-box chart-box--tall">` с `PieChart` — шапка с
итогом (`cat-head`: подпись «За месяц» и сумма в `cat-head-total`) и
таблица строк. В строке: имя, дорожка `cat-bar` с вложенной
`cat-bar-fill` (`aria-hidden`, `style={{ width: ... }}`), сумма,
доля. Ширина — `${((d.value / catMax) * 100).toFixed(1)}%`, при
`catMax === 0` строк нет вовсе. Доля — как сейчас,
`((d.value / catTotal) * 100).toFixed(1)`. Квадратики `swatch`,
строку «Итого» и `Tooltip` этой карточки удалить.

- [ ] **Step 5: Дописать стили в `summary.css`**

Полоса высотой 8 пикселей, дорожка на `var(--surface-container-high)`,
заливка `var(--expense)`, наружный конец скруглён (`border-radius: 0
4px 4px 0`), левый край прямой — все полосы начинаются от одной
вертикали. Итог в шапке — крупнее основного текста. На ширине до
560 пикселей полоса переносится под имя на всю строку.

- [ ] **Step 6: Прогнать тест и убедиться, что проходит**

Run: `cd frontend && pnpm vitest run src/features/summary/CategoryBars.test.tsx`
Expected: PASS, 8 тестов.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/features/summary/DashboardPage.tsx \
        frontend/src/features/summary/summary.css \
        frontend/src/features/summary/CategoryBars.test.tsx
git commit -m "feat(summary): полосы по категориям вместо кольца"
```

---

### Task 2: Убрать осиротевший код

**Files:**
- Modify: `frontend/src/features/summary/DashboardPage.tsx` (импорты,
  константа `PIE_COLORS` на строке 33)
- Modify: `frontend/src/features/summary/summary.css` (`.swatch`,
  `.swatch--rest`, `.swatch--empty`, `.chart-box--tall`)

**Interfaces:**
- Consumes: список имён из блока Interfaces задачи 1.
- Produces: ничего.

- [ ] **Step 1: Проверить каждое имя на оставшиеся вхождения**

Run: `cd frontend && grep -rn "PIE_COLORS\|chart-box--tall\|swatch" src`
Expected: вхождения только в тех местах, которые эта задача удаляет.
Имя, которое используется где-то ещё, остаётся — и это отмечается в
отчёте.

- [ ] **Step 2: Удалить неиспользуемое**

`PIE_COLORS` и ставшие лишними импорты `Pie`, `PieChart`, `Cell` из
`recharts` (`Tooltip`, `ResponsiveContainer`, `Bar`, `BarChart`,
`CartesianGrid`, `XAxis`, `YAxis` нужны другим карточкам — проверить
по факту). В `summary.css` — классы из списка выше вместе с их
комментариями.

- [ ] **Step 3: Линтер, типы, тесты, сборка**

Run: `cd frontend && pnpm lint && pnpm tsc --noEmit && pnpm vitest run && pnpm build`
Expected: всё без ошибок и предупреждений о неиспользуемых именах.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/features/summary/DashboardPage.tsx \
        frontend/src/features/summary/summary.css
git commit -m "refactor(summary): убрать палитру и стили кольца"
```
