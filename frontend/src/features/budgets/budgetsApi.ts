import type { Budget } from "@/features/budgets/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export interface BudgetCreateInput {
  month: string
  category_id: string
  planned: string
  notes?: string | null
  rollover: boolean
}

export interface BudgetUpdateInput {
  planned?: string
  notes?: string | null
  rollover?: boolean
}

export interface BudgetImportItem {
  category_id: string
  planned: string
  notes?: string | null
  rollover: boolean
}

export async function listBudgets(month: string): Promise<Budget[]> {
  return unwrap(
    await api.get<ApiResponse<Budget[]>>("/budgets", { params: { month } }),
  )
}

export async function createBudget(
  input: BudgetCreateInput,
): Promise<Budget> {
  return unwrap(await api.post<ApiResponse<Budget>>("/budgets", input))
}

export async function updateBudget(
  id: string,
  input: BudgetUpdateInput,
): Promise<Budget> {
  return unwrap(await api.patch<ApiResponse<Budget>>(`/budgets/${id}`, input))
}

export async function deleteBudget(id: string): Promise<void> {
  await api.delete(`/budgets/${id}`)
}

export async function importBudgets(
  month: string,
  items: BudgetImportItem[],
): Promise<Budget[]> {
  return unwrap(
    await api.post<ApiResponse<Budget[]>>("/budgets/import", { month, items }),
  )
}
