import type {
  Transaction,
  TransactionCursor,
  TransactionFilters,
  Transfer,
} from "@/features/transactions/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"
import type { RequiredKind } from "@/types/enums"

export interface TransactionCreateInput {
  account_id: string
  kind: "expense" | "income"
  amount: string
  date: string
  category_id?: string | null
  required?: RequiredKind | null
  comment?: string | null
}

export interface TransactionUpdateInput {
  amount?: string
  date?: string
  category_id?: string | null
  required?: RequiredKind | null
  comment?: string | null
}

export interface TransferCreateInput {
  from_account_id: string
  to_account_id: string
  amount_from: string
  amount_to: string
  date: string
  comment?: string | null
  fee_amount?: string | null
  fee_category_id?: string | null
}

export interface TransactionPage {
  items: Transaction[]
  nextCursor: TransactionCursor | null
}

// meta типизируется локально: глобальный Meta объявляет next_cursor
// строкой, а бэкенд отдаёт объект-курсор именно для transactions.
interface ListMeta {
  next_cursor: TransactionCursor | null
}

export async function listTransactions(
  filters: TransactionFilters,
  cursor: TransactionCursor | null,
  limit = 20,
): Promise<TransactionPage> {
  const params: Record<string, string | number> = { limit }
  if (filters.date_from) params.date_from = filters.date_from
  if (filters.date_to) params.date_to = filters.date_to
  if (filters.account_id) params.account_id = filters.account_id
  if (filters.category_id) params.category_id = filters.category_id
  if (filters.kind) params.kind = filters.kind
  if (cursor) {
    params.cursor_date = cursor.cursor_date
    params.cursor_id = cursor.cursor_id
  }

  const res = await api.get<ApiResponse<Transaction[]>>("/transactions", {
    params,
  })
  const meta = res.data.meta as unknown as ListMeta
  return { items: res.data.data, nextCursor: meta.next_cursor ?? null }
}

export async function createTransaction(
  input: TransactionCreateInput,
): Promise<Transaction> {
  return unwrap(
    await api.post<ApiResponse<Transaction>>("/transactions", input),
  )
}

export async function updateTransaction(
  id: string,
  input: TransactionUpdateInput,
): Promise<Transaction> {
  return unwrap(
    await api.patch<ApiResponse<Transaction>>(`/transactions/${id}`, input),
  )
}

export async function deleteTransaction(id: string): Promise<void> {
  await api.delete(`/transactions/${id}`)
}

export async function createTransfer(
  input: TransferCreateInput,
): Promise<Transfer> {
  return unwrap(await api.post<ApiResponse<Transfer>>("/transfers", input))
}

export async function getTransfer(id: string): Promise<Transfer> {
  return unwrap(await api.get<ApiResponse<Transfer>>(`/transfers/${id}`))
}

export async function updateTransfer(
  id: string,
  input: TransferCreateInput,
): Promise<Transfer> {
  return unwrap(
    await api.patch<ApiResponse<Transfer>>(`/transfers/${id}`, input),
  )
}

export async function deleteTransfer(id: string): Promise<void> {
  await api.delete(`/transfers/${id}`)
}
