import type { AuthorizeParams } from "@/features/ai/scopes"
import type {
  AiConnection,
  AiScope,
  AuthorizeCheck,
  PersonalTokenCreated,
} from "@/features/ai/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function listConnections(): Promise<AiConnection[]> {
  const res = await api.get<ApiResponse<AiConnection[]>>("/ai/connections")
  return unwrap(res)
}

export async function createPersonalToken(input: {
  name: string
  scopes: AiScope[]
}): Promise<PersonalTokenCreated> {
  const res = await api.post<ApiResponse<PersonalTokenCreated>>(
    "/ai/connections",
    input,
  )
  return unwrap(res)
}

export async function revokeConnection(id: string): Promise<void> {
  await api.post(`/ai/connections/${id}/revoke`)
}

export async function checkAuthorization(
  params: AuthorizeParams,
): Promise<AuthorizeCheck> {
  const res = await api.get<ApiResponse<AuthorizeCheck>>(
    "/ai/oauth/authorize/check",
    { params },
  )
  return unwrap(res)
}

export async function approveAuthorization(
  params: AuthorizeParams,
  scopes: AiScope[],
): Promise<string> {
  const res = await api.post<ApiResponse<{ redirect_to: string }>>(
    "/ai/oauth/authorize/approve",
    { ...params, scopes },
  )
  return unwrap(res).redirect_to
}
