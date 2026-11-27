// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { SpendingByPayee } from "@/features/payees/types"

// Обзор тянет десяток хуков; нас интересует только отчёт по
// получателям, остальные отдают «ещё грузится».
const pending = { data: undefined, isPending: true }

vi.mock("@/features/budgets/hooks", () => ({ useBudgets: () => pending }))
vi.mock("@/features/categories/hooks", () => ({
  useCategories: () => pending,
}))
vi.mock("@/features/summary/hooks", () => ({
  useByCategory: () => pending,
  useCashflow: () => pending,
  useDailyAllowance: () => pending,
  useDashboard: () => pending,
  useMoneyAge: () => pending,
}))
vi.mock("@/features/transactions/hooks", () => ({
  useTransactions: () => pending,
}))

let report: SpendingByPayee
vi.mock("@/features/payees/hooks", () => ({
  useSpendingByPayee: () => ({ data: report, isPending: false }),
}))

import { DashboardPage } from "@/features/summary/DashboardPage"

function renderPage() {
  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  report = {
    month: "2026-08",
    items: [
      {
        payee_id: "p1",
        name: "Пятёрочка",
        amount_rub: "800.00",
        operations: 2,
      },
    ],
    total_rub: "800.00",
    unsorted_names: 0,
    unsorted_amount: "0",
  }
})

afterEach(cleanup)

describe("строка «не разобрано» под отчётом по получателям", () => {
  it("показывает число имён и сумму со ссылкой в очередь", () => {
    report.unsorted_names = 2
    report.unsorted_amount = "1100.00"
    renderPage()

    const link = screen.getByRole("link", { name: /не разобрано/i })
    expect(link).toHaveAttribute("href", "/payees")
    expect(link).toHaveTextContent(/2 имени/)
    expect(link).toHaveTextContent(/1\s?100/)
  })

  it("при нуле имён строки нет вовсе", () => {
    renderPage()
    expect(screen.queryByText(/не разобрано/i)).not.toBeInTheDocument()
  })

  it("видна, даже если подтверждённых получателей нет", () => {
    report.items = []
    report.total_rub = "0"
    report.unsorted_names = 1
    report.unsorted_amount = "300.00"
    renderPage()
    expect(screen.getByText(/не разобрано/i)).toBeInTheDocument()
  })
})
