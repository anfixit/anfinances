// Зеркало UserRead (app/domains/auth/schemas.py).
export interface User {
  id: string
  email: string
  name: string | null
  timezone: string
  default_currency: string
  locale: string
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export type AuthMode = "single_user" | "multi_user_no_verify" | "multi_user"
