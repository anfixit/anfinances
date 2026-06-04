import { createBrowserRouter } from "react-router-dom"

import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { Layout } from "@/app/Layout"
import { CategoriesPage } from "@/features/categories/CategoriesPage"
import { CurrenciesPage } from "@/features/currencies/CurrenciesPage"
import { LoginPage } from "@/features/auth/LoginPage"
import { HomePage } from "@/features/home/HomePage"
import { TransactionsPage } from "@/features/transactions/TransactionsPage"

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
          { path: "/transactions", element: <TransactionsPage /> },
          { path: "/categories", element: <CategoriesPage /> },
          { path: "/currencies", element: <CurrenciesPage /> },
        ],
      },
    ],
  },
])
