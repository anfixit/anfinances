import type { IsoDate, Money } from "@/types/api"

// Зеркало CreditRead (app/domains/credits/schemas.py).
export interface Credit {
  id: string
  name: string
  lender: string | null
  currency_code: string
  principal_initial: Money
  principal_balance: Money
  annual_rate: Money | null
  term_months: number | null
  start_date: string | null
  payment_day: number | null
  linked_account_id: string | null
  comments: string | null
  is_archived: boolean
  created_at: IsoDate
  updated_at: IsoDate
}

// Зеркало CreditPaymentRead.
export interface CreditPayment {
  id: string
  credit_id: string
  payment_account_id: string
  transaction_id: string | null
  date: IsoDate
  total_amount: Money
  principal_amount: Money
  interest_amount: Money
  fee_amount: Money
  currency_code: string
  interest_category_id: string | null
  fee_category_id: string | null
  comment: string | null
  created_at: IsoDate
  updated_at: IsoDate
}
