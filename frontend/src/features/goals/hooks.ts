import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import {
  deleteGoal,
  listGoals,
  upsertGoal,
} from "@/features/goals/goalsApi"
import type { GoalUpsertInput } from "@/features/goals/types"
import { queryKeys } from "@/lib/query/keys"

function invalidate(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["goals"] })
}

export function useGoals(month: string) {
  return useQuery({
    queryKey: queryKeys.goals(month),
    queryFn: () => listGoals(month),
  })
}

export function useUpsertGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: GoalUpsertInput) => upsertGoal(input),
    onSuccess: () => invalidate(qc),
  })
}

export function useDeleteGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (categoryId: string) => deleteGoal(categoryId),
    onSuccess: () => invalidate(qc),
  })
}
