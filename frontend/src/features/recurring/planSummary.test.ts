import { describe, expect, it } from "vitest"

import type { Category } from "@/features/categories/types"
import type { Recurring } from "@/features/recurring/types"
import { buildRecurringPlanSummary } from "@/features/recurring/planSummary"

const PARENT_ID = "10000000-0000-0000-0000-000000000001"
const CHILD_ID = "10000000-0000-0000-0000-000000000002"

const categories: Category[] = [
  {
    id: PARENT_ID,
    name: "Дом",
    kind: "expense",
    parent_id: null,
    icon: null,
    sort_order: 0,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: CHILD_ID,
    name: "Коммунальные услуги",
    kind: "expense",
    parent_id: PARENT_ID,
    icon: null,
    sort_order: 0,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function recurring(
  categoryId: string,
  amountRub: string,
  name: string,
): Recurring {
  return {
    id: crypto.randomUUID(),
    required: "required",
    category_id: categoryId,
    name,
    monthly_amount: amountRub,
    currency_code: "RUB",
    amount_rub: amountRub,
    comments: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }
}

describe("buildRecurringPlanSummary", () => {
  it("uses parent plan as the category envelope", () => {
    const result = buildRecurringPlanSummary(
      [
        recurring(PARENT_ID, "10000", "Дом"),
        recurring(CHILD_ID, "4000", "Коммунальные услуги"),
      ],
      categories,
    )

    expect(result.totalRub).toBe(10000)
    expect(result.categories[0]?.detailedRub).toBe(4000)
  })

  it("sums subcategories when parent plan is absent", () => {
    const result = buildRecurringPlanSummary(
      [
        recurring(CHILD_ID, "4000", "Электричество"),
        recurring(CHILD_ID, "3000", "Вода"),
      ],
      categories,
    )

    expect(result.totalRub).toBe(7000)
  })

  it("marks details that exceed the parent envelope", () => {
    const result = buildRecurringPlanSummary(
      [
        recurring(PARENT_ID, "5000", "Дом"),
        recurring(CHILD_ID, "7000", "Коммунальные услуги"),
      ],
      categories,
    )

    expect(result.totalRub).toBe(5000)
    expect(result.categories[0]?.isExceeded).toBe(true)
  })
})
