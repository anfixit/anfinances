import { createBrowserRouter } from "react-router-dom"

import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { Layout } from "@/app/Layout"
import { AccountsPage } from "@/features/accounts/AccountsPage"
import { BudgetsPage } from "@/features/budgets/BudgetsPage"
import { CategoriesPage } from "@/features/categories/CategoriesPage"
import { CurrenciesPage } from "@/features/currencies/CurrenciesPage"
import { LoginPage } from "@/features/auth/LoginPage"
import { DashboardPage } from "@/features/summary/DashboardPage"
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
          { path: "/", element: <DashboardPage /> },
          { path: "/transactions", element: <TransactionsPage /> },
          { path: "/budgets", element: <BudgetsPage /> },
          { path: "/accounts", element: <AccountsPage /> },
          { path: "/categories", element: <CategoriesPage /> },
          { path: "/currencies", element: <CurrenciesPage /> },
        ],
      },
    ],
  },
])
