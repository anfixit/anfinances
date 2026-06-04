export type ThemeMode = "light" | "dark"

const STORAGE_KEY = "anfinances-theme"

export function getStoredTheme(): ThemeMode | null {
  const value = localStorage.getItem(STORAGE_KEY)
  return value === "light" || value === "dark" ? value : null
}

export function systemTheme(): ThemeMode {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
}

export function applyTheme(mode: ThemeMode): void {
  document.documentElement.dataset.theme = mode
  localStorage.setItem(STORAGE_KEY, mode)
}
