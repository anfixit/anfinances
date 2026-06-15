import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import type { Account } from "@/features/accounts/types"
import { useCategories } from "@/features/categories/hooks"
import {
  useCreateTransaction,
  useCreateTransfer,
} from "@/features/transactions/hooks"
import {
  ordinaryTxSchema,
  transferTxSchema,
} from "@/features/transactions/schemas"
import { AppError } from "@/lib/api/errors"

type Mode = "expense" | "income" | "transfer"

// datetime-local в текущей таймзоне (YYYY-MM-DDTHH:mm).
function nowLocalInput(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

const blank = () => ""

export function TransactionSheet({ onDone }: { onDone: () => void }) {
  const accountsQ = useAccounts()
  const categoriesQ = useCategories()
  const createTx = useCreateTransaction()
  const createTransfer = useCreateTransfer()

  const [mode, setMode] = useState<Mode>("expense")
  const [date, setDate] = useState<string>(() => nowLocalInput())
  const [comment, setComment] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  // Обычная операция
  const [accountId, setAccountId] = useState("")
  const [amount, setAmount] = useState("")
  const [categoryId, setCategoryId] = useState("")
  const [required, setRequired] = useState("")

  // Перевод
  const [fromId, setFromId] = useState("")
  const [toId, setToId] = useState("")
  const [amountFrom, setAmountFrom] = useState("")
  const [amountTo, setAmountTo] = useState("")
  const [feeAmount, setFeeAmount] = useState("")
  const [feeCategory, setFeeCategory] = useState("")

  if (accountsQ.isPending || categoriesQ.isPending) {
    return <p>Загрузка…</p>
  }
  if (!accountsQ.data || !categoriesQ.data) {
    return <p className="error">Не удалось загрузить счета и категории</p>
  }

  const accounts: Account[] = accountsQ.data
  const categories = categoriesQ.data
  const accById = new Map(accounts.map((a) => [a.id, a]))

  const expenseCats = categories.filter((c) => c.kind === "expense")
  const incomeCats = categories.filter((c) => c.kind === "income")
  const ordinaryCats = mode === "income" ? incomeCats : expenseCats

  const fromAcc = accById.get(fromId)
  const toAcc = accById.get(toId)
  const sameCurrency =
    fromAcc !== undefined &&
    toAcc !== undefined &&
    fromAcc.currency_code === toAcc.currency_code
  const needsConversion =
    fromAcc !== undefined && toAcc !== undefined && !sameCurrency

  const pending = createTx.isPending || createTransfer.isPending

  const onError = (err: unknown) => {
    setFormError(err instanceof AppError ? err.message : "Ошибка сохранения")
  }

  const submitOrdinary = () => {
    const parsed = ordinaryTxSchema.safeParse({
      account_id: accountId,
      amount,
      date,
      category_id: categoryId || null,
      required: mode === "expense" && required ? required : null,
      comment: comment || null,
    })
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }
    createTx.mutate(
      {
        account_id: accountId,
        kind: mode === "income" ? "income" : "expense",
        amount: amount.trim(),
        date: new Date(date).toISOString(),
        category_id: categoryId || null,
        required: mode === "expense" && required ? (required as never) : null,
        comment: comment || null,
      },
      { onSuccess: onDone, onError },
    )
  }

  const submitTransfer = () => {
    const effectiveTo = sameCurrency ? amountFrom : amountTo
    const parsed = transferTxSchema.safeParse({
      from_account_id: fromId,
      to_account_id: toId,
      amount_from: amountFrom,
      amount_to: effectiveTo,
      date,
      fee_amount: feeAmount || null,
      fee_category_id: feeCategory || null,
      comment: comment || null,
    })
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }
    createTransfer.mutate(
      {
        from_account_id: fromId,
        to_account_id: toId,
        amount_from: amountFrom.trim(),
        amount_to: effectiveTo.trim(),
        date: new Date(date).toISOString(),
        comment: comment || null,
        fee_amount: feeAmount || null,
        fee_category_id: feeAmount ? feeCategory || null : null,
      },
      { onSuccess: onDone, onError },
    )
  }

  const submit = () => {
    setFormError(null)
    if (mode === "transfer") {
      submitTransfer()
    } else {
      submitOrdinary()
    }
  }

  return (
    <div className="form">
      <div className="segmented" role="group" aria-label="Тип операции">
        <button
          type="button"
          aria-pressed={mode === "expense"}
          onClick={() => setMode("expense")}
        >
          Расход
        </button>
        <button
          type="button"
          aria-pressed={mode === "income"}
          onClick={() => setMode("income")}
        >
          Доход
        </button>
        <button
          type="button"
          aria-pressed={mode === "transfer"}
          onClick={() => setMode("transfer")}
        >
          Перевод
        </button>
      </div>

      {mode !== "transfer" && (
        <>
          <label className="field">
            <span>Счёт</span>
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">— выберите —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency_code})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Сумма</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Категория</span>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              <option value="">— без категории —</option>
              {ordinaryCats.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          {mode === "expense" && (
            <label className="field">
              <span>Обязательность</span>
              <select
                value={required}
                onChange={(e) => setRequired(e.target.value)}
              >
                <option value="">— не указано —</option>
                <option value="required">Обязательный</option>
                <option value="optional">Необязательный</option>
              </select>
            </label>
          )}
        </>
      )}

      {mode === "transfer" && (
        <>
          <label className="field">
            <span>Со счёта</span>
            <select value={fromId} onChange={(e) => setFromId(e.target.value)}>
              <option value="">— выберите —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency_code})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>На счёт</span>
            <select value={toId} onChange={(e) => setToId(e.target.value)}>
              <option value="">— выберите —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency_code})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>
              Списано{fromAcc ? ` (${fromAcc.currency_code})` : ""}
            </span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={amountFrom}
              onChange={(e) => setAmountFrom(e.target.value)}
            />
          </label>
          {needsConversion && (
            <label className="field">
              <span>Получено ({toAcc?.currency_code})</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                value={amountTo}
                onChange={(e) => setAmountTo(e.target.value)}
              />
            </label>
          )}
          <label className="field">
            <span>Комиссия (необязательно)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={feeAmount}
              onChange={(e) => setFeeAmount(e.target.value)}
            />
          </label>
          {feeAmount && (
            <label className="field">
              <span>Категория комиссии</span>
              <select
                value={feeCategory}
                onChange={(e) => setFeeCategory(e.target.value)}
              >
                <option value="">— без категории —</option>
                {expenseCats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}

      <label className="field">
        <span>Дата и время</span>
        <input
          type="datetime-local"
          value={date}
          onChange={(e) => setDate(e.target.value || blank())}
        />
      </label>

      <label className="field">
        <span>Комментарий</span>
        <input value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>

      {formError && <p className="error">{formError}</p>}

      <button type="button" onClick={submit} disabled={pending}>
        {pending ? "Сохраняю…" : "Сохранить"}
      </button>
    </div>
  )
}
