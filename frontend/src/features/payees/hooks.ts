import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  acceptCandidate,
  deletePayee,
  listCandidates,
  listPayees,
  mergePayees,
  rejectCandidate,
  renamePayee,
  setPayeeVaried,
  spendingByPayee,
  unrejectCandidate,
} from "@/features/payees/payeesApi"
import type { CandidateStatus } from "@/features/payees/types"
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

export function useCandidates(status: CandidateStatus) {
  return useQuery({
    queryKey: queryKeys.payeeCandidates(status),
    queryFn: () => listCandidates(status),
  })
}

// Обновление данных после мутаций делает глобальный MutationCache.
export function useAcceptCandidate() {
  return useMutation({
    mutationFn: (vars: { id: string; payeeId: string | null }) =>
      acceptCandidate(vars.id, vars.payeeId),
  })
}

export function useRejectCandidate() {
  return useMutation({ mutationFn: (id: string) => rejectCandidate(id) })
}

export function useUnrejectCandidate() {
  return useMutation({ mutationFn: (id: string) => unrejectCandidate(id) })
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

export function useSetPayeeVaried() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; varied: boolean }) =>
      setPayeeVaried(vars.id, vars.varied),
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
