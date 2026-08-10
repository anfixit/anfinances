import type { Money } from "@/types/api"

export interface AccountBalance {
  account_id: string
  name: string
  currency_code: string
  balance: Money
  balance_rub: Money | null
}

export interface Dashboard {
  accounts: AccountBalance[]
  total_capital_rub: Money
  total_credit_debt_rub: Money
  is_total_complete: boolean
  missing_rate_currencies: string[]
}

export interface Cashflow {
  date_from: string
  date_to: string
  income_rub: Money
  expense_rub: Money
  net_rub: Money
}

export interface CategorySpending {
  category_id: string | null
  amount_rub: Money
}

export interface ByCategory {
  month: string
  items: CategorySpending[]
  total_rub: Money
}

export interface Obligation {
  name: string
  amount_rub: Money
  kind: string
}

export interface DailyAllowance {
  until: string
  days_left: number
  liquid_rub: Money
  obligations_rub: Money
  obligations: Obligation[]
  safe_to_spend_rub: Money
  per_day_rub: Money
  is_short: boolean
  is_total_complete: boolean
  missing_rate_currencies: string[]
}
