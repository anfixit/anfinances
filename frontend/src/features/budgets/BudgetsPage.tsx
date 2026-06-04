import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

import { useCategories } from "@/features/categories/hooks"
import { listBudgets } from "@/features/budgets/budgetsApi"
import { BudgetForm } from "@/features/budgets/BudgetForm"
import {
  useBudgets,
  useDeleteBudget,
  useImportBudgets,
} from "@/features/budgets/hooks"
import type { Budget } from "@/features/budgets/types"
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

interface SheetState {
  categoryId: string
  categoryName: string
  budget: Budget | null
}

export function BudgetsPage() {
  const qc = useQueryClient()
  const [month, setMonth] = useState<string>(() => currentMonth())
  const [sheet, setSheet] = useState<SheetState | null>(null)

  const categoriesQ = useCategories()
  const budgetsQ = useBudgets(month)
  const del = useDeleteBudget()
  const importMut = useImportBudgets()

  const budgets = budgetsQ.data ?? []
  const byCat = new Map(budgets.map((b) => [b.category_id, b]))

  const expenseCats = (categoriesQ.data ?? [])
    .filter((c) => c.kind === "expense")
    .sort((a, b) => a.name.localeCompare(b.name, "ru"))

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
      {expenseCats.length === 0 && categoriesQ.isSuccess && (
        <p>Нет расходных категорий. Создайте их в разделе «Категории».</p>
      )}

      <ul className="budget-list">
        {expenseCats.map((cat) => {
          const b = byCat.get(cat.id)
          if (!b) {
            return (
              <li key={cat.id} className="budget-row budget-row--empty">
                <span className="budget-name">{cat.name}</span>
                <span className="budget-hint">лимит не задан</span>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    setSheet({
                      categoryId: cat.id,
                      categoryName: cat.name,
                      budget: null,
                    })
                  }
                >
                  Задать лимит
                </button>
              </li>
            )
          }
          const available = Number(b.available)
          const spent = Number(b.spent)
          const over = Number(b.remaining) < 0
          const pct =
            available > 0
              ? Math.min(100, (spent / available) * 100)
              : spent > 0
                ? 100
                : 0
          return (
            <li key={cat.id} className="budget-row">
              <div className="budget-head">
                <span className="budget-name">{cat.name}</span>
                <span className="num budget-figures">
                  {formatMoney(b.spent, "RUB")} / {formatMoney(b.available, "RUB")}
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
                  {formatMoney(b.remaining, "RUB")}
                </span>
                {b.rollover && (
                  <span className="chip-static">
                    перенос {formatMoney(b.rollover_amount, "RUB")}
                  </span>
                )}
                <span className="spacer" />
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    setSheet({
                      categoryId: cat.id,
                      categoryName: cat.name,
                      budget: b,
                    })
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
