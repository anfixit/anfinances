import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  archiveCategory,
  createCategory,
  listCategories,
  updateCategory,
} from "@/features/categories/categoriesApi"
import type {
  CategoryCreateInput,
  CategoryUpdateInput,
} from "@/features/categories/categoriesApi"
import { queryKeys } from "@/lib/query/keys"

export function useCategories() {
  return useQuery({
    queryKey: queryKeys.categories,
    queryFn: listCategories,
  })
}

export function useCreateCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: CategoryCreateInput) => createCategory(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.categories }),
  })
}

export function useUpdateCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: CategoryUpdateInput }) =>
      updateCategory(vars.id, vars.input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.categories }),
  })
}

export function useArchiveCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveCategory(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.categories }),
  })
}
