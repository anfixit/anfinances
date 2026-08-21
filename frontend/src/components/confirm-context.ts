/** Контекст диалога подтверждения: сам контекст, хук и типы.
 *
 * Отдельно от провайдера, потому что react-refresh ругается на файл,
 * который экспортирует и компонент, и всё остальное.
 */

import { createContext, use } from "react"

export interface ConfirmOptions {
  /** Заголовок: что именно произойдёт. Без «Вы уверены?». */
  title: string
  /** Пояснение — строка или абзацы. Здесь место последствиям. */
  body?: string | string[]
  confirmLabel?: string
  cancelLabel?: string
  /** Красная кнопка и фокус на «Отмене»: действие не откатить. */
  danger?: boolean
}

export interface NotifyOptions {
  title: string
  body?: string | string[]
  closeLabel?: string
}

export interface ConfirmApi {
  confirm: (options: ConfirmOptions) => Promise<boolean>
  notify: (options: NotifyOptions) => Promise<void>
}

export const ConfirmContext = createContext<ConfirmApi | null>(null)

export function useConfirm(): ConfirmApi {
  const api = use(ConfirmContext)
  if (api === null) {
    throw new Error("useConfirm вызван вне ConfirmProvider")
  }
  return api
}
