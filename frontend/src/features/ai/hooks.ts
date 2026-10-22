import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  checkAuthorization,
  createPersonalToken,
  listConnections,
  revokeConnection,
} from "@/features/ai/aiApi"
import type { AuthorizeParams } from "@/features/ai/scopes"
import type { AiScope } from "@/features/ai/types"
import { queryKeys } from "@/lib/query/keys"

export function useAiConnections() {
  return useQuery({
    queryKey: queryKeys.aiConnections,
    queryFn: listConnections,
  })
}

export function useCreatePersonalToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { name: string; scopes: AiScope[] }) =>
      createPersonalToken(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiConnections }),
  })
}

export function useRevokeConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => revokeConnection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiConnections }),
  })
}

export function useAuthorizeCheck(params: AuthorizeParams, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.aiAuthorizeCheck(params),
    queryFn: () => checkAuthorization(params),
    enabled,
    // Проверка — разовая: повтор после ошибки и перезапрос при
    // возврате на вкладку только путают страницу согласия.
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}
