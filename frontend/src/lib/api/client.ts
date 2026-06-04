import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios"

import { getAccessToken, setAccessToken } from "@/auth/tokenStore"
import { AppError, isApiErrorBody } from "@/lib/api/errors"
import { API_BASE_URL } from "@/lib/api/baseUrl"
import { refreshAccessToken } from "@/lib/api/refresh"
import type { ApiResponse } from "@/types/api"

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`)
  }
  return config
})

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

function toError(error: AxiosError): AppError | AxiosError {
  const body = error.response?.data
  return isApiErrorBody(body) ? new AppError(body) : error
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status

    if (status !== 401 || !config || config._retried) {
      return Promise.reject(toError(error))
    }
    // /auth/refresh сам отдал 401 — сессии нет, не зацикливаемся.
    if (config.url?.endsWith("/auth/refresh")) {
      setAccessToken(null)
      return Promise.reject(toError(error))
    }

    config._retried = true
    try {
      await refreshAccessToken()
      return await api(config)
    } catch {
      setAccessToken(null)
      return Promise.reject(toError(error))
    }
  },
)

// Распаковка конверта: вызовы возвращают уже data, не {data, meta}.
export function unwrap<T>(response: AxiosResponse<ApiResponse<T>>): T {
  return response.data.data
}
