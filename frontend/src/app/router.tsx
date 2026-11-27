import { createBrowserRouter } from "react-router-dom"

import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { Layout } from "@/app/Layout"
import { NotFoundPage, RouteErrorPage } from "@/app/RouteStatus"
import { LoginPage } from "@/features/auth/LoginPage"

// Страницы грузятся по требованию. Раньше всё приложение, включая
// графики обзора (~360 КБ), качалось сразу — даже на экране входа и
// на странице согласия ИИ, где графиков нет. Вход остаётся в общем
// бандле: с него начинается каждая сессия.
export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
    errorElement: <RouteErrorPage />,
  },
  // Согласие OAuth для ИИ-ассистентов: вне Layout (без меню), вход
  // проверяет сама страница — после логина возвращает сюда же.
  {
    path: "/oauth/authorize",
    lazy: async () => ({
      Component: (await import("@/features/ai/OAuthAuthorizePage"))
        .OAuthAuthorizePage,
    }),
    errorElement: <RouteErrorPage />,
  },
  {
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <Layout />,
        children: [
          {
            path: "/",
            lazy: async () => ({
              Component: (await import("@/features/summary/DashboardPage"))
                .DashboardPage,
            }),
          },
          {
            path: "/transactions",
            lazy: async () => ({
              Component: (
                await import("@/features/transactions/TransactionsPage")
              ).TransactionsPage,
            }),
          },
          {
            path: "/budgets",
            lazy: async () => ({
              Component: (await import("@/features/budgets/BudgetsPage"))
                .BudgetsPage,
            }),
          },
          {
            path: "/recurring",
            lazy: async () => ({
              Component: (await import("@/features/recurring/RecurringPage"))
                .RecurringPage,
            }),
          },
          {
            path: "/credits",
            lazy: async () => ({
              Component: (await import("@/features/credits/CreditsPage"))
                .CreditsPage,
            }),
          },
          {
            path: "/accounts",
            lazy: async () => ({
              Component: (await import("@/features/accounts/AccountsPage"))
                .AccountsPage,
            }),
          },
          {
            path: "/categories",
            lazy: async () => ({
              Component: (await import("@/features/categories/CategoriesPage"))
                .CategoriesPage,
            }),
          },
          {
            path: "/payees",
            lazy: async () => ({
              Component: (await import("@/features/payees/PayeesPage"))
                .PayeesPage,
            }),
          },
          {
            path: "/currencies",
            lazy: async () => ({
              Component: (await import("@/features/currencies/CurrenciesPage"))
                .CurrenciesPage,
            }),
          },
          {
            path: "/settings",
            lazy: async () => ({
              Component: (await import("@/features/settings/SettingsPage"))
                .SettingsPage,
            }),
          },
          {
            path: "/backup",
            lazy: async () => ({
              Component: (await import("@/features/backup/BackupPage"))
                .BackupPage,
            }),
          },
          {
            path: "/trash",
            lazy: async () => ({
              Component: (await import("@/features/trash/TrashPage"))
                .TrashPage,
            }),
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
])
