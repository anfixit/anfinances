import type { IsoDate, Money } from "@/types/api"

// Зеркало BudgetRead (app/domains/budgets/schemas.py). Все суммы в рублях.
export interface Budget {
  id: string
  month: string
  category_id: string
  planned: Money
  notes: string | null
  rollover: boolean
  rollover_amount: Money
  available: Money
  spent: Money
  remaining: Money
  created_at: IsoDate
  updated_at: IsoDate
}
