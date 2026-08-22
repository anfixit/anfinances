import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  listReconciliations,
  previewReconciliation,
  reconcile,
} from "@/features/accounts/reconcileApi"
import type { ReconcileInput } from "@/features/accounts/reconcileApi"
import { queryKeys } from "@/lib/query/keys"

export function useReconciliations(accountId: string | null) {
  return useQuery({
    queryKey: queryKeys.reconciliations(accountId ?? ""),
    queryFn: () => listReconciliations(accountId ?? ""),
    enabled: accountId !== null,
  })
}

export function usePreviewReconciliation() {
  return useMutation({
    mutationFn: (vars: { accountId: string; input: ReconcileInput }) =>
      previewReconciliation(vars.accountId, vars.input),
  })
}

export function useReconcile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { accountId: string; input: ReconcileInput }) =>
      reconcile(vars.accountId, vars.input),
    onSuccess: () => {
      // Корректировка меняет остаток счёта и капитал, а отметка —
      // список операций.
      void qc.invalidateQueries({ queryKey: queryKeys.accounts })
      void qc.invalidateQueries({ queryKey: ["transactions"] })
      void qc.invalidateQueries({ queryKey: ["summary"] })
      void qc.invalidateQueries({ queryKey: ["reconciliations"] })
    },
  })
}
