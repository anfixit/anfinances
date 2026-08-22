import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  deletePayee,
  listNewPayees,
  listPayees,
  mergePayees,
  renamePayee,
  spendingByPayee,
} from "@/features/payees/payeesApi"
import { queryKeys } from "@/lib/query/keys"

function invalidate(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["payees"] })
  // Операции держат снимок имени получателя — после слияния и
  // переименования список надо перечитать.
  void qc.invalidateQueries({ queryKey: ["transactions"] })
}

export function usePayees() {
  return useQuery({ queryKey: queryKeys.payees, queryFn: listPayees })
}

export function useNewPayees() {
  return useQuery({ queryKey: queryKeys.newPayees, queryFn: listNewPayees })
}

export function useSpendingByPayee(month: string) {
  return useQuery({
    queryKey: queryKeys.payeeSpending(month),
    queryFn: () => spendingByPayee(month),
  })
}

export function useRenamePayee() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; name: string }) =>
      renamePayee(vars.id, vars.name),
    onSuccess: () => invalidate(qc),
  })
}

export function useMergePayees() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { sourceId: string; targetId: string }) =>
      mergePayees(vars.sourceId, vars.targetId),
    onSuccess: () => invalidate(qc),
  })
}

export function useDeletePayee() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deletePayee(id),
    onSuccess: () => invalidate(qc),
  })
}
