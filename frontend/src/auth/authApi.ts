import { api, unwrap } from "@/lib/api/client"
import type { User } from "@/auth/types"
import type { ApiResponse } from "@/types/api"

interface AccessTokenData {
  access_token: string
  token_type: string
}

// Тело ответа login — только access; refresh ставится в HttpOnly-cookie.
export async function login(email: string, password: string): Promise<string> {
  const res = await api.post<ApiResponse<AccessTokenData>>("/auth/login", {
    email,
    password,
  })
  return unwrap(res).access_token
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout")
}

export async function fetchMe(): Promise<User> {
  const res = await api.get<ApiResponse<User>>("/auth/me")
  return unwrap(res)
}
