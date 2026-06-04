import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  archiveAccount,
  createAccount,
  listAccounts,
  restoreAccount,
  updateAccount,
} from "@/features/accounts/accountsApi"
import type {
  AccountCreateInput,
  AccountUpdateInput,
} from "@/features/accounts/accountsApi"
import { queryKeys } from "@/lib/query/keys"

export function useAccounts() {
  return useQuery({ queryKey: queryKeys.accounts, queryFn: listAccounts })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: AccountCreateInput) => createAccount(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.accounts }),
  })
}

export function useUpdateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; input: AccountUpdateInput }) =>
      updateAccount(vars.id, vars.input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.accounts }),
  })
}

export function useArchiveAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveAccount(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.accounts }),
  })
}

export function useRestoreAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => restoreAccount(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.accounts }),
  })
}
