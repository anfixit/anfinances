import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import { useCategories } from "@/features/categories/hooks"
import { Sheet } from "@/components/Sheet"
import { TransactionSheet } from "@/features/transactions/TransactionSheet"
import {
  useDeleteTransaction,
  useDeleteTransfer,
  useTransactions,
} from "@/features/transactions/hooks"
import type {
  Transaction,
  TransactionFilters,
} from "@/features/transactions/types"
import { formatDate } from "@/lib/datetime"
import { formatMoney } from "@/lib/money"
import type { TransactionKind } from "@/types/enums"

const KIND_TABS: { value: TransactionKind | "all"; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "expense", label: "Расходы" },
  { value: "income", label: "Доходы" },
  { value: "transfer", label: "Переводы" },
]

export function TransactionsPage() {
  const [filters, setFilters] = useState<TransactionFilters>({})
  const [kindTab, setKindTab] = useState<TransactionKind | "all">("all")
  const [sheetOpen, setSheetOpen] = useState(false)

  const accountsQ = useAccounts()
  const categoriesQ = useCategories()
  const list = useTransactions(filters)
  const delTx = useDeleteTransaction()
  const delTransfer = useDeleteTransfer()

  const accById = new Map((accountsQ.data ?? []).map((a) => [a.id, a]))
  const catById = new Map((categoriesQ.data ?? []).map((c) => [c.id, c]))

  const setKind = (value: TransactionKind | "all") => {
    setKindTab(value)
    setFilters((f) => {
      const next = { ...f }
      if (value === "all") {
        delete next.kind
      } else {
        next.kind = value
      }
      return next
    })
  }

  const patchFilter = (key: keyof TransactionFilters, value: string) => {
    setFilters((f) => {
      const next = { ...f }
      if (value) {
        next[key] = value
      } else {
        delete next[key]
      }
      return next
    })
  }

  const remove = (t: Transaction) => {
    if (t.transfer_id) {
      if (window.confirm("Удалить перевод целиком?")) {
        delTransfer.mutate(t.transfer_id)
      }
      return
    }
    if (window.confirm("Удалить операцию?")) {
      delTx.mutate(t.id)
    }
  }

  const rows = list.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <h1>Операции</h1>

      <div className="card filters">
        <div className="segmented" role="group" aria-label="Тип">
          {KIND_TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              aria-pressed={kindTab === t.value}
              onClick={() => setKind(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="filters-row">
          <label className="field">
            <span>С даты</span>
            <input
              type="date"
              onChange={(e) =>
                patchFilter(
                  "date_from",
                  e.target.value
                    ? new Date(e.target.value).toISOString()
                    : "",
                )
              }
            />
          </label>
          <label className="field">
            <span>По дату</span>
            <input
              type="date"
              onChange={(e) =>
                patchFilter(
                  "date_to",
                  e.target.value
                    ? new Date(e.target.value).toISOString()
                    : "",
                )
              }
            />
          </label>
          <label className="field">
            <span>Счёт</span>
            <select
              onChange={(e) => patchFilter("account_id", e.target.value)}
            >
              <option value="">Все</option>
              {(accountsQ.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Категория</span>
            <select
              onChange={(e) => patchFilter("category_id", e.target.value)}
            >
              <option value="">Все</option>
              {(categoriesQ.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {list.isPending && <p>Загрузка…</p>}
      {list.isError && <p className="error">Не удалось загрузить операции</p>}
      {list.isSuccess && rows.length === 0 && <p>Операций пока нет.</p>}

      <ul className="tx-list">
        {rows.map((t) => {
          const isIncome = Number(t.amount) >= 0
          const label =
            t.kind === "transfer"
              ? "Перевод"
              : (t.category_id && catById.get(t.category_id)?.name) ||
                "Без категории"
          const account = accById.get(t.account_id)
          return (
            <li key={t.id} className="tx-row">
              <div className="tx-main">
                <span className="tx-label">{label}</span>
                <span className="tx-sub">
                  {account?.name ?? "—"} · {formatDate(t.date)}
                </span>
                {t.comment && <span className="tx-comment">{t.comment}</span>}
              </div>
              <span className={`amount ${isIncome ? "income" : "expense"}`}>
                {formatMoney(t.amount, t.currency_code)}
              </span>
              <button
                type="button"
                className="link danger"
                onClick={() => remove(t)}
              >
                Удалить
              </button>
            </li>
          )
        })}
      </ul>

      {list.hasNextPage && (
        <p>
          <button
            type="button"
            className="btn-tonal"
            onClick={() => void list.fetchNextPage()}
            disabled={list.isFetchingNextPage}
          >
            {list.isFetchingNextPage ? "Загружаю…" : "Загрузить ещё"}
          </button>
        </p>
      )}

      <button type="button" className="fab" onClick={() => setSheetOpen(true)}>
        + Добавить
      </button>

      <Sheet
        open={sheetOpen}
        title="Новая операция"
        onClose={() => setSheetOpen(false)}
      >
        <TransactionSheet onDone={() => setSheetOpen(false)} />
      </Sheet>
    </>
  )
}
