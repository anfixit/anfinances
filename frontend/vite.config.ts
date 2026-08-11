import { fileURLToPath, URL } from "node:url"

import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Прокси /api → FastAPI (dev). Алиас @/ → src.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Библиотеки отдельно от своего кода: они меняются раз в
        // полгода, а приложение — каждый деплой. Одним куском
        // браузер каждый раз качал заново и то, и другое.
        manualChunks: (id: string) => {
          if (!id.includes("node_modules")) {
            return undefined
          }
          if (id.includes("recharts") || id.includes("d3-")) {
            return "charts"
          }
          if (id.includes("react-router") || id.includes("react-dom")) {
            return "react"
          }
          if (id.includes("@tanstack")) {
            return "query"
          }
          return "vendor"
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})
