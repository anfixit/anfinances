import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  archiveCredit,
  createCredit,
  createCreditPayment,
  listCreditPayments,
  listCredits,
  updateCredit,
} from "@/features/credits/creditsApi"
import type {
  CreditCreateInput,
  CreditPaymentCreateInput,
  CreditUpdateInput,
} from "@/features/credits/creditsApi"
import { queryKeys } from "@/lib/query/keys"

function invalidateCredits(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: queryKeys.credits })
}

function invalidateAfterCreditPayment(qc: QueryClient, creditId: string): void {
  invalidateCredits(qc)
  void qc.invalidateQueries({ queryKey: queryKeys.accounts })
  void qc.invalidateQueries({ queryKey: ["transactions"] })
  void qc.invalidateQueries({ queryKey: ["summary"] })
  void qc.invalidateQueries({ queryKey: queryKeys.creditPayments(creditId) })
}

export function useCredits() {
  return useQuery({ queryKey: queryKeys.credits, queryFn: listCredits })
}

export function useCreditPayments(creditId: string | null) {
  return useQuery({
    queryKey: queryKeys.creditPayments(creditId ?? ""),
    queryFn: () => listCreditPayments(creditId as string),
    enabled: creditId !== null,
  })
}

export function useCreateCredit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: CreditCreateInput) => createCredit(input),
    onSuccess: () => invalidateCredits(qc),
  })
}

export function useUpdateCredit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: CreditUpdateInput }) =>
      updateCredit(vars.id, vars.input),
    onSuccess: () => invalidateCredits(qc),
  })
}

export function useArchiveCredit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveCredit(id),
    onSuccess: () => invalidateCredits(qc),
  })
}

export function useCreateCreditPayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      creditId: string
      input: CreditPaymentCreateInput
    }) => createCreditPayment(vars.creditId, vars.input),
    onSuccess: (_data, vars) => invalidateAfterCreditPayment(qc, vars.creditId),
  })
}
