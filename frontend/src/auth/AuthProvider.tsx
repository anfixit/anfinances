import { useCallback, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"

import {
  fetchMe,
  login as loginRequest,
  logout as logoutRequest,
} from "@/auth/authApi"
import { AuthContext } from "@/auth/authContext"
import type { AuthContextValue, AuthStatus } from "@/auth/authContext"
import { setAccessToken, setOnAuthExpired } from "@/auth/tokenStore"
import type { User } from "@/auth/types"
import { refreshAccessToken } from "@/lib/api/refresh"
import { queryClient } from "@/lib/query/queryClient"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading")
  const [user, setUser] = useState<User | null>(null)

  // Тихий вход при старте: refresh по cookie → /auth/me. Нет cookie —
  // переходим в unauthenticated (увидим экран логина).
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        await refreshAccessToken()
        const me = await fetchMe()
        if (!cancelled) {
          setUser(me)
          setStatus("authenticated")
        }
      } catch {
        if (!cancelled) {
          setAccessToken(null)
          setStatus("unauthenticated")
        }
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  // Когда api-перехватчик не смог обновить токен — уводим в
  // unauthenticated (ProtectedRoute редиректит на /login).
  useEffect(() => {
    setOnAuthExpired(() => {
      setAccessToken(null)
      setUser(null)
      setStatus("unauthenticated")
      queryClient.clear()
    })
    return () => setOnAuthExpired(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginRequest(email, password)
    setAccessToken(token)
    const me = await fetchMe()
    setUser(me)
    setStatus("authenticated")
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setAccessToken(null)
      setUser(null)
      setStatus("unauthenticated")
      queryClient.clear()
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, logout }),
    [status, user, login, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
