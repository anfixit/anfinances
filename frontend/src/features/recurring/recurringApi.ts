import type { Recurring } from "@/features/recurring/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"
import type { RequiredKind } from "@/types/enums"

export interface RecurringCreateInput {
  required?: RequiredKind
  category_id: string
  name: string
  monthly_amount: string
  currency_code?: string
  comments?: string | null
}

export interface RecurringUpdateInput {
  required?: RequiredKind
  category_id?: string
  name?: string
  monthly_amount?: string
  currency_code?: string
  comments?: string | null
}

export interface RecurringGenerationProposal {
  category_id: string
  category_name: string
  category_path: string
  monthly_amount: string
  currency_code: string
}

export async function listRecurring(): Promise<Recurring[]> {
  return unwrap(await api.get<ApiResponse<Recurring[]>>("/recurring"))
}

export async function createRecurring(
  input: RecurringCreateInput,
): Promise<Recurring> {
  return unwrap(await api.post<ApiResponse<Recurring>>("/recurring", input))
}

export async function updateRecurring(
  id: string,
  input: RecurringUpdateInput,
): Promise<Recurring> {
  return unwrap(
    await api.patch<ApiResponse<Recurring>>(`/recurring/${id}`, input),
  )
}

export async function archiveRecurring(id: string): Promise<void> {
  await api.delete(`/recurring/${id}`)
}

export async function previewGeneration(): Promise<
  RecurringGenerationProposal[]
> {
  return unwrap(
    await api.get<ApiResponse<RecurringGenerationProposal[]>>(
      "/recurring/generation-preview",
    ),
  )
}

export async function generateFromCategories(
  categoryIds: string[],
): Promise<Recurring[]> {
  return unwrap(
    await api.post<ApiResponse<Recurring[]>>(
      "/recurring/generate-from-categories",
      { category_ids: categoryIds },
    ),
  )
}
