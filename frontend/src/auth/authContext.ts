import { createContext } from "react"

import type { User } from "@/auth/types"

export type AuthStatus = "loading" | "authenticated" | "unauthenticated"

export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Подставить свежий профиль — после того как сервер его сохранил. */
  updateUser: (user: User) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
