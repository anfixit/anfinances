import type { Goal, GoalUpsertInput } from "@/features/goals/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function listGoals(month: string): Promise<Goal[]> {
  const res = await api.get<ApiResponse<Goal[]>>("/goals", {
    params: { month },
  })
  return unwrap(res)
}

export async function upsertGoal(input: GoalUpsertInput): Promise<void> {
  await api.put("/goals", input)
}

export async function deleteGoal(categoryId: string): Promise<void> {
  await api.delete(`/goals/${categoryId}`)
}
