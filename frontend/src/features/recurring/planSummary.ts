import type { Category } from "@/features/categories/types"
import type { Recurring } from "@/features/recurring/types"
import { sumMoney } from "@/lib/money"

interface RecurringCategorySummary {
  categoryId: string
  categoryName: string
  plannedRub: number
  detailedRub: number
  effectiveRub: number
  isExceeded: boolean
}

export interface RecurringPlanSummary {
  totalRub: number
  categories: RecurringCategorySummary[]
}

export function buildRecurringPlanSummary(
  items: readonly Recurring[],
  categories: readonly Category[],
): RecurringPlanSummary {
  const categoriesById = new Map(
    categories.map((category) => [category.id, category]),
  )
  const groupedItems = new Map<
    string,
    { parent: Recurring[]; children: Recurring[] }
  >()

  for (const item of items) {
    const category = categoriesById.get(item.category_id)
    const rootId = category?.parent_id ?? category?.id ?? item.category_id
    const group = groupedItems.get(rootId) ?? { parent: [], children: [] }

    if (category === undefined || category.parent_id === null) {
      group.parent.push(item)
    } else {
      group.children.push(item)
    }
    groupedItems.set(rootId, group)
  }

  const summaries = [...groupedItems.entries()].map(([rootId, group]) => {
    const rootCategory = categoriesById.get(rootId)
    const plannedRub = sumMoney(
      group.parent.map((item) => item.amount_rub ?? "0"),
    )
    const detailedRub = sumMoney(
      group.children.map((item) => item.amount_rub ?? "0"),
    )
    const effectiveRub = plannedRub > 0 ? plannedRub : detailedRub

    return {
      categoryId: rootId,
      categoryName: rootCategory?.name ?? "Неизвестная категория",
      plannedRub,
      detailedRub,
      effectiveRub,
      isExceeded: plannedRub > 0 && detailedRub > plannedRub,
    }
  })

  return {
    totalRub: sumMoney(
      summaries.map((summary) => String(summary.effectiveRub)),
    ),
    categories: summaries,
  }
}
