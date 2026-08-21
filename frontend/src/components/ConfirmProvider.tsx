/** Диалог подтверждения вместо window.confirm.
 *
 * Нативное окно показывает голый текст и имя домена, не умеет
 * выделить опасное действие и намертво вешает страницу, пока висит.
 * Здесь то же самое, но своим оформлением и с местом под последствия:
 * что удаляем, на сколько изменится итог, что потом не вернуть.
 *
 * Обещание вместо колбэка, чтобы на месте вызова осталась та же
 * прямая строчка, что была с confirm(): `if (await confirm(...))`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"

import {
  ConfirmContext,
  type ConfirmApi,
  type ConfirmOptions,
  type NotifyOptions,
} from "@/components/confirm-context"

interface Pending {
  title: string
  body: string[]
  confirmLabel: string
  /** null — сообщение с одной кнопкой, отменять там нечего. */
  cancelLabel: string | null
  danger: boolean
  resolve: (ok: boolean) => void
}

function paragraphs(body: string | string[] | undefined): string[] {
  if (body === undefined) {
    return []
  }
  return typeof body === "string" ? [body] : body
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null)

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setPending({
          title: options.title,
          body: paragraphs(options.body),
          confirmLabel: options.confirmLabel ?? "Продолжить",
          cancelLabel: options.cancelLabel ?? "Отмена",
          danger: options.danger ?? false,
          resolve,
        })
      }),
    [],
  )

  const notify = useCallback(
    (options: NotifyOptions) =>
      new Promise<void>((resolve) => {
        setPending({
          title: options.title,
          body: paragraphs(options.body),
          confirmLabel: options.closeLabel ?? "Понятно",
          cancelLabel: null,
          danger: false,
          resolve: () => {
            resolve()
          },
        })
      }),
    [],
  )

  const api = useMemo<ConfirmApi>(
    () => ({ confirm, notify }),
    [confirm, notify],
  )

  const answer = useCallback((ok: boolean) => {
    setPending((current) => {
      current?.resolve(ok)
      return null
    })
  }, [])

  return (
    <ConfirmContext value={api}>
      {children}
      {pending !== null && <Dialog pending={pending} onAnswer={answer} />}
    </ConfirmContext>
  )
}

function Dialog({
  pending,
  onAnswer,
}: {
  pending: Pending
  onAnswer: (ok: boolean) => void
}) {
  const panel = useRef<HTMLDivElement | null>(null)
  const safe = useRef<HTMLButtonElement | null>(null)
  const returnTo = useRef<HTMLElement | null>(null)

  useEffect(() => {
    returnTo.current = document.activeElement as HTMLElement | null
    safe.current?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onAnswer(false)
        return
      }
      if (e.key !== "Tab" || panel.current === null) {
        return
      }
      // Диалог модальный: Tab не должен уводить на список под ним.
      const items = [
        ...panel.current.querySelectorAll<HTMLButtonElement>("button"),
      ]
      const first = items[0]
      const last = items[items.length - 1]
      if (first === undefined || last === undefined) {
        return
      }
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("keydown", onKey)
      document.body.style.overflow = previousOverflow
      returnTo.current?.focus()
    }
  }, [onAnswer])

  const cancel = pending.cancelLabel

  return (
    <div
      className="confirm-scrim"
      onClick={() => {
        onAnswer(false)
      }}
    >
      <div
        ref={panel}
        className="confirm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => {
          e.stopPropagation()
        }}
      >
        <h2 id="confirm-title">{pending.title}</h2>
        {pending.body.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <div className="confirm-actions">
          {cancel !== null && (
            <button
              type="button"
              ref={safe}
              className="btn-tonal"
              onClick={() => {
                onAnswer(false)
              }}
            >
              {cancel}
            </button>
          )}
          <button
            type="button"
            // Единственная кнопка — она же безопасная: фокус ей.
            ref={cancel === null ? safe : null}
            className={pending.danger ? "btn-danger" : undefined}
            onClick={() => {
              onAnswer(true)
            }}
          >
            {pending.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
