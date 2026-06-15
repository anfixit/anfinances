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
