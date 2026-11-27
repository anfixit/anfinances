import { QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "react-router-dom"

import { router } from "@/app/router"
import { AuthProvider } from "@/auth/AuthProvider"
import { ConfirmProvider } from "@/components/ConfirmProvider"
import { ErrorToast } from "@/components/ErrorToast"
import { queryClient } from "@/lib/query/queryClient"

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ConfirmProvider>
          <RouterProvider router={router} />
          <ErrorToast />
        </ConfirmProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
