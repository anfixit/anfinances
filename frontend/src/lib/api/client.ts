import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios"

import { getAccessToken, notifyAuthExpired } from "@/auth/tokenStore"
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

// Адреса, которые нельзя чинить обновлением сессии. 401 от них значит
// «неверный пароль» или «сессии нет», а не «токен протух»: обновлять
// нечего, а повторять — тем более. Повтор входа стоил второй попытки
// из лимита (10 в минуту), и пять опечаток подряд давали 429 вместо
// внятного «неверный email или пароль».
const NO_REFRESH_RETRY = ["/auth/login", "/auth/refresh"] as const

function skipsRefresh(url: string | undefined): boolean {
  return NO_REFRESH_RETRY.some((path) => url?.endsWith(path) ?? false)
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
    if (skipsRefresh(config.url)) {
      // Refresh ответил 401 — сессии нет, уводим на /login. Для самого
      // входа этого делать нельзя: человек как раз пытается войти, и
      // чистка состояния посреди попытки выглядит как поломка сайта.
      if (config.url?.endsWith("/auth/refresh")) {
        notifyAuthExpired()
      }
      return Promise.reject(toError(error))
    }

    config._retried = true
    try {
      await refreshAccessToken()
      return await api(config)
    } catch {
      notifyAuthExpired()
      return Promise.reject(toError(error))
    }
  },
)

// Распаковка конверта: вызовы возвращают уже data, не {data, meta}.
export function unwrap<T>(response: AxiosResponse<ApiResponse<T>>): T {
  return response.data.data
}
