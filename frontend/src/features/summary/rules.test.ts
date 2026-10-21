import { describe, expect, it } from "vitest"

import type { Budget } from "@/features/budgets/types"
import { buildRules, overspentCategories } from "@/features/summary/rules"

const FOOD = "food"
const GROCERIES = "groceries"
const CAR = "car"
const FUEL = "fuel"

function budget(categoryId: string, planned: string, spent: string): Budget {
  const remaining = String(Number(planned) - Number(spent))
  return {
    id: `b-${categoryId}`,
    month: "2026-10",
    category_id: categoryId,
    planned,
    notes: null,
    rollover: false,
    rollover_amount: "0",
    available: planned,
    spent,
    remaining,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  }
}

const parentOf = new Map<string, string | null>([
  [FOOD, null],
  [GROCERIES, FOOD],
  [CAR, null],
  [FUEL, CAR],
])

describe("overspentCategories", () => {
  it("видит обычный перерасход: лимит 5 000, потрачено 7 000", () => {
    // Раньше считалось по «доступно», и такой минус не замечался.
    const over = overspentCategories([budget(FOOD, "5000", "7000")])
    expect(over).toEqual([{ categoryId: FOOD, over: 2000, unbudgeted: false }])
  })

  it("трата без лимита — тоже минус", () => {
    const over = overspentCategories(
      [],
      [{ category_id: FUEL, amount_rub: "9147.50" }],
      parentOf,
    )
    expect(over).toEqual([{ categoryId: FUEL, over: 9147.5, unbudgeted: true }])
  })

  it("подкатегорию покрывает лимит родителя", () => {
    const over = overspentCategories(
      [budget(FOOD, "15000", "1300")],
      [{ category_id: GROCERIES, amount_rub: "1300" }],
      parentOf,
    )
    expect(over).toEqual([])
  })

  it("возврат без лимита минусом не считается", () => {
    const over = overspentCategories(
      [],
      [{ category_id: FUEL, amount_rub: "-500" }],
      parentOf,
    )
    expect(over).toEqual([])
  })
})

describe("правило 3", () => {
  it("не говорит «ни одна категория не в минусе», когда траты без лимита", () => {
    const rules = buildRules(
      undefined,
      undefined,
      [],
      [{ category_id: FUEL, amount_rub: "9147.50" }],
      parentOf,
    )
    const rule3 = rules.find((r) => r.n === 3)
    expect(rule3?.status).toBe("warn")
    expect(rule3?.hint).toContain("без лимита: 1")
  })
})
