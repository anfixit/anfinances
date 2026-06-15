// Конверт ответов бэкенда (ADR-014). Деньги — строки (Decimal),
// даты — ISO-строки. Клиент не считает деньги, только форматирует.
export type Money = string
export type IsoDate = string

export interface Meta {
  page?: number
  per_page?: number
  total?: number
  total_pages?: number
  next_cursor?: string | null
}

export interface ApiResponse<T> {
  data: T
  meta: Meta
}

export interface ApiErrorDetail {
  field?: string | null
  message: string
}

export interface ApiErrorBody {
  code: string
  message: string
  details?: ApiErrorDetail[]
}
