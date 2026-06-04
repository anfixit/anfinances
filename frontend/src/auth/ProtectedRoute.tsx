import { Navigate, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/useAuth"

export function ProtectedRoute() {
  const { status } = useAuth()

  if (status === "loading") {
    return <p className="page">Загрузка…</p>
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}
