// Access-токен живёт только в памяти модуля (не в localStorage):
// при XSS его нельзя вытащить из стораджа. Refresh — в HttpOnly-cookie.
let accessToken: string | null = null

// Подписка на «сессия умерла»: api-перехватчик дёргает её, когда
// refresh окончательно провалился, чтобы AuthProvider увёл на /login.
type AuthExpiredHandler = () => void
let onAuthExpired: AuthExpiredHandler | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function setOnAuthExpired(handler: AuthExpiredHandler | null): void {
  onAuthExpired = handler
}

// Токен протух и обновить не удалось: чистим и уведомляем подписчика.
export function notifyAuthExpired(): void {
  accessToken = null
  onAuthExpired?.()
}
