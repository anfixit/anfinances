import { useQuery } from "@tanstack/react-query"

import {
  getByCategory,
  getCashflow,
  getDashboard,
} from "@/features/summary/summaryApi"
import { queryKeys } from "@/lib/query/keys"

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.summary.dashboard,
    queryFn: getDashboard,
  })
}

export function useCashflow(from: string, to: string) {
  return useQuery({
    queryKey: queryKeys.summary.cashflow({ from, to }),
    queryFn: () => getCashflow(from, to),
  })
}

export function useByCategory(month: string) {
  return useQuery({
    queryKey: queryKeys.summary.byCategory(month),
    queryFn: () => getByCategory(month),
  })
}
