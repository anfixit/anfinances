import type { DeletedRecord } from "@/features/trash/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function listTrash(): Promise<DeletedRecord[]> {
  const res = await api.get<ApiResponse<DeletedRecord[]>>("/trash", {
    params: { limit: 200 },
  })
  return unwrap(res)
}

export async function restoreFromTrash(id: string): Promise<DeletedRecord> {
  const res = await api.post<ApiResponse<DeletedRecord>>(
    `/trash/${id}/restore`,
  )
  return unwrap(res)
}
