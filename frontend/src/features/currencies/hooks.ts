import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  listCurrencies,
  listMyCurrencies,
  listRates,
  refreshRates,
  setMyCurrencies,
} from "@/features/currencies/currenciesApi"
import type { UserCurrencyItem } from "@/features/currencies/currenciesApi"
import { queryKeys } from "@/lib/query/keys"

export function useCurrencies() {
  return useQuery({
    queryKey: queryKeys.currencies,
    queryFn: listCurrencies,
  })
}

export function useRates() {
  return useQuery({ queryKey: queryKeys.rates, queryFn: listRates })
}

export function useMyCurrencies() {
  return useQuery({
    queryKey: queryKeys.myCurrencies,
    queryFn: listMyCurrencies,
  })
}

export function useSetMyCurrencies() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: UserCurrencyItem[]) => setMyCurrencies(items),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.myCurrencies }),
  })
}

export function useRefreshRates() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => refreshRates(),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.rates }),
  })
}

/**
 * Валюты для селектов в формах — только свои, а не весь справочник.
 *
 * В справочнике полторы сотни валют мира; выбирать из них рубль
 * каждый раз — работа на ровном месте. Названия берём из общего
 * справочника: в наборе пользователя хранится только код.
 */
export function useCurrencyOptions() {
  const mine = useMyCurrencies()
  const registry = useCurrencies()

  const names = new Map(
    (registry.data ?? []).map((c) => [c.code, c.name]),
  )
  const options = [...(mine.data ?? [])]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((c) => ({
      code: c.currency_code,
      label: names.has(c.currency_code)
        ? `${c.currency_code} — ${names.get(c.currency_code)}`
        : c.currency_code,
    }))

  return {
    options,
    isPending: mine.isPending,
    // Пустой набор — не ошибка, но и выбрать из него нечего.
    isEmpty: mine.isSuccess && options.length === 0,
  }
}
