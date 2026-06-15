import { useState } from "react"

import { applyTheme, getStoredTheme, systemTheme } from "@/lib/theme"
import type { ThemeMode } from "@/lib/theme"

export function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>(
    () => getStoredTheme() ?? systemTheme(),
  )

  const toggle = () => {
    const next: ThemeMode = mode === "dark" ? "light" : "dark"
    applyTheme(next)
    setMode(next)
  }

  return (
    <button
      type="button"
      className="link"
      onClick={toggle}
      aria-label="Переключить тему"
    >
      {mode === "dark" ? "Светлая" : "Тёмная"}
    </button>
  )
}
