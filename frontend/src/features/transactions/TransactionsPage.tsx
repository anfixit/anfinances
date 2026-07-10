import { useState } from "react"

import { Sheet } from "@/components/Sheet"
import { useAccounts } from "@/features/accounts/hooks"
import type { Account } from "@/features/accounts/types"
import { useCategories } from "@/features/categories/hooks"
import { categoryPath, CATEGORY_PATH_SEP } from "@/features/categories/path"
import type { Category } from "@/features/categories/types"
import { compareCategoriesByName } from "@/features/categories/sort"
import { TransactionSheet } from "@/features/transactions/TransactionSheet"
import {
  useDeleteTransaction,
  useDeleteTransfer,
  useTransactions,
  useTransfer,
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

const DELETED_ACCOUNT_LABEL = "Удалённый счёт"
const UNCATEGORIZED_LABEL = "Без категории"

function snapshotCategoryPath(transaction: Transaction): string | null {
  if (transaction.category_name_snapshot === null) {
    return null
  }
  if (transaction.subcategory_name_snapshot === null) {
    return transaction.category_name_snapshot
  }
  return [
    transaction.category_name_snapshot,
    transaction.subcategory_name_snapshot,
  ].join(CATEGORY_PATH_SEP)
}

function transactionCategoryLabel(
  transaction: Transaction,
  categoryById: ReadonlyMap<string, Category>,
): string {
  if (transaction.kind === "transfer") {
    return "Перевод"
  }
  return (
    snapshotCategoryPath(transaction) ??
    categoryPath(categoryById, transaction.category_id) ??
    UNCATEGORIZED_LABEL
  )
}

function accountName(
  transaction: Transaction,
  accountById: ReadonlyMap<string, Account>,
): string {
  return (
    transaction.account_name_snapshot ??
    accountById.get(transaction.account_id)?.name ??
    DELETED_ACCOUNT_LABEL
  )
}

function otherTransferAccountName(
  transaction: Transaction,
  rows: readonly Transaction[],
  accountById: ReadonlyMap<string, Account>,
): string | null {
  if (transaction.transfer_id === null) {
    return null
  }
  if (transaction.to_account_name_snapshot !== null) {
    return transaction.to_account_name_snapshot
  }

  const otherLeg = rows.find(
    (row) =>
      row.transfer_id === transaction.transfer_id &&
      row.id !== transaction.id &&
      row.kind === "transfer",
  )
  if (otherLeg === undefined) {
    return null
  }
  return accountName(otherLeg, accountById)
}

function accountLine(
  transaction: Transaction,
  rows: readonly Transaction[],
  accountById: ReadonlyMap<string, Account>,
): string {
  const current = accountName(transaction, accountById)
  const other = otherTransferAccountName(transaction, rows, accountById)
  if (transaction.kind !== "transfer" || other === null) {
    return current
  }
  if (Number(transaction.amount) < 0) {
    return `${current} → ${other}`
  }
  return `${other} → ${current}`
}

export function TransactionsPage() {
  const [filters, setFilters] = useState<TransactionFilters>({})
  const [kindTab, setKindTab] = useState<TransactionKind | "all">("all")
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editingTx, setEditingTx] = useState<Transaction | null>(null)
  const [editingTransferId, setEditingTransferId] = useState<string | null>(
    null,
  )

  const accountsQ = useAccounts()
  const categoriesQ = useCategories()
  const list = useTransactions(filters)
  const delTx = useDeleteTransaction()
  const delTransfer = useDeleteTransfer()
  const transferQ = useTransfer(editingTransferId)

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

  const patchFilter = (
    key: Exclude<keyof TransactionFilters, "kind">,
    value: string,
  ) => {
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

  const openCreate = () => {
    setEditingTx(null)
    setEditingTransferId(null)
    setSheetOpen(true)
  }

  const openEdit = (transaction: Transaction) => {
    setEditingTransferId(null)
    setEditingTx(transaction)
    setSheetOpen(true)
  }

  const openTransferEdit = (transferId: string) => {
    setEditingTx(null)
    setEditingTransferId(transferId)
    setSheetOpen(true)
  }

  const closeSheet = () => {
    setSheetOpen(false)
    setEditingTx(null)
    setEditingTransferId(null)
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

  // Категории фильтра: родители верхнего уровня с вложенными
  // подкатегориями. Сам родитель тоже выбираем (его прямые операции).
  const allCats = categoriesQ.data ?? []
  const filterParents = allCats
    .filter((c) => c.parent_id === null)
    .sort(compareCategoriesByName)

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
              onChange={(e) => patchFilter("date_from", e.target.value)}
            />
          </label>
          <label className="field">
            <span>По дату</span>
            <input
              type="date"
              onChange={(e) => patchFilter("date_to", e.target.value)}
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
              {filterParents.map((p) => {
                const children = allCats
                  .filter((c) => c.parent_id === p.id)
                  .sort(compareCategoriesByName)
                if (children.length === 0) {
                  return (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  )
                }
                return (
                  <optgroup key={p.id} label={p.name}>
                    <option value={p.id}>{p.name} — вся категория</option>
                    {children.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </optgroup>
                )
              })}
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
          const label = transactionCategoryLabel(t, catById)
          const account = accountLine(t, rows, accById)
          const editableTransferId =
            t.kind === "transfer" && Number(t.amount) < 0
              ? t.transfer_id
              : null
          return (
            <li key={t.id} className="tx-row">
              <div className="tx-main">
                <span className="tx-label">{label}</span>
                <span className="tx-sub">
                  {account} · {formatDate(t.date)}
                </span>
                {t.comment && <span className="tx-comment">{t.comment}</span>}
              </div>
              <span className={`amount ${isIncome ? "income" : "expense"}`}>
                {formatMoney(t.amount, t.currency_code)}
              </span>
              <div className="tx-actions">
                {!t.transfer_id && (
                  <>
                    <button
                      type="button"
                      className="link"
                      onClick={() => openEdit(t)}
                    >
                      Изменить
                    </button>
                    <button
                      type="button"
                      className="link danger"
                      onClick={() => remove(t)}
                    >
                      Удалить
                    </button>
                  </>
                )}
                {editableTransferId && (
                  <>
                    <button
                      type="button"
                      className="link"
                      onClick={() => openTransferEdit(editableTransferId)}
                    >
                      Изменить перевод
                    </button>
                    <button
                      type="button"
                      className="link danger"
                      onClick={() => remove(t)}
                    >
                      Удалить
                    </button>
                  </>
                )}
              </div>
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

      <button type="button" className="fab" onClick={openCreate}>
        + Добавить
      </button>

      <Sheet
        open={sheetOpen}
        title={
          editingTransferId
            ? "Редактирование перевода"
            : editingTx
              ? "Редактирование операции"
              : "Новая операция"
        }
        onClose={closeSheet}
      >
        {editingTransferId && transferQ.isPending && <p>Загрузка…</p>}
        {editingTransferId && transferQ.isError && (
          <p className="error">Не удалось загрузить перевод</p>
        )}
        {(!editingTransferId || transferQ.data) && (
          <TransactionSheet
            key={editingTransferId ?? editingTx?.id ?? "new"}
            onDone={closeSheet}
            {...(editingTx ? { transaction: editingTx } : {})}
            {...(transferQ.data ? { transfer: transferQ.data } : {})}
          />
        )}
      </Sheet>
    </>
  )
}
