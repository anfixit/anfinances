import type { ApiErrorBody, ApiErrorDetail } from "@/types/api"

// Ошибки бэка приходят без конверта: {code, message, details}.
export class AppError extends Error {
  readonly code: string
  readonly details: ApiErrorDetail[]

  constructor(body: ApiErrorBody) {
    const details = body.details ?? []
    const message =
      body.message === "Validation failed" && details[0]
        ? details[0].message
        : body.message
    super(message)
    this.name = "AppError"
    this.code = body.code
    this.details = details
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
