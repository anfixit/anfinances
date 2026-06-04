// Access-токен живёт только в памяти модуля (не в localStorage):
// при XSS его нельзя вытащить из стораджа. Refresh — в HttpOnly-cookie.
let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}
