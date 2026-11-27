import { AppError } from "@/lib/api/errors"

// Ошибка действия без собственной формы: «Удалить», «В архив»,
// «Переставить», «Отозвать доступ». Раньше такой сбой проглатывался
// молча — строка оставалась на месте, и было непонятно, удалилось или
// нет. Формы показывают ошибку у полей сами и сюда не пишут.

type Listener = (message: string) => void

const listeners = new Set<Listener>()

const FALLBACK =
  "Не получилось сохранить. Проверьте связь и попробуйте ещё раз."

export function reportError(error: unknown): void {
  const message = error instanceof AppError ? error.message : FALLBACK
  for (const listener of listeners) {
    listener(message)
  }
}

export function subscribeToErrors(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
