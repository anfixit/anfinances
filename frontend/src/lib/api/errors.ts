import type { ApiErrorBody, ApiErrorDetail } from "@/types/api"

// Ошибки бэка приходят без конверта: {code, message, details}.
export class AppError extends Error {
  readonly code: string
  readonly details: ApiErrorDetail[]

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.name = "AppError"
    this.code = body.code
    this.details = body.details ?? []
  }
}

export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    "message" in value
  )
}
