import { useState } from "react"
import { Link } from "react-router-dom"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { useBudgets } from "@/features/budgets/hooks"
import { useCategories } from "@/features/categories/hooks"
import { categoryPath } from "@/features/categories/path"
import {
  useByCategory,
  useCashflow,
  useDailyAllowance,
  useDashboard,
  useMoneyAge,
} from "@/features/summary/hooks"
import { useSpendingByPayee } from "@/features/payees/hooks"
import { useTransactions } from "@/features/transactions/hooks"
import { buildRules, overspentCategories } from "@/features/summary/rules"
import type { Rule } from "@/features/summary/rules"
import { formatMoney, sumMoney } from "@/lib/money"

// Подсказки графиков показывали голое «16000» — в приложении про
// деньги число без валюты читается как ошибка.
function moneyTip(value: unknown): string {
  return formatMoney(String(value), "RUB")
}

// Recharts рисует подсказку жёстко белой поверх инлайн-стилей; в
// тёмной теме она светилась чужим прямоугольником. Перебиваем
// токенами — переменные в inline style работают.
const TIP_BOX = {
  background: "var(--surface-container-low)",
  border: "1px solid var(--outline-variant)",
  borderRadius: "var(--shape-s)",
  boxShadow: "var(--elev-2)",
  color: "var(--on-surface)",
  padding: "8px 10px",
}
const TIP_TEXT = { color: "var(--on-surface)" }

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
  const payeesQ = useSpendingByPayee(month)
  // Операции без категории бюджет молча пропускает. Пока их не
  // видно, они и не разбираются.
  const looseQ = useTransactions({ uncategorized: true })

  const categoryById = new Map((categoriesQ.data ?? []).map((c) => [c.id, c]))
  // Полный путь: «Аксессуары» бывают и в «Авто», и в «Одежде», и по
  // одному имени две строки таблицы было не различить.
  const catName = (id: string | null): string => {
    if (id === null) {
      return "Без категории"
    }
    return categoryPath(categoryById, id) ?? "Категория"
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

  const parentOf = new Map(
    (categoriesQ.data ?? []).map((c) => [c.id, c.parent_id]),
  )
  const spending = cats.data?.items ?? []
  const rules = buildRules(
    allowance.data,
    age.data,
    budgetsQ.data,
    spending,
    parentOf,
  )
  const overspent = overspentCategories(
    budgetsQ.data ?? [],
    spending,
    parentOf,
  )

  const catRows = (cats.data?.items ?? [])
    .map((i) => ({
      // Ключ — id, а не имя: одинаковые имена подкатегорий давали
      // повторяющиеся ключи, и React мог потерять строку.
      key: i.category_id ?? "uncategorized",
      name: catName(i.category_id),
      value: Number(i.amount_rub),
    }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value)

  const loose = looseQ.data?.pages.flatMap((p) => p.items) ?? []

  // Итог — по показанным строкам, а не по всему ответу. Возврат
  // больше трат даёт по категории минус, такая строка не
  // показывается, и доли от полного ответа сложились бы в больше
  // ста процентов.
  const catTotal = sumMoney(catRows.map((d) => String(d.value)))
  // Полоса отсчитывается от самой крупной категории, а не от итога:
  // массив уже отсортирован по убыванию, значит максимум — первый.
  // Строки с нулём и минусом отфильтрованы, поэтому при непустом
  // списке делитель всегда больше нуля.
  const catMax = catRows[0]?.value ?? 0

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
              {/* «Не хватает −6 517 ₽» — двойное отрицание: в
                  подписи уже сказано, что это нехватка. */}
              {allowance.data.is_short
                ? formatMoney(
                    allowance.data.safe_to_spend_rub.replace(/^-/, ""),
                    "RUB",
                  )
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
            {/* Пока планов на месяц нет, «не распределено» в точности
                равно «свободно» слева — та же цифра в третий раз на
                экране ничего не добавляла. Говорим, что делать. */}
            {budgetsQ.data?.length === 0 ? (
              <>
                <span className="capital-label">Планов на месяц нет</span>
                <p className="allowance-note">
                  Деньги ещё не разложены по категориям.{" "}
                  <Link to="/budgets">Задать лимиты на «Бюджете»</Link> —
                  первое правило: у каждого рубля своя работа.
                </p>
              </>
            ) : (
              <>
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
              </>
            )}
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

      {loose.length > 0 && (
        <div className="card">
          <h2>Без категории</h2>
          <p className="allowance-note">
            Эти операции бюджет не видит — пока у них нет категории, они
            не попадают ни в один конверт.
          </p>
          <table className="data-table">
            <tbody>
              {loose.slice(0, 10).map((t) => (
                <tr key={t.id}>
                  <td>
                    {new Date(t.date).toLocaleDateString("ru-RU")}
                    {t.payee_name_snapshot !== null &&
                      ` · ${t.payee_name_snapshot}`}
                  </td>
                  <td className="num">
                    {formatMoney(t.amount, t.currency_code)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loose.length > 10 && (
            <p className="allowance-note">
              Показаны первые 10. Остальные — на странице операций.
            </p>
          )}
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
                  <td>
                    {catName(c.categoryId)}
                    {c.unbudgeted && (
                      <span className="acc-meta"> · без лимита</span>
                    )}
                  </td>
                  <td className="num expense">
                    −{formatMoney(String(c.over), "RUB")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="allowance-note">
            Покройте их из категорий с запасом — кнопка «Покрыть» в
            бюджете, а где лимита нет — задайте его.
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
                  <Tooltip
                    formatter={moneyTip}
                    contentStyle={TIP_BOX}
                    itemStyle={TIP_TEXT}
                    labelStyle={TIP_TEXT}
                    cursor={{ fill: "var(--surface-container)" }}
                  />
                  <Bar
                    // Без имени подсказка подписывала столбец «value».
                    name="Сумма"
                    dataKey="value"
                    radius={[3, 3, 0, 0]}
                    animationDuration={450}
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

      {/* Категория говорит, на что ушли деньги; получатель — кому.
          Без второго «Продукты 12 340» не подсказывает, что делать. */}
      {payeesQ.data && payeesQ.data.items.length > 0 && (
        <div className="card">
          <h2>Кому ушли деньги</h2>
          <table className="data-table">
            <tbody>
              {payeesQ.data.items.slice(0, 12).map((p) => (
                <tr key={p.payee_id}>
                  <td>{p.name}</td>
                  <td className="num data-share">
                    {p.operations} оп.
                  </td>
                  <td className="num">
                    {formatMoney(p.amount_rub, "RUB")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Расходы по категориям</h2>
        {cats.isPending && <p>Загрузка…</p>}
        {cats.data && catRows.length === 0 && (
          <p>За этот месяц расходов нет.</p>
        )}
        {catRows.length > 0 && (
          <>
            {/* Итог стоит над списком: в кольце он лежал бы в центре,
                а в таблице строка «Итого» снизу дублировала бы его. */}
            <div className="cat-head">
              <span>За месяц</span>
              <strong className="cat-head-total num">
                {formatMoney(String(catTotal), "RUB")}
              </strong>
            </div>
            {/* Полосы от одной вертикали: так величины сравниваются
                точнее, чем секторами круга, и цвет не обязан
                различать категории — их различают имена. */}
            <table className="data-table cat-list">
              <tbody>
                {catRows.map((d) => (
                  <tr key={d.key}>
                    <td>{d.name}</td>
                    <td className="cat-bar">
                      <span className="cat-bar-track" aria-hidden="true">
                        <span
                          className="cat-bar-fill"
                          style={{
                            width: `${((d.value / catMax) * 100).toFixed(1)}%`,
                          }}
                        />
                      </span>
                    </td>
                    <td className="num">
                      {formatMoney(String(d.value), "RUB")}
                    </td>
                    <td className="num data-share">
                      {catTotal > 0
                        ? // Запятая, а не точка: рядом в той же
                          // строке рубли через запятую, и точка
                          // рядом с ними читается как чужая.
                          `${((d.value / catTotal) * 100)
                            .toFixed(1)
                            .replace(".", ",")}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
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
