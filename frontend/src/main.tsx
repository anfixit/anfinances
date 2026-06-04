import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { App } from "@/App"
import "@/index.css"
import "@/features/transactions/transactions.css"

// Применяем сохранённую тему до рендера, чтобы не мигало.
const storedTheme = localStorage.getItem("anfinances-theme")
if (storedTheme === "light" || storedTheme === "dark") {
  document.documentElement.dataset.theme = storedTheme
}

const root = document.getElementById("root")
if (!root) {
  throw new Error("Root element #root not found")
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
