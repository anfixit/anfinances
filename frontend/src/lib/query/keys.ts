// Фабрики ключей TanStack Query. Мутации инвалидируют их по карте
// из FRONTEND_PLAN §5.2.
export const queryKeys = {
  health: ["health"] as const,
  config: ["config"] as const,
  me: ["me"] as const,
  accounts: ["accounts"] as const,
  categories: ["categories"] as const,
  payees: ["payees"] as const,
  newPayees: ["payees", "new"] as const,
  payeeSpending: (month: string) => ["payees", "spending", month] as const,
  currencies: ["currencies"] as const,
  rates: ["currencies", "rates"] as const,
  myCurrencies: ["users", "me", "currencies"] as const,
  recurring: ["recurring"] as const,
  credits: ["credits"] as const,
  creditPayments: (creditId: string) =>
    ["credits", creditId, "payments"] as const,
  transactions: (filters: Readonly<Record<string, unknown>>) =>
    ["transactions", filters] as const,
  budgets: (month: string) => ["budgets", month] as const,
  summary: {
    dashboard: ["summary", "dashboard"] as const,
    cashflow: (range: Readonly<Record<string, unknown>>) =>
      ["summary", "cashflow", range] as const,
    byCategory: (month: string) => ["summary", "by-category", month] as const,
    dailyAllowance: ["summary", "daily-allowance"] as const,
    moneyAge: ["summary", "money-age"] as const,
  },
} as const
