import type { Payee, SpendingByPayee } from "@/features/payees/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function listPayees(): Promise<Payee[]> {
  const res = await api.get<ApiResponse<Payee[]>>("/payees")
  return unwrap(res)
}

export async function listNewPayees(): Promise<Payee[]> {
  const res = await api.get<ApiResponse<Payee[]>>("/payees/new")
  return unwrap(res)
}

export async function spendingByPayee(
  month: string,
): Promise<SpendingByPayee> {
  const res = await api.get<ApiResponse<SpendingByPayee>>(
    "/payees/spending",
    { params: { month } },
  )
  return unwrap(res)
}

export async function renamePayee(id: string, name: string): Promise<Payee> {
  const res = await api.patch<ApiResponse<Payee>>(`/payees/${id}`, { name })
  return unwrap(res)
}

export async function mergePayees(
  sourceId: string,
  targetId: string,
): Promise<{ moved: number }> {
  const res = await api.post<ApiResponse<{ moved: number }>>(
    `/payees/${sourceId}/merge/${targetId}`,
  )
  return unwrap(res)
}

export async function deletePayee(id: string): Promise<void> {
  await api.delete(`/payees/${id}`)
}
