import type {
  Candidate,
  CandidateStatus,
  Payee,
  SpendingByPayee,
} from "@/features/payees/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function listPayees(): Promise<Payee[]> {
  const res = await api.get<ApiResponse<Payee[]>>("/payees")
  return unwrap(res)
}

export async function listCandidates(
  status: CandidateStatus,
): Promise<Candidate[]> {
  const res = await api.get<ApiResponse<Candidate[]>>("/payees/candidates", {
    params: { status },
  })
  return unwrap(res)
}

// payeeId = null — завести нового получателя; иначе приклеить имя к
// существующему.
export async function acceptCandidate(
  id: string,
  payeeId: string | null,
): Promise<void> {
  await api.post(`/payees/candidates/${id}/accept`, { payee_id: payeeId })
}

export async function rejectCandidate(id: string): Promise<void> {
  await api.post(`/payees/candidates/${id}/reject`)
}

export async function unrejectCandidate(id: string): Promise<void> {
  await api.post(`/payees/candidates/${id}/unreject`)
}

export async function spendingByPayee(month: string): Promise<SpendingByPayee> {
  const res = await api.get<ApiResponse<SpendingByPayee>>("/payees/spending", {
    params: { month },
  })
  return unwrap(res)
}

export async function renamePayee(id: string, name: string): Promise<Payee> {
  const res = await api.patch<ApiResponse<Payee>>(`/payees/${id}`, { name })
  return unwrap(res)
}

export async function setPayeeVaried(
  id: string,
  varied: boolean,
): Promise<Payee> {
  const res = await api.patch<ApiResponse<Payee>>(`/payees/${id}`, {
    varied_categories: varied,
  })
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
