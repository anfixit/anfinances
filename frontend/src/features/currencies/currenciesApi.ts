import type {
  Currency,
  ExchangeRate,
  RefreshResult,
  UserCurrency,
} from "@/features/currencies/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export interface UserCurrencyItem {
  currency_code: string
  is_default: boolean
  sort_order: number
}

export async function listCurrencies(): Promise<Currency[]> {
  return unwrap(await api.get<ApiResponse<Currency[]>>("/currencies"))
}

export async function listRates(): Promise<ExchangeRate[]> {
  return unwrap(
    await api.get<ApiResponse<ExchangeRate[]>>("/currencies/rates"),
  )
}

export async function refreshRates(): Promise<RefreshResult> {
  return unwrap(
    await api.post<ApiResponse<RefreshResult>>("/currencies/rates/refresh"),
  )
}

export async function listMyCurrencies(): Promise<UserCurrency[]> {
  return unwrap(
    await api.get<ApiResponse<UserCurrency[]>>("/users/me/currencies"),
  )
}

export async function setMyCurrencies(
  items: UserCurrencyItem[],
): Promise<UserCurrency[]> {
  return unwrap(
    await api.put<ApiResponse<UserCurrency[]>>("/users/me/currencies", {
      items,
    }),
  )
}
