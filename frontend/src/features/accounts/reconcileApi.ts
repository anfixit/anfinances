import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse, IsoDate, Money } from "@/types/api"

export interface ReconcileInput {
  statement_balance: string
  date: string
  adjust?: boolean
  adjustment_category_id?: string | null
}

export interface ReconciliationPreview {
  account_id: string
  date: IsoDate
  statement_balance: Money
  computed_balance: Money
  difference: Money
  unreconciled_count: number
}

export interface Reconciliation {
  id: string
  account_id: string
  date: IsoDate
  statement_balance: Money
  computed_balance: Money
  adjustment_transaction_id: string | null
  created_at: IsoDate
}

export async function previewReconciliation(
  accountId: string,
  input: ReconcileInput,
): Promise<ReconciliationPreview> {
  const res = await api.post<ApiResponse<ReconciliationPreview>>(
    `/accounts/${accountId}/reconcile/preview`,
    input,
  )
  return unwrap(res)
}

export async function reconcile(
  accountId: string,
  input: ReconcileInput,
): Promise<Reconciliation> {
  const res = await api.post<ApiResponse<Reconciliation>>(
    `/accounts/${accountId}/reconcile`,
    input,
  )
  return unwrap(res)
}

export async function listReconciliations(
  accountId: string,
): Promise<Reconciliation[]> {
  const res = await api.get<ApiResponse<Reconciliation[]>>(
    `/accounts/${accountId}/reconciliations`,
  )
  return unwrap(res)
}
