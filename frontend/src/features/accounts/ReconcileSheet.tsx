import { useState } from "react"

import { useCategories } from "@/features/categories/hooks"
import {
  usePreviewReconciliation,
  useReconcile,
  useReconciliations,
} from "@/features/accounts/reconcileHooks"
import type { ReconciliationPreview } from "@/features/accounts/reconcileApi"
import type { Account } from "@/features/accounts/types"
import { AppError } from "@/lib/api/errors"
import { formatMoney } from "@/lib/money"

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Конец дня: выписка за 21-е включает всё, что было 21-го. */
function endOfDay(date: string): string {
  return new Date(`${date}T23:59:59`).toISOString()
}

export function ReconcileSheet({
  account,
  onDone,
}: {
  account: Account
  onDone: () => void
}) {
  const [balance, setBalance] = useState("")
  const [date, setDate] = useState(today())
  const [category, setCategory] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [seen, setSeen] = useState<ReconciliationPreview | null>(null)

  const preview = usePreviewReconciliation()
  const apply = useReconcile()
  const history = useReconciliations(account.id)
  const categories = useCategories()

  const onError = (e: unknown) => {
    setError(e instanceof AppError ? e.message : "Не получилось")
  }

  const check = () => {
    setError(null)
    preview.mutate(
      {
        accountId: account.id,
        input: {
          statement_balance: balance.trim(),
          date: endOfDay(date),
        },
      },
      { onSuccess: setSeen, onError },
    )
  }

  const finish = (adjust: boolean) => {
    setError(null)
    apply.mutate(
      {
        accountId: account.id,
        input: {
          statement_balance: balance.trim(),
          date: endOfDay(date),
          adjust,
          adjustment_category_id: adjust ? category || null : null,
        },
      },
      { onSuccess: onDone, onError },
    )
  }

  const difference = seen === null ? null : Number(seen.difference)
  const matches = difference !== null && difference === 0

  return (
    <div className="form">
      <p className="hint">
        Введите остаток, который показывает банк на конец дня.
        Расхождение — это задвоенная, пропавшая или не туда записанная
        операция; сначала стоит найти её, а не закрывать корректировкой.
      </p>

      <label className="field">
        <span>Остаток по банку, {account.currency_code}</span>
        <input
          inputMode="decimal"
          value={balance}
          placeholder="0.00"
          onChange={(e) => {
            setBalance(e.target.value)
            setSeen(null)
          }}
        />
      </label>

      <label className="field">
        <span>На дату</span>
        <input
          type="date"
          value={date}
          onChange={(e) => {
            setDate(e.target.value || today())
            setSeen(null)
          }}
        />
      </label>

      {seen !== null && (
        <div className="card card--inset recon-result">
          <div className="acc-row">
            <span className="acc-name">Записано в anfinances</span>
            <span className="num">
              {formatMoney(seen.computed_balance, account.currency_code)}
            </span>
          </div>
          <div className="acc-row">
            <span className="acc-name">Показывает банк</span>
            <span className="num">
              {formatMoney(seen.statement_balance, account.currency_code)}
            </span>
          </div>
          <div className="acc-row">
            <span className="acc-name">
              <strong>Расхождение</strong>
            </span>
            <span className={matches ? "num income" : "num expense"}>
              {formatMoney(seen.difference, account.currency_code)}
            </span>
          </div>
          <p className="allowance-note">
            {matches
              ? `Сходится. Под отметку сверки попадёт операций: ${String(seen.unreconciled_count)}.`
              : difference !== null && difference > 0
                ? "В банке больше, чем записано: не хватает дохода или записан лишний расход."
                : "В банке меньше, чем записано: не хватает траты или доход записан дважды."}
          </p>
        </div>
      )}

      {seen !== null && !matches && (
        <label className="field">
          <span>Категория корректировки</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Без категории</option>
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {error !== null && <p className="error">{error}</p>}

      <div className="transaction-submit">
        {seen === null ? (
          <button
            type="button"
            onClick={check}
            disabled={balance.trim() === "" || preview.isPending}
          >
            Сверить
          </button>
        ) : matches ? (
          <button
            type="button"
            onClick={() => finish(false)}
            disabled={apply.isPending}
          >
            Отметить сверенным
          </button>
        ) : (
          <button
            type="button"
            className="btn-danger"
            onClick={() => finish(true)}
            disabled={apply.isPending}
          >
            Закрыть корректировкой
          </button>
        )}
        <button type="button" className="link" onClick={onDone}>
          Закрыть
        </button>
      </div>

      {history.data && history.data.length > 0 && (
        <>
          <h3>Прошлые сверки</h3>
          <table className="data-table">
            <tbody>
              {history.data.slice(0, 8).map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.date).toLocaleDateString("ru-RU")}</td>
                  <td className="num">
                    {formatMoney(
                      r.statement_balance,
                      account.currency_code,
                    )}
                  </td>
                  <td className="num data-share">
                    {r.adjustment_transaction_id === null
                      ? "сошлось"
                      : "с корректировкой"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
