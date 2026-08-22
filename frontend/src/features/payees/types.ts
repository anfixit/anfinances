import type { IsoDate, Money } from "@/types/api"

// Зеркало PayeeRead (app/domains/payees/schemas.py).
export interface Payee {
  id: string
  name: string
  last_category_id: string | null
  created_at: IsoDate
  updated_at: IsoDate
}

export interface PayeeSpending {
  payee_id: string
  name: string
  amount_rub: Money
  operations: number
}

export interface SpendingByPayee {
  month: string
  items: PayeeSpending[]
  total_rub: Money
}
