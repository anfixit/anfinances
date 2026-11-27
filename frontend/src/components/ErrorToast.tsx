import { useEffect, useState } from "react"

import { subscribeToErrors } from "@/lib/errors/reportError"

const VISIBLE_MS = 8000

/** Плашка внизу экрана с ошибкой последнего действия. */
export function ErrorToast() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => subscribeToErrors(setMessage), [])

  useEffect(() => {
    if (message === null) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setMessage(null)
    }, VISIBLE_MS)
    return () => {
      window.clearTimeout(timer)
    }
  }, [message])

  if (message === null) {
    return null
  }

  return (
    <div className="error-toast" role="alert">
      <span>{message}</span>
      <button
        type="button"
        className="error-toast-close"
        aria-label="Закрыть"
        onClick={() => {
          setMessage(null)
        }}
      >
        ×
      </button>
    </div>
  )
}
