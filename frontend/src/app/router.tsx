import { createBrowserRouter } from "react-router-dom"

import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { LoginPage } from "@/features/auth/LoginPage"
import { HomePage } from "@/features/home/HomePage"

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: "/",
        element: <HomePage />,
      },
    ],
  },
])
