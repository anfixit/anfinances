import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

import type { Category } from "@/features/categories/types"
import { useCategories } from "@/features/categories/hooks"
import { listBudgets } from "@/features/budgets/budgetsApi"
import { BudgetForm } from "@/features/budgets/BudgetForm"
import {
  useBudgets,
  useDeleteBudget,
  useImportBudgets,
} from "@/features/budgets/hooks"
import type { Budget } from "@/features/budgets/types"
import { useByCategory } from "@/features/summary/hooks"
import { Sheet } from "@/components/Sheet"
import { queryKeys } from "@/lib/query/keys"
import { formatMoney } from "@/lib/money"

function currentMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function shiftMonth(month: string, delta: number): string {
  const [ys, ms] = month.split("-")
  const d = new Date(Number(ys), Number(ms) - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function monthLabel(month: string): string {
  const [ys, ms] = month.split("-")
  return new Intl.DateTimeFormat("ru-RU", {
    month: "long",
    year: "numeric",
  }).format(new Date(Number(ys), Number(ms) - 1, 1))
}

function rub(value: number): string {
  return formatMoney(String(value), "RUB")
}

interface SheetState {
  categoryId: string
  categoryName: string
  budget: Budget | null
}

export function BudgetsPage() {
  const qc = useQueryClient()
  const [month, setMonth] = useState<string>(() => currentMonth())
  const [sheet, setSheet] = useState<SheetState | null>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const categoriesQ = useCategories()
  const budgetsQ = useBudgets(month)
  const spendingQ = useByCategory(month)
  const del = useDeleteBudget()
  const importMut = useImportBudgets()

  const budgets = budgetsQ.data ?? []
  const byCat = new Map(budgets.map((b) => [b.category_id, b]))
  const spendMap = new Map(
    (spendingQ.data?.items ?? []).map((i) => [i.category_id, Number(i.amount_rub)]),
  )

  const expense = (categoriesQ.data ?? []).filter((c) => c.kind === "expense")
  const byName = (a: Category, b: Category) => a.name.localeCompare(b.name, "ru")
  const parents = expense.filter((c) => c.parent_id === null).sort(byName)
  const childrenOf = (pid: string) =>
    expense.filter((c) => c.parent_id === pid).sort(byName)

  const spentOf = (cat: Category): number => {
    const b = byCat.get(cat.id)
    return b ? Number(b.spent) : (spendMap.get(cat.id) ?? 0)
  }

  const toggle = (id: string) => {
    setOpen((o) => ({ ...o, [id]: !o[id] }))
  }

  const copyPrev = async () => {
    const prev = shiftMonth(month, -1)
    const prevBudgets = await qc.fetchQuery({
      queryKey: queryKeys.budgets(prev),
      queryFn: () => listBudgets(prev),
    })
    if (prevBudgets.length === 0) {
      window.alert("В прошлом месяце бюджета нет.")
      return
    }
    if (
      budgets.length > 0 &&
      !window.confirm("Перезаписать текущий бюджет значениями прошлого месяца?")
    ) {
      return
    }
    importMut.mutate({
      month,
      items: prevBudgets.map((b) => ({
        category_id: b.category_id,
        planned: b.planned,
        notes: b.notes,
        rollover: b.rollover,
      })),
    })
  }

  const removeBudget = (b: Budget, name: string) => {
    if (window.confirm(`Удалить лимит по категории «${name}»?`)) {
      del.mutate(b.id)
    }
  }

  const renderRow = (cat: Category, label: string, indent: boolean) => {
    const b = byCat.get(cat.id)
    const cls = `budget-row${indent ? " indent" : ""}`
    if (!b) {
      const spent = spendMap.get(cat.id) ?? 0
      return (
        <div className={`${cls} budget-row--empty`} key={cat.id}>
          <span className="budget-name">{label}</span>
          <span className="budget-hint">
            {spent > 0 ? `потрачено ${rub(spent)}` : "лимит не задан"}
          </span>
          <button
            type="button"
            className="link"
            onClick={() =>
              setSheet({ categoryId: cat.id, categoryName: cat.name, budget: null })
            }
          >
            Задать лимит
          </button>
        </div>
      )
    }
    const available = Number(b.available)
    const spent = Number(b.spent)
    const over = Number(b.remaining) < 0
    const pct =
      available > 0 ? Math.min(100, (spent / available) * 100) : spent > 0 ? 100 : 0
    return (
      <div className={cls} key={cat.id}>
        <div className="budget-head">
          <span className="budget-name">{label}</span>
          <span className="num budget-figures">
            {rub(spent)} / {rub(available)}
          </span>
        </div>
        <div className="bar">
          <div
            className="bar-fill"
            style={{
              width: `${String(pct)}%`,
              background: over ? "var(--expense)" : "var(--income)",
            }}
          />
        </div>
        <div className="budget-foot">
          <span className={`num ${over ? "expense" : ""}`}>
            {over ? "перерасход " : "остаток "}
            {rub(Number(b.remaining))}
          </span>
          {b.rollover && (
            <span className="chip-static">перенос {rub(Number(b.rollover_amount))}</span>
          )}
          <span className="spacer" />
          <button
            type="button"
            className="link"
            onClick={() =>
              setSheet({ categoryId: cat.id, categoryName: cat.name, budget: b })
            }
          >
            Изменить
          </button>
          <button
            type="button"
            className="link danger"
            onClick={() => removeBudget(b, cat.name)}
          >
            Удалить
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      <h1>Бюджет</h1>

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

      <p>
        <button
          type="button"
          className="btn-outline"
          onClick={() => void copyPrev()}
          disabled={importMut.isPending}
        >
          {importMut.isPending ? "Копирую…" : "Скопировать из прошлого месяца"}
        </button>
      </p>

      {(categoriesQ.isPending || budgetsQ.isPending) && <p>Загрузка…</p>}
      {parents.length === 0 && categoriesQ.isSuccess && (
        <p>Нет расходных категорий. Создайте их в разделе «Категории».</p>
      )}

      <ul className="budget-list">
        {parents.map((parent) => {
          const kids = childrenOf(parent.id)

          // Лист без подкатегорий — обычная строка.
          if (kids.length === 0) {
            return (
              <li key={parent.id} className="budget-leaf">
                {renderRow(parent, parent.name, false)}
              </li>
            )
          }

          // Группа: итог по родителю + детям.
          const groupCats = [parent, ...kids]
          let avail = 0
          let spentTotal = 0
          for (const c of groupCats) {
            const b = byCat.get(c.id)
            if (b) {
              avail += Number(b.available)
            }
            spentTotal += spentOf(c)
          }
          const over = avail > 0 && spentTotal > avail
          const pct =
            avail > 0
              ? Math.min(100, (spentTotal / avail) * 100)
              : spentTotal > 0
                ? 100
                : 0
          const isOpen = open[parent.id] ?? false

          return (
            <li key={parent.id} className="budget-group">
              <button
                type="button"
                className="group-head"
                onClick={() => toggle(parent.id)}
                aria-expanded={isOpen}
              >
                <span className="group-caret">{isOpen ? "▾" : "▸"}</span>
                <span className="group-name">{parent.name}</span>
                <span className="num group-figures">
                  {rub(spentTotal)} / {rub(avail)}
                </span>
              </button>
              <div className="bar group-bar">
                <div
                  className="bar-fill"
                  style={{
                    width: `${String(pct)}%`,
                    background: over ? "var(--expense)" : "var(--income)",
                  }}
                />
              </div>
              {isOpen && (
                <div className="group-children">
                  {renderRow(parent, "Общий лимит (без подкатегории)", true)}
                  {kids.map((c) => renderRow(c, c.name, true))}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <Sheet
        open={sheet !== null}
        title={sheet?.budget ? "Изменить лимит" : "Новый лимит"}
        onClose={() => setSheet(null)}
      >
        {sheet && (
          <BudgetForm
            key={`${sheet.categoryId}-${sheet.budget?.id ?? "new"}`}
            month={month}
            categoryId={sheet.categoryId}
            categoryName={sheet.categoryName}
            budget={sheet.budget}
            onDone={() => setSheet(null)}
          />
        )}
      </Sheet>
    </>
  )
}
