import { createBrowserRouter } from "react-router-dom"

import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { Layout } from "@/app/Layout"
import { CategoriesPage } from "@/features/categories/CategoriesPage"
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
        element: <Layout />,
        children: [
          { path: "/", element: <HomePage /> },
          { path: "/categories", element: <CategoriesPage /> },
        ],
      },
    ],
  },
])
