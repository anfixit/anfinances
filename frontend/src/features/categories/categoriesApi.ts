import type { Category } from "@/features/categories/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export interface CategoryCreateInput {
  name: string
  kind: Category["kind"]
  parent_id?: string | null
  icon?: string | null
  sort_order?: number
}

export interface CategoryUpdateInput {
  name?: string
  icon?: string | null
  sort_order?: number
}

export async function listCategories(): Promise<Category[]> {
  const res = await api.get<ApiResponse<Category[]>>("/categories")
  return unwrap(res)
}

export async function createCategory(
  input: CategoryCreateInput,
): Promise<Category> {
  const res = await api.post<ApiResponse<Category>>("/categories", input)
  return unwrap(res)
}

export async function updateCategory(
  id: string,
  input: CategoryUpdateInput,
): Promise<Category> {
  const res = await api.patch<ApiResponse<Category>>(
    `/categories/${id}`,
    input,
  )
  return unwrap(res)
}

export async function archiveCategory(id: string): Promise<void> {
  await api.delete(`/categories/${id}`)
}
