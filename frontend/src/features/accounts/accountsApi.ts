import type { Account } from "@/features/accounts/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"
import type { AccountType } from "@/types/enums"

export interface AccountCreateInput {
  name: string
  type: AccountType
  currency_code: string
  initial_balance?: string
  credit_limit?: string | null
  color?: string | null
  sort_order?: number
  comments?: string | null
}

export interface AccountUpdateInput {
  name?: string
  type?: AccountType
  initial_balance?: string
  credit_limit?: string | null
  color?: string | null
  sort_order?: number
  comments?: string | null
}

export async function listAccounts(): Promise<Account[]> {
  return unwrap(await api.get<ApiResponse<Account[]>>("/accounts"))
}

export async function createAccount(
  input: AccountCreateInput,
): Promise<Account> {
  return unwrap(await api.post<ApiResponse<Account>>("/accounts", input))
}

export async function updateAccount(
  id: string,
  input: AccountUpdateInput,
): Promise<Account> {
  return unwrap(
    await api.patch<ApiResponse<Account>>(`/accounts/${id}`, input),
  )
}

export async function archiveAccount(id: string): Promise<void> {
  await api.delete(`/accounts/${id}`)
}

export async function restoreAccount(id: string): Promise<Account> {
  return unwrap(
    await api.post<ApiResponse<Account>>(`/accounts/${id}/restore`),
  )
}
