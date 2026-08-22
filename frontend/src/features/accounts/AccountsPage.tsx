import { useState } from "react"

import {
  useAccounts,
  useArchiveAccount,
  useReorderAccounts,
} from "@/features/accounts/hooks"
import { AccountForm } from "@/features/accounts/AccountForm"
import { ReconcileSheet } from "@/features/accounts/ReconcileSheet"
import { TYPE_LABELS } from "@/features/accounts/types"
import type { Account } from "@/features/accounts/types"
import { Sheet } from "@/components/Sheet"
import { useConfirm } from "@/components/confirm-context"
import { formatMoney } from "@/lib/money"
import { useDashboard } from "@/features/summary/hooks"

export function AccountsPage() {
  const { confirm } = useConfirm()
  const accounts = useAccounts()
  const archive = useArchiveAccount()
  const reorder = useReorderAccounts()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [reconciling, setReconciling] = useState<Account | null>(null)
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

  // Архивный счёт выпадает из капитала. Пустой уходит молча, а с
  // остатком — только после того, как показали, на сколько изменится
  // итог: тихая правка капитала обнаруживается через неделю.
  const remove = async (account: Account) => {
    const balance = Number(account.current_balance)
    if (balance === 0) {
      const ok = await confirm({
        title: `Архивировать счёт «${account.name}»?`,
        body: [
          "Счёт пропадёт из списков и выбора при вводе операции. " +
            "Прошлые операции по нему останутся, вернуть счёт можно " +
            "в любой момент.",
        ],
        confirmLabel: "Архивировать",
      })
      if (ok) {
        archive.mutate({ id: account.id })
      }
      return
    }
    const shown = formatMoney(account.current_balance, account.currency_code)
    const ok = await confirm({
      title: `На счёте «${account.name}» остаток ${shown}`,
      body: [
        "Архивный счёт не входит в капитал — итог уменьшится на эту " +
          "сумму, будто денег не было.",
        "Обычно остаток сначала переводят на другой счёт, и только " +
          "пустой счёт убирают.",
      ],
      confirmLabel: "Всё равно архивировать",
      danger: true,
    })
    if (ok) {
      archive.mutate({ id: account.id, force: true })
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

  // Рублёвую оценку валютных счетов считает сервер — здесь только
  // складываем. Курса может не быть, и тогда честнее сказать, что
  // итог неполный, чем молча его занизить.
  const dash = useDashboard()
  const rubById = new Map(
    (dash.data?.accounts ?? []).map((a) => [a.account_id, a.balance_rub]),
  )
  const withoutRate = list.filter((a) => rubById.get(a.id) == null)
  const totalRub = list.reduce(
    (sum, a) => sum + Number(rubById.get(a.id) ?? 0),
    0,
  )

  return (
    <>
      <div className="page-head">
        <h1>Счета</h1>
        <button type="button" onClick={openCreate}>
          + Добавить счёт
        </button>
      </div>

      {list.length > 0 && dash.data && (
        <div className="card acc-total">
          <span>Всего на счетах:</span>
          <span className="num">{formatMoney(String(totalRub), "RUB")}</span>
          {withoutRate.length > 0 && (
            <span className="acc-total-note">
              Без учёта {withoutRate.map((a) => a.name).join(", ")} — нет
              курса валюты.
            </span>
          )}
        </div>
      )}

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
              {formatMoney(a.current_balance, a.currency_code)}
            </span>
            <span className="acc-actions">
              <button
                type="button"
                className="link"
                onClick={() => {
                  setReconciling(a)
                }}
              >
                Сверить
              </button>
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
                onClick={() => {
                  void remove(a)
                }}
              >
                В архив
              </button>
            </span>
          </li>
        ))}
      </ul>

      <Sheet
        open={reconciling !== null}
        title={`Сверка: ${reconciling?.name ?? ""}`}
        onClose={() => {
          setReconciling(null)
        }}
      >
        {reconciling !== null && (
          <ReconcileSheet
            key={reconciling.id}
            account={reconciling}
            onDone={() => {
              setReconciling(null)
            }}
          />
        )}
      </Sheet>

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
