import { useEffect } from "react"
import type { ReactNode } from "react"

interface SheetProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

export function Sheet({ open, title, onClose, children }: SheetProps) {
  useEffect(() => {
    if (!open) {
      return
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("keydown", onKey)
    }
  }, [open, onClose])

  if (!open) {
    return null
  }

  return (
    <div className="sheet-scrim" onClick={onClose}>
      <aside
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
