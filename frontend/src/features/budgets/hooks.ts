import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  createBudget,
  deleteBudget,
  importBudgets,
  listBudgets,
  updateBudget,
} from "@/features/budgets/budgetsApi"
import type {
  BudgetCreateInput,
  BudgetImportItem,
  BudgetUpdateInput,
} from "@/features/budgets/budgetsApi"
import { queryKeys } from "@/lib/query/keys"

function invalidate(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["budgets"] })
  void qc.invalidateQueries({ queryKey: ["summary"] })
}

export function useBudgets(month: string) {
  return useQuery({
    queryKey: queryKeys.budgets(month),
    queryFn: () => listBudgets(month),
  })
}

export function useCreateBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: BudgetCreateInput) => createBudget(input),
    onSuccess: () => invalidate(qc),
  })
}

export function useUpdateBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: BudgetUpdateInput }) =>
      updateBudget(vars.id, vars.input),
    onSuccess: () => invalidate(qc),
  })
}

export function useDeleteBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteBudget(id),
    onSuccess: () => invalidate(qc),
  })
}

export function useImportBudgets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { month: string; items: BudgetImportItem[] }) =>
      importBudgets(vars.month, vars.items),
    onSuccess: () => invalidate(qc),
  })
}
