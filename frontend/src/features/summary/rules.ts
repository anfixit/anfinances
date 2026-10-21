/** Четыре правила ВНБ, посчитанные по живым данным.
 *
 * Правила — не украшение на дашборде: каждое либо выполняется, либо
 * нет, и у каждого есть число, по которому это видно. Метод без
 * обратной связи превращается в лозунги, поэтому считаем честно и
 * говорим, что делать, когда правило не выполнено.
 */

import type { Budget } from "@/features/budgets/types"
import type { DailyAllowance, MoneyAge } from "@/features/summary/types"
import { sumMoney } from "@/lib/money"

export type RuleStatus = "ok" | "warn" | "unknown"

// Пока данных нет, правило не имеет права ничего утверждать. Иначе
// на полсекунды загрузки дашборд заявляет «ничего не отложено» при
// сорока тысячах в копилках — и после такого числам не верят.
const LOADING = "Считаю…"

/** «1 день», «3 дня», «17 дней» — иначе читается как машинный вывод. */
export function dayWord(days: number): string {
  const last = days % 10
  const tens = days % 100
  if (tens >= 11 && tens <= 14) {
    return `${String(days)} дней`
  }
  if (last === 1) {
    return `${String(days)} день`
  }
  if (last >= 2 && last <= 4) {
    return `${String(days)} дня`
  }
  return `${String(days)} дней`
}

export interface Rule {
  n: number
  name: string
  /** Число, по которому видно, выполняется правило или нет. */
  value: number | null
  status: RuleStatus
  /** Что это значит и что делать. Одна фраза. */
  hint: string
}

export interface OverspentCategory {
  categoryId: string
  over: number
  /** Потрачено там, где лимита нет вовсе. */
  unbudgeted: boolean
}

export interface SpendingItem {
  category_id: string | null
  amount_rub: string
}

/** Категории в минусе: потрачено больше лимита — или без лимита.
 *
 * Перерасход — это минус в остатке, а не в «доступно». По «доступно»
 * ловился только минус, перенесённый с прошлых месяцев, а обычное
 * «лимит 5 000, потрачено 7 000» правило не видело.
 *
 * Трата без лимита — тоже минус: денег под неё не выделяли. Но трата
 * в подкатегории покрыта лимитом родителя, если он есть: родительский
 * лимит — общий конверт на всю ветку.
 */
export function overspentCategories(
  budgets: readonly Budget[],
  spending: readonly SpendingItem[] = [],
  parentOf: ReadonlyMap<string, string | null> = new Map(),
): OverspentCategory[] {
  const budgeted = new Set(budgets.map((b) => b.category_id))
  const result: OverspentCategory[] = budgets
    .map((b) => ({
      categoryId: b.category_id,
      over: -Number(b.remaining),
      unbudgeted: false,
    }))
    .filter((c) => c.over > 0)

  for (const item of spending) {
    const spent = Number(item.amount_rub)
    const id = item.category_id
    if (id === null || spent <= 0 || budgeted.has(id)) {
      continue
    }
    const parent = parentOf.get(id) ?? null
    if (parent !== null && budgeted.has(parent)) {
      continue
    }
    result.push({ categoryId: id, over: spent, unbudgeted: true })
  }
  return result.sort((a, b) => b.over - a.over)
}

export function buildRules(
  allowance: DailyAllowance | undefined,
  age: MoneyAge | undefined,
  budgets: readonly Budget[] | undefined,
  spending: readonly SpendingItem[] = [],
  parentOf: ReadonlyMap<string, string | null> = new Map(),
): Rule[] {
  const unallocated = allowance ? Number(allowance.unallocated_rub) : null
  const obligations = allowance ? Number(allowance.obligations_rub) : null
  const over = budgets
    ? overspentCategories(budgets, spending, parentOf)
    : undefined
  const withoutLimit = over?.filter((c) => c.unbudgeted).length ?? 0
  const overTotal = over ? sumMoney(over.map((c) => String(c.over))) : null

  return [
    {
      n: 1,
      name: "У каждого рубля есть работа",
      value: unallocated,
      status:
        unallocated === null
          ? "unknown"
          : allowance?.is_overplanned === true || unallocated > 0
            ? "warn"
            : "ok",
      hint:
        allowance === undefined
          ? LOADING
          : allowance.is_overplanned
            ? "Распланировано больше, чем есть. Урежьте план."
            : unallocated !== null && unallocated > 0
              ? "Столько денег ещё не получили назначения. Разложите по категориям."
              : "Свободных денег без назначения нет — так и должно быть.",
    },
    {
      n: 2,
      name: "Готовьтесь к истинным расходам",
      value: obligations,
      status:
        obligations === null ? "unknown" : obligations > 0 ? "ok" : "warn",
      hint:
        allowance === undefined
          ? LOADING
          : obligations !== null && obligations > 0
            ? "Столько отложено на обязательные платежи — эти деньги уже заняты."
            : "Ничего не отложено. Заведите план-минимум и копилки на редкие траты.",
    },
    {
      n: 3,
      name: "Переносите, а не отчаивайтесь",
      value: overTotal,
      status:
        overTotal === null ? "unknown" : overTotal > 0 ? "warn" : "ok",
      hint:
        budgets === undefined
          ? LOADING
          : overTotal !== null && overTotal > 0
            ? `Категорий в минусе: ${String(over?.length ?? 0)}${
                withoutLimit > 0
                  ? `, из них без лимита: ${String(withoutLimit)}`
                  : ""
              }. Покройте из других или задайте лимит — это нормальная часть метода.`
            : "Ни одна категория не в минусе.",
    },
    {
      n: 4,
      name: "Живите на деньги прошлого месяца",
      value: age ? Number(age.current_month_expense_rub) : null,
      status: age === undefined ? "unknown" : age.is_covered ? "ok" : "warn",
      hint:
        age === undefined
          ? LOADING
          : `${
              age.is_covered
                ? "Траты этого месяца покрыты доходом прошлого."
                : "Тратите быстрее, чем зарабатывали в прошлом месяце."
            }${
              age.age_days === null
                ? ""
                : ` Возраст денег: ${dayWord(age.age_days)}.`
            }`,
    },
  ]
}
