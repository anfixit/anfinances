import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  createTransaction,
  createTransfer,
  deleteTransaction,
  deleteTransfer,
  getTransfer,
  listTransactions,
  updateTransaction,
  updateTransfer,
} from "@/features/transactions/transactionsApi"
import type {
  TransactionCreateInput,
  TransactionUpdateInput,
  TransferCreateInput,
} from "@/features/transactions/transactionsApi"
import type {
  TransactionCursor,
  TransactionFilters,
} from "@/features/transactions/types"
import { queryKeys } from "@/lib/query/keys"

// Создание/изменение/удаление операции двигает балансы, сводку и
// бюджет — гасим кэш по префиксам.
function invalidateAfterTx(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["transactions"] })
  void qc.invalidateQueries({ queryKey: ["summary"] })
  void qc.invalidateQueries({ queryKey: ["transfers"] })
  void qc.invalidateQueries({ queryKey: ["budgets"] })
  void qc.invalidateQueries({ queryKey: queryKeys.accounts })
}

export function useTransactions(filters: TransactionFilters) {
  return useInfiniteQuery({
    queryKey: queryKeys.transactions(
      filters as Readonly<Record<string, unknown>>,
    ),
    queryFn: ({ pageParam }) => listTransactions(filters, pageParam, 20),
    initialPageParam: null as TransactionCursor | null,
    getNextPageParam: (last) => last.nextCursor,
  })
}

export function useCreateTransaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: TransactionCreateInput) => createTransaction(input),
    onSuccess: () => invalidateAfterTx(qc),
  })
}

export function useUpdateTransaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: TransactionUpdateInput }) =>
      updateTransaction(vars.id, vars.input),
    onSuccess: () => invalidateAfterTx(qc),
  })
}

export function useDeleteTransaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteTransaction(id),
    onSuccess: () => invalidateAfterTx(qc),
  })
}

export function useTransfer(transferId: string | null) {
  return useQuery({
    queryKey: ["transfers", transferId],
    queryFn: () => getTransfer(transferId as string),
    enabled: transferId !== null,
  })
}

export function useCreateTransfer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: TransferCreateInput) => createTransfer(input),
    onSuccess: () => invalidateAfterTx(qc),
  })
}

export function useUpdateTransfer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: TransferCreateInput }) =>
      updateTransfer(vars.id, vars.input),
    onSuccess: () => invalidateAfterTx(qc),
  })
}

export function useDeleteTransfer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteTransfer(id),
    onSuccess: () => invalidateAfterTx(qc),
  })
}
