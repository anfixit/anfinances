import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  archiveRecurring,
  createRecurring,
  generateFromCategories,
  listRecurring,
  previewGeneration,
  updateRecurring,
} from "@/features/recurring/recurringApi"
import type {
  RecurringCreateInput,
  RecurringUpdateInput,
} from "@/features/recurring/recurringApi"
import type { Recurring } from "@/features/recurring/types"
import { queryKeys } from "@/lib/query/keys"

export function useRecurring() {
  return useQuery({ queryKey: queryKeys.recurring, queryFn: listRecurring })
}

export function useCreateRecurring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: RecurringCreateInput) => createRecurring(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.recurring }),
  })
}

export function useUpdateRecurring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: RecurringUpdateInput }) =>
      updateRecurring(vars.id, vars.input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.recurring }),
  })
}

export function useArchiveRecurring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveRecurring(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.recurring }),
  })
}

export function usePreviewGeneration() {
  return useMutation({ mutationFn: () => previewGeneration() })
}

export function useGenerateFromCategories() {
  const qc = useQueryClient()
  return useMutation<Recurring[], Error, string[]>({
    mutationFn: (categoryIds) => generateFromCategories(categoryIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.recurring }),
  })
}
