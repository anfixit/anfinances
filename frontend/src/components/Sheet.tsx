import { useEffect, useRef } from "react"
import type { ReactNode } from "react"

interface SheetProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",")

export function Sheet({ open, title, onClose, children }: SheetProps) {
  const panel = useRef<HTMLElement | null>(null)
  const returnTo = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    // Куда вернуть фокус после закрытия: без этого он падает в
    // начало страницы, и с клавиатуры до списка не добраться.
    returnTo.current = document.activeElement as HTMLElement | null
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()

    // Фон не должен уезжать под панелью: на телефоне прокрутка
    // «проваливается» на страницу и теряет место в списке.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
        return
      }
      if (e.key !== "Tab" || panel.current === null) {
        return
      }
      // Ловушка фокуса: Tab внутри панели не должен уводить на
      // элементы под ней — они для пользователя сейчас не существуют.
      const items = [
        ...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ].filter((el) => el.offsetParent !== null)
      if (items.length === 0) {
        return
      }
      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      if (firstItem === undefined || lastItem === undefined) {
        return
      }
      const active = document.activeElement
      if (e.shiftKey && active === firstItem) {
        e.preventDefault()
        lastItem.focus()
      } else if (!e.shiftKey && active === lastItem) {
        e.preventDefault()
        firstItem.focus()
      }
    }

    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("keydown", onKey)
      document.body.style.overflow = previousOverflow
      returnTo.current?.focus()
    }
  }, [open, onClose])

  if (!open) {
    return null
  }

  return (
    <div className="sheet-scrim" onClick={onClose}>
      <aside
        ref={panel}
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => {
          e.stopPropagation()
        }}
      >
        <header className="sheet-head">
          <h2>{title}</h2>
          <button type="button" className="link" onClick={onClose}>
            Закрыть
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </aside>
    </div>
  )
}
