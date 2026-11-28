// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"
import { cleanup, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Category } from "@/features/categories/types"
import type { ByCategory } from "@/features/summary/types"

// Обзор тянет десяток хуков; здесь важны только расходы по категориям
// и справочник категорий — остальные отдают «ещё грузится».
const pending = { data: undefined, isPending: true }

vi.mock("@/features/budgets/hooks", () => ({ useBudgets: () => pending }))
vi.mock("@/features/transactions/hooks", () => ({
  useTransactions: () => pending,
}))
vi.mock("@/features/payees/hooks", () => ({
  useSpendingByPayee: () => pending,
}))

let byCategory: ByCategory
vi.mock("@/features/summary/hooks", () => ({
  useByCategory: () => ({ data: byCategory, isPending: false }),
  useCashflow: () => pending,
  useDailyAllowance: () => pending,
  useDashboard: () => pending,
  useMoneyAge: () => pending,
}))

let categories: Category[]
vi.mock("@/features/categories/hooks", () => ({
  useCategories: () => ({ data: categories, isPending: false }),
}))

import { DashboardPage } from "@/features/summary/DashboardPage"

function cat(
  id: string,
  name: string,
  parentId: string | null = null,
): Category {
  return {
    id,
    name,
    kind: "expense",
    parent_id: parentId,
    icon: null,
    sort_order: 0,
    is_archived: false,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  }
}

function renderPage() {
  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

// Имена категорий обзор печатает и в карточке «Перерасход по
// категориям»: без лимитов перерасходом считается любая трата. Все
// запросы здесь ограничены своей карточкой.
function card() {
  const heading = screen.getByRole("heading", {
    name: "Расходы по категориям",
  })
  const box = heading.closest(".card")
  if (box === null) {
    throw new Error("карточка «Расходы по категориям» не найдена")
  }
  return within(box as HTMLElement)
}

function fills(): HTMLElement[] {
  const heading = screen.getByRole("heading", {
    name: "Расходы по категориям",
  })
  const box = heading.closest(".card")
  return Array.from(
    box?.querySelectorAll<HTMLElement>(".cat-bar-fill") ?? [],
  )
}

// Десять категорий — больше прежнего предела в восемь секторов.
// Суммы 1000…100 шагом 100: итог 5500, самая крупная 18,2%,
// самая мелкая 1,8%.
const TEN = Array.from({ length: 10 }, (_, i) => ({
  id: `c${String(i + 1)}`,
  name: `Категория ${String(i + 1)}`,
  amount: `${String((10 - i) * 100)}.00`,
}))

beforeEach(() => {
  categories = TEN.map((c) => cat(c.id, c.name))
  byCategory = {
    month: "2026-11",
    items: TEN.map((c) => ({ category_id: c.id, amount_rub: c.amount })),
    total_rub: "5500.00",
  }
})

afterEach(cleanup)

describe("карточка «Расходы по категориям»", () => {
  it("показывает все категории, а не восемь и «Прочее»", () => {
    renderPage()

    expect(card().getByText("Категория 10")).toBeInTheDocument()
    expect(card().queryByText(/Прочее/)).not.toBeInTheDocument()
  })

  it("полоса крупнейшей категории — во всю дорожку, вдвое меньшей — вполовину", () => {
    renderPage()

    const bars = fills()
    expect(bars).toHaveLength(10)
    // Сравниваем числом, а не строкой: «60.0%» от toFixed(1) и
    // нормализация CSSOM — не то, что проверяет этот тест.
    expect(parseFloat(bars[0]?.style.width ?? "")).toBeCloseTo(100)
    expect(parseFloat(bars[4]?.style.width ?? "")).toBeCloseTo(60)
  })

  it("итог стоит вверху карточки, строки «Итого» внизу нет", () => {
    renderPage()

    expect(card().getByText(/За месяц/)).toBeInTheDocument()
    expect(card().getByText(/5\s?500/)).toBeInTheDocument()
    expect(card().queryByText("Итого")).not.toBeInTheDocument()
  })

  it("доля считается от показанных строк и печатается через запятую", () => {
    // Возврат уводит общую сумму ответа в 5450, но строка с ним не
    // показывается — доли должны считаться от 5500, иначе их сумма
    // перевалит за сто процентов.
    categories = [...categories, cat("cneg", "Возврат")]
    byCategory.items = [
      ...byCategory.items,
      { category_id: "cneg", amount_rub: "-50.00" },
    ]
    renderPage()

    expect(card().getByText("18,2%")).toBeInTheDocument()
    expect(card().getByText("1,8%")).toBeInTheDocument()
  })

  it("отрицательная сумма не показывается и в итог не входит", () => {
    categories = [...categories, cat("cneg", "Возврат")]
    byCategory.items = [
      ...byCategory.items,
      { category_id: "cneg", amount_rub: "-50.00" },
    ]
    renderPage()

    expect(fills()).toHaveLength(10)
    expect(card().queryByText("Возврат")).not.toBeInTheDocument()
    expect(card().getByText(/5\s?500/)).toBeInTheDocument()
  })

  it("когда все суммы нулевые — текст про отсутствие расходов", () => {
    byCategory.items = byCategory.items.map((i) => ({
      ...i,
      amount_rub: "0",
    }))
    renderPage()

    expect(card().getByText("За этот месяц расходов нет.")).toBeInTheDocument()
    expect(fills()).toHaveLength(0)
  })

  it("длинный путь категории выводится целиком", () => {
    categories = [
      cat("p1", "Очень длинный родитель"),
      cat("ch1", "И подкатегория подлиннее", "p1"),
    ]
    byCategory.items = [{ category_id: "ch1", amount_rub: "1000.00" }]
    renderPage()

    expect(
      card().getByText("Очень длинный родитель → И подкатегория подлиннее"),
    ).toBeInTheDocument()
  })

  it("две категории не из активного списка дают две строки", () => {
    categories = []
    byCategory.items = [
      { category_id: "gone-1", amount_rub: "300.00" },
      { category_id: "gone-2", amount_rub: "200.00" },
    ]
    renderPage()

    expect(card().getAllByText("Категория")).toHaveLength(2)
    expect(fills()).toHaveLength(2)
  })
})
