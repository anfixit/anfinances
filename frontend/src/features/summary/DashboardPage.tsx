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

import { useBudgets } from "@/features/budgets/hooks"
import { useCategories } from "@/features/categories/hooks"
import {
  useByCategory,
  useCashflow,
  useDailyAllowance,
  useDashboard,
  useMoneyAge,
} from "@/features/summary/hooks"
import { buildRules, overspentCategories } from "@/features/summary/rules"
import type { Rule } from "@/features/summary/rules"
import { formatMoney, sumMoney } from "@/lib/money"

// Оттенки одного синего с добавками — на Хабре график не пестрит.
const PIE_COLORS = [
  "#4c8eda",
  "#7fb2e8",
  "#3f8f4a",
  "#d0453b",
  "#b9762a",
  "#6c7378",
  "#2f6ba8",
  "#a3c7ec",
  "#7a5ea8",
  "#3a8f8c",
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
  const text = new Intl.DateTimeFormat("ru-RU", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, mon - 1, 1))
  // CSS capitalize поднял бы и «г.» в «Г.» — заглавная нужна одна.
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function DashboardPage() {
  const [month, setMonth] = useState<string>(() => currentMonth())
  const bounds = monthBounds(month)

  const dash = useDashboard()
  const allowance = useDailyAllowance()
  const age = useMoneyAge()
  const flow = useCashflow(bounds.from, bounds.to)
  const cats = useByCategory(month)
  const categoriesQ = useCategories()
  const budgetsQ = useBudgets(month)

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

  const rules = buildRules(allowance.data, age.data, budgetsQ.data)
  const overspent = overspentCategories(budgetsQ.data ?? [])

  const pieData = (cats.data?.items ?? [])
    .map((i) => ({
      name: catName(i.category_id),
      value: Number(i.amount_rub),
    }))
    .filter((d) => d.value > 0)

  const catTotal = sumMoney((cats.data?.items ?? []).map((i) => i.amount_rub))

  return (
    <>
      <h1>Обзор</h1>

      {/* Правила метода — самое верхнее на странице. Сайт не просто
          хранит цифры: он говорит, что с ними не так. */}
      <div className="card rules-card">
        <h2>Метод ВНБ: четыре правила</h2>
        <div className="rules-grid">
          {rules.map((rule) => (
            <RuleTile key={rule.n} rule={rule} />
          ))}
        </div>
      </div>

      {allowance.data && (
        <div className="rules-row">
          <div className="card allowance">
            <span className="capital-label">
              {allowance.data.is_short
                ? "Не хватает на обязательства"
                : "Можно тратить в день"}
            </span>
            <span
              className={
                allowance.data.is_short
                  ? "capital-value num expense"
                  : "capital-value num"
              }
            >
              {allowance.data.is_short
                ? formatMoney(allowance.data.safe_to_spend_rub, "RUB")
                : formatMoney(allowance.data.per_day_rub, "RUB")}
            </span>
            <p className="allowance-note">
              {allowance.data.days_left} дн. до{" "}
              {new Date(allowance.data.until).toLocaleDateString("ru-RU")}.
              Свободно{" "}
              <span className="num">
                {formatMoney(allowance.data.safe_to_spend_rub, "RUB")}
              </span>{" "}
              из{" "}
              <span className="num">
                {formatMoney(allowance.data.liquid_rub, "RUB")}
              </span>
              , отложено{" "}
              <span className="num">
                {formatMoney(allowance.data.obligations_rub, "RUB")}
              </span>
              .
            </p>
            {allowance.data.obligations.length > 0 && (
              <ul className="allowance-list">
                {allowance.data.obligations.map((o) => (
                  <li key={`${o.kind}-${o.name}`} className="acc-row">
                    <span className="acc-name">{o.name}</span>
                    <span className="num">
                      {formatMoney(o.amount_rub, "RUB")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card allowance">
            <span className="capital-label">
              {allowance.data.is_overplanned
                ? "Распланировано больше, чем есть"
                : "Не распределено"}
            </span>
            <span
              className={
                allowance.data.is_overplanned
                  ? "capital-value num expense"
                  : "capital-value num"
              }
            >
              {formatMoney(allowance.data.unallocated_rub, "RUB")}
            </span>
            <p className="allowance-note">
              В планах на месяц ещё не истрачено{" "}
              <span className="num">
                {formatMoney(allowance.data.planned_remaining_rub, "RUB")}
              </span>
              .
            </p>
            {age.data && (
              <p
                className={
                  age.data.is_covered ? "allowance-note" : "capital-debt"
                }
              >
                Возраст денег:{" "}
                {formatMoney(age.data.current_month_expense_rub, "RUB")}{" "}
                потрачено против{" "}
                {formatMoney(age.data.previous_month_income_rub, "RUB")}{" "}
                дохода прошлого месяца.
              </p>
            )}
            {!allowance.data.is_total_complete && (
              <p className="capital-warning" role="status">
                Нет курса для{" "}
                {allowance.data.missing_rate_currencies.join(", ")} — счёт
                неполный.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Третье правило в действии: что именно перерасходовано и на
          сколько. Без этого списка «переносите» — пустой совет. */}
      {overspent.length > 0 && (
        <div className="card">
          <h2>Перерасход по категориям</h2>
          <table className="data-table">
            <tbody>
              {overspent.map((c) => (
                <tr key={c.categoryId}>
                  <td>{catName(c.categoryId)}</td>
                  <td className="num expense">
                    −{formatMoney(String(c.over), "RUB")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="allowance-note">
            Покройте их из категорий с запасом — кнопка «Покрыть» в
            бюджете.
          </p>
        </div>
      )}

      <div className="card capital">
        {dash.isPending && <p>Загрузка…</p>}
        {dash.isError && <p className="error">Не удалось загрузить капитал</p>}
        {dash.data && (
          <>
            <span className="capital-label">Капитал (в рублях)</span>
            <span className="capital-value num">
              {formatMoney(dash.data.total_capital_rub, "RUB")}
            </span>
            {Number(dash.data.total_credit_debt_rub) > 0 && (
              <p className="capital-debt">
                В том числе долг по кредитам:{" "}
                <span className="num">
                  −{formatMoney(dash.data.total_credit_debt_rub, "RUB")}
                </span>
              </p>
            )}
            {!dash.data.is_total_complete && (
              <p className="capital-warning" role="status">
                Итог рассчитан не полностью: нет курса для{" "}
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
                  {/* Без въезда: график читают, а не смотрят, как он
                      появляется — и анимация иногда застревает. */}
                  <Bar
                    dataKey="value"
                    radius={[3, 3, 0, 0]}
                    isAnimationActive={false}
                  >
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
          <>
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
                    isAnimationActive={false}
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
            {/* Круг показывает пропорции, но не суммы. Рядом таблица:
                по ней видно, сколько именно и какая это доля. */}
            <table className="data-table">
              <tbody>
                {[...pieData]
                  .sort((a, b) => b.value - a.value)
                  .map((d) => (
                    <tr key={d.name}>
                      <td>{d.name}</td>
                      <td className="num">
                        {formatMoney(String(d.value), "RUB")}
                      </td>
                      <td className="num data-share">
                        {catTotal > 0
                          ? `${((d.value / catTotal) * 100).toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                <tr className="data-total">
                  <td>Итого</td>
                  <td className="num">
                    {formatMoney(String(catTotal), "RUB")}
                  </td>
                  <td />
                </tr>
              </tbody>
            </table>
          </>
        )}
      </div>
    </>
  )
}

function RuleTile({ rule }: { rule: Rule }) {
  return (
    <div className={`rule rule--${rule.status}`}>
      <span className="rule-n">Правило {rule.n}</span>
      <span className="rule-name">{rule.name}</span>
      {rule.value !== null && (
        <span className="rule-value num">
          {formatMoney(String(rule.value), "RUB")}
        </span>
      )}
      <span className="rule-hint">{rule.hint}</span>
    </div>
  )
}
