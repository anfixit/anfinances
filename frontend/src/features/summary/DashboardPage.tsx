import { useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { useCategories } from "@/features/categories/hooks"
import {
  useByCategory,
  useCashflow,
  useDashboard,
} from "@/features/summary/hooks"
import { formatMoney } from "@/lib/money"

const PIE_COLORS = [
  "#4b53c9",
  "#77536c",
  "#2e6a45",
  "#b3261e",
  "#5b5d72",
  "#9a6700",
  "#3a7d8c",
  "#8c5a3a",
  "#6750a4",
  "#b58392",
]

function currentMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function parseMonth(month: string): { year: number; mon: number } {
  const [ys, ms] = month.split("-")
  return { year: Number(ys), mon: Number(ms) }
}

function monthBounds(month: string): { from: string; to: string } {
  const { year, mon } = parseMonth(month)
  const lastDay = new Date(year, mon, 0).getDate()
  return {
    from: `${month}-01`,
    to: `${month}-${String(lastDay).padStart(2, "0")}`,
  }
}

function shiftMonth(month: string, delta: number): string {
  const { year, mon } = parseMonth(month)
  const d = new Date(year, mon - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function monthLabel(month: string): string {
  const { year, mon } = parseMonth(month)
  return new Intl.DateTimeFormat("ru-RU", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, mon - 1, 1))
}

export function DashboardPage() {
  const [month, setMonth] = useState<string>(() => currentMonth())
  const bounds = monthBounds(month)

  const dash = useDashboard()
  const flow = useCashflow(bounds.from, bounds.to)
  const cats = useByCategory(month)
  const categoriesQ = useCategories()

  const catName = (id: string | null): string => {
    if (id === null) {
      return "Без категории"
    }
    return (
      (categoriesQ.data ?? []).find((c) => c.id === id)?.name ?? "Категория"
    )
  }

  const flowData = flow.data
    ? [
        {
          name: "Доход",
          value: Number(flow.data.income_rub),
          color: "var(--income)",
        },
        {
          name: "Расход",
          value: Number(flow.data.expense_rub),
          color: "var(--expense)",
        },
      ]
    : []

  const pieData = (cats.data?.items ?? [])
    .map((i) => ({
      name: catName(i.category_id),
      value: Number(i.amount_rub),
    }))
    .filter((d) => d.value > 0)

  return (
    <>
      <h1>Обзор</h1>

      <div className="card capital">
        {dash.isPending && <p>Загрузка…</p>}
        {dash.isError && <p className="error">Не удалось загрузить капитал</p>}
        {dash.data && (
          <>
            <span className="capital-label">Капитал (в рублях)</span>
            <span className="capital-value num">
              {formatMoney(dash.data.total_capital_rub, "RUB")}
            </span>
            {!dash.data.is_total_complete && (
              <p className="capital-warning" role="status">
                Итог рассчитан не полностью: нет курса для {" "}
                {dash.data.missing_rate_currencies.join(", ")}
              </p>
            )}
            <ul className="acc-list">
              {dash.data.accounts.map((a) => (
                <li key={a.account_id} className="acc-row">
                  <span className="acc-name">{a.name}</span>
                  <span className="num">
                    {formatMoney(a.balance, a.currency_code)}
                  </span>
                  {a.currency_code !== "RUB" && (
                    <span className="acc-rub num">
                      {a.balance_rub === null
                        ? "Курс недоступен"
                        : formatMoney(a.balance_rub, "RUB")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="month-switch">
        <button
          type="button"
          className="btn-tonal"
          onClick={() => setMonth((m) => shiftMonth(m, -1))}
        >
          ‹
        </button>
        <span className="month-label">{monthLabel(month)}</span>
        <button
          type="button"
          className="btn-tonal"
          onClick={() => setMonth((m) => shiftMonth(m, 1))}
        >
          ›
        </button>
      </div>

      <div className="card">
        <h2>Доходы и расходы</h2>
        {flow.isPending && <p>Загрузка…</p>}
        {flow.data && (
          <>
            <div className="stat-row">
              <div className="stat">
                <span className="stat-label">Доход</span>
                <span className="stat-value num income">
                  {formatMoney(flow.data.income_rub, "RUB")}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Расход</span>
                <span className="stat-value num expense">
                  {formatMoney(flow.data.expense_rub, "RUB")}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Итого</span>
                <span className="stat-value num">
                  {formatMoney(flow.data.net_rub, "RUB")}
                </span>
              </div>
            </div>
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flowData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis width={80} />
                  <Tooltip />
                  <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                    {flowData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h2>Расходы по категориям</h2>
        {cats.isPending && <p>Загрузка…</p>}
        {cats.data && pieData.length === 0 && (
          <p>За этот месяц расходов нет.</p>
        )}
        {pieData.length > 0 && (
          <div className="chart-box chart-box--tall">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={70}
                  outerRadius={110}
                  paddingAngle={2}
                >
                  {pieData.map((d, i) => (
                    <Cell
                      key={d.name}
                      fill={PIE_COLORS[i % PIE_COLORS.length] ?? "#888888"}
                    />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </>
  )
}
