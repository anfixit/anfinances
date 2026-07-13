import type { Credit, CreditPayment } from "@/features/credits/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export interface CreditCreateInput {
  name: string
  lender?: string | null
  currency_code: string
  principal_initial: string
  annual_rate?: string | null
  term_months?: number | null
  start_date?: string | null
  payment_day?: number | null
  linked_account_id?: string | null
  comments?: string | null
}

export interface CreditUpdateInput {
  name?: string
  lender?: string | null
  principal_initial?: string
  annual_rate?: string | null
  term_months?: number | null
  start_date?: string | null
  payment_day?: number | null
  linked_account_id?: string | null
  comments?: string | null
}

export interface CreditPaymentCreateInput {
  payment_account_id: string
  date: string
  total_amount: string
  principal_amount: string
  interest_amount: string
  fee_amount: string
  interest_category_id?: string | null
  fee_category_id?: string | null
  comment?: string | null
}

export async function listCredits(): Promise<Credit[]> {
  return unwrap(await api.get<ApiResponse<Credit[]>>("/credits"))
}

export async function createCredit(
  input: CreditCreateInput,
): Promise<Credit> {
  return unwrap(await api.post<ApiResponse<Credit>>("/credits", input))
}

export async function updateCredit(
  id: string,
  input: CreditUpdateInput,
): Promise<Credit> {
  return unwrap(await api.patch<ApiResponse<Credit>>(`/credits/${id}`, input))
}

export async function archiveCredit(id: string): Promise<void> {
  await api.delete(`/credits/${id}`)
}

export async function listCreditPayments(
  creditId: string,
): Promise<CreditPayment[]> {
  return unwrap(
    await api.get<ApiResponse<CreditPayment[]>>(
      `/credits/${creditId}/payments`,
    ),
  )
}

export async function createCreditPayment(
  creditId: string,
  input: CreditPaymentCreateInput,
): Promise<CreditPayment> {
  return unwrap(
    await api.post<ApiResponse<CreditPayment>>(
      `/credits/${creditId}/payments`,
      input,
    ),
  )
}
