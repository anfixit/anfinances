import type { IsoDate, Money } from "@/types/api"
import type { AccountType } from "@/types/enums"

// Зеркало AccountRead (app/domains/accounts/schemas.py).
export interface Account {
  id: string
  name: string
  type: AccountType
  currency_code: string
  initial_balance: Money
  current_balance: Money
  has_transactions: boolean
  credit_limit: Money | null
  color: string | null
  sort_order: number
  comments: string | null
  is_archived: boolean
  created_at: IsoDate
  updated_at: IsoDate
}

export const TYPE_LABELS: Record<AccountType, string> = {
  card: "Карта",
  cash: "Наличные",
  card_credit: "Кредитная карта",
  savings: "Накопительный",
  investment: "Инвестиции",
}
