import { QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "react-router-dom"

import { router } from "@/app/router"
import { AuthProvider } from "@/auth/AuthProvider"
import { queryClient } from "@/lib/query/queryClient"

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  )
}
