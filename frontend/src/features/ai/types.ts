export type AiScope = "finance.read" | "finance.write"

export interface AiConnection {
  id: string
  kind: "personal" | "oauth"
  name: string
  client_id: string | null
  scopes: AiScope[]
  created_at: string
  last_used_at: string | null
}

export interface PersonalTokenCreated {
  connection: AiConnection
  // Показывается один раз: на сервере остаётся только хеш.
  token: string
}

export interface AuthorizeCheck {
  status: "ok" | "error"
  client_id: string | null
  client_name: string | null
  redirect_host: string | null
  scopes: AiScope[]
  deny_redirect_to: string | null
  error: string | null
  message: string | null
  redirect_to: string | null
}
