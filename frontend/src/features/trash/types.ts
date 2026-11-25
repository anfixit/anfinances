import type { IsoDate } from "@/types/api"

/** Строка для окон подтверждения удаления. */
export const TRASH_NOTE = "Вернуть можно из корзины: Настройки → Корзина."

export type DeletedKind = "transaction" | "transfer" | "credit_payment"

export interface DeletedRecord {
  id: string
  kind: DeletedKind
  summary: string
  /** Кто удалил: «Сайт» или «ИИ: ChatGPT». */
  source: string
  deleted_at: IsoDate
  restored_at: IsoDate | null
}
