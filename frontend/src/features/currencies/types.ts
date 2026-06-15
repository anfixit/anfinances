import type { IsoDate, Money } from "@/types/api"

// Зеркало схем домена currencies / users.
export interface Currency {
  code: string
  name: string
  symbol: string | null
  decimals: number
}

export interface ExchangeRate {
  base_code: string
  quote_code: string
  rate: Money
  fetched_at: IsoDate
}

export interface UserCurrency {
  id: string
  currency_code: string
  is_default: boolean
  sort_order: number
}

export interface RefreshResult {
  updated: number
  base: string
}
