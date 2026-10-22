import type { AiScope } from "@/features/ai/types"

// Параметры запроса авторизации OAuth, которые страница согласия
// пересылает бэкенду как есть. Остальное из адреса не берём.
export const AUTHORIZE_PARAMS = [
  "response_type",
  "client_id",
  "redirect_uri",
  "scope",
  "state",
  "code_challenge",
  "code_challenge_method",
  "resource",
] as const

export type AuthorizeParams = Partial<
  Record<(typeof AUTHORIZE_PARAMS)[number], string>
>

export function authorizeParamsFrom(search: URLSearchParams): AuthorizeParams {
  const params: AuthorizeParams = {}
  for (const key of AUTHORIZE_PARAMS) {
    const value = search.get(key)
    if (value !== null) {
      params[key] = value
    }
  }
  return params
}

// Права словами: запись включает чтение, поэтому для пары
// показываем одно «чтение и запись».
export function scopesLabel(scopes: readonly AiScope[]): string {
  return scopes.includes("finance.write") ? "Чтение и запись" : "Только чтение"
}

/** Куда вернуть после входа. Только свои пути — без открытого редиректа. */
export function safeReturnPath(from: unknown): string {
  if (
    typeof from !== "string" ||
    !from.startsWith("/") ||
    from.startsWith("//") ||
    from.startsWith("/\\")
  ) {
    return "/"
  }
  return from
}
