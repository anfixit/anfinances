import type { Money } from "@/types/api"

export interface AccountBalance {
  account_id: string
  name: string
  currency_code: string
  balance: Money
  balance_rub: Money
}

export interface Dashboard {
  accounts: AccountBalance[]
  total_capital_rub: Money
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
