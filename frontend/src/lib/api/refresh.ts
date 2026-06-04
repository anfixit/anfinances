import axios from "axios"

import { setAccessToken } from "@/auth/tokenStore"
import type { ApiResponse } from "@/types/api"

interface AccessTokenData {
  access_token: string
  token_type: string
}

// Отдельный инстанс без перехватчиков: сам запрос refresh не должен
// уходить в рекурсию на 401. Refresh-cookie летит автоматически.
const refreshClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,
})

let inflight: Promise<string> | null = null

async function doRefresh(): Promise<string> {
  const res =
    await refreshClient.post<ApiResponse<AccessTokenData>>("/auth/refresh")
  const token = res.data.data.access_token
  setAccessToken(token)
  return token
}

// Single-flight: параллельные 401 ждут один общий refresh, иначе
// ротация refresh-токена сломается.
export function refreshAccessToken(): Promise<string> {
  inflight ??= doRefresh().finally(() => {
    inflight = null
  })
  return inflight
}
