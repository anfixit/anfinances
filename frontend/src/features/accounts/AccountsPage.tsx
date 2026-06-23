import { useState } from "react"

import {
  useAccounts,
  useArchiveAccount,
  useReorderAccounts,
} from "@/features/accounts/hooks"
import { AccountForm } from "@/features/accounts/AccountForm"
import { TYPE_LABELS } from "@/features/accounts/types"
import type { Account } from "@/features/accounts/types"
import { Sheet } from "@/components/Sheet"
import { formatMoney } from "@/lib/money"

export function AccountsPage() {
  const accounts = useAccounts()
  const archive = useArchiveAccount()
  const reorder = useReorderAccounts()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editing, setEditing] = useState<Account | null>(null)

  const openCreate = () => {
    setEditing(null)
    setSheetOpen(true)
  }
  const openEdit = (account: Account) => {
    setEditing(account)
    setSheetOpen(true)
  }
  const close = () => {
    setSheetOpen(false)
  }

  const remove = (account: Account) => {
    if (window.confirm(`Архивировать счёт «${account.name}»?`)) {
      archive.mutate(account.id)
    }
  }

  const move = (index: number, dir: -1 | 1) => {
    const list = [...(accounts.data ?? [])]
    const target = index + dir
    const a = list[index]
    const b = list[target]
    if (!a || !b) {
      return
    }
    list[index] = b
    list[target] = a
    // Пересчитываем sort_order = позиция; шлём только изменившимся.
    const changed = list
      .map((acc, idx) => ({ acc, idx }))
      .filter(({ acc, idx }) => acc.sort_order !== idx)
      .map(({ acc, idx }) => ({ id: acc.id, sort_order: idx }))
    if (changed.length > 0) {
      reorder.mutate(changed)
    }
  }

  const list = accounts.data ?? []

  return (
    <>
      <div className="page-head">
        <h1>Счета</h1>
        <button type="button" onClick={openCreate}>
          + Добавить счёт
        </button>
      </div>

      {accounts.isPending && <p>Загрузка…</p>}
      {accounts.isError && <p className="error">Не удалось загрузить счета</p>}
      {accounts.isSuccess && list.length === 0 && (
        <p>Счетов пока нет. Добавьте первый, чтобы вести операции.</p>
      )}

      <ul className="acc-cards">
        {list.map((a, i) => (
          <li key={a.id} className="acc-card">
            <span className="acc-arrows">
              <button
                type="button"
                className="icon-btn"
                aria-label="Выше"
                disabled={i === 0 || reorder.isPending}
                onClick={() => move(i, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Ниже"
                disabled={i === list.length - 1 || reorder.isPending}
                onClick={() => move(i, 1)}
              >
                ↓
              </button>
            </span>
            <span
              className="color-dot"
              style={{ background: a.color ?? "var(--outline)" }}
            />
            <div className="acc-info">
              <span className="acc-title">{a.name}</span>
              <span className="acc-meta">
                {TYPE_LABELS[a.type]} · {a.currency_code}
                {a.credit_limit
                  ? ` · лимит ${formatMoney(a.credit_limit, a.currency_code)}`
                  : ""}
              </span>
            </div>
            <span className="num acc-balance">
              {formatMoney(a.initial_balance, a.currency_code)}
            </span>
            <button
              type="button"
              className="link"
              onClick={() => openEdit(a)}
            >
              Изменить
            </button>
            <button
              type="button"
              className="link danger"
              onClick={() => remove(a)}
            >
              В архив
            </button>
          </li>
        ))}
      </ul>

      <Sheet
        open={sheetOpen}
        title={editing ? "Редактировать счёт" : "Новый счёт"}
        onClose={close}
      >
        <AccountForm
          key={editing?.id ?? "new"}
          account={editing}
          onDone={close}
        />
      </Sheet>
    </>
  )
}
