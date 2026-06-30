import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import type { Account } from "@/features/accounts/types"
import { CategorySelect } from "@/features/categories/CategorySelect"
import { useCategories } from "@/features/categories/hooks"
import {
  useCreateTransaction,
  useCreateTransfer,
  useUpdateTransaction,
} from "@/features/transactions/hooks"
import {
  ordinaryTxSchema,
  transferTxSchema,
} from "@/features/transactions/schemas"
import type { Transaction } from "@/features/transactions/types"
import { AppError } from "@/lib/api/errors"

type Mode = "expense" | "income" | "transfer"

// datetime-local в текущей таймзоне (YYYY-MM-DDTHH:mm).
function toLocalInput(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value)
  const local = new Date(
    date.getTime() - date.getTimezoneOffset() * 60_000,
  )
  return local.toISOString().slice(0, 16)
}

function nowLocalInput(): string {
  return toLocalInput(new Date())
}

const blank = () => ""

interface TransactionSheetProps {
  onDone: () => void
  transaction?: Transaction
}

export function TransactionSheet({
  onDone,
  transaction,
}: TransactionSheetProps) {
  const accountsQ = useAccounts()
  const categoriesQ = useCategories()
  const createTx = useCreateTransaction()
  const createTransfer = useCreateTransfer()
  const updateTx = useUpdateTransaction()
  const editing = transaction !== undefined

  const [mode, setMode] = useState<Mode>(() =>
    transaction?.kind === "income" ? "income" : "expense",
  )
  const [date, setDate] = useState<string>(() =>
    transaction ? toLocalInput(transaction.date) : nowLocalInput(),
  )
  const [comment, setComment] = useState(transaction?.comment ?? "")
  const [formError, setFormError] = useState<string | null>(null)

  // Обычная операция
  const [accountId, setAccountId] = useState(
    transaction?.account_id ?? "",
  )
  const [amount, setAmount] = useState(() => {
    if (!transaction) {
      return ""
    }
    return transaction.amount.startsWith("-")
      ? transaction.amount.slice(1)
      : transaction.amount
  })
  const [categoryId, setCategoryId] = useState(
    transaction?.category_id ?? "",
  )
  const [required, setRequired] = useState(
    transaction?.required ?? "",
  )

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

  // Тип категории для обычной операции: расход или доход.
  const ordinaryKind = mode === "income" ? "income" : "expense"

  const fromAcc = accById.get(fromId)
  const toAcc = accById.get(toId)
  const sameCurrency =
    fromAcc !== undefined &&
    toAcc !== undefined &&
    fromAcc.currency_code === toAcc.currency_code
  const needsConversion =
    fromAcc !== undefined && toAcc !== undefined && !sameCurrency

  const pending =
    createTx.isPending || createTransfer.isPending || updateTx.isPending

  const onError = (err: unknown) => {
    setFormError(err instanceof AppError ? err.message : "Ошибка сохранения")
  }

  // Смена типа операции: категория расхода и дохода — разные
  // деревья, поэтому при переключении сбрасываем выбор.
  const changeMode = (next: Mode) => {
    if (editing) {
      return
    }
    setMode(next)
    setCategoryId("")
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
    if (transaction) {
      updateTx.mutate(
        {
          id: transaction.id,
          input: {
            amount: amount.trim(),
            date: new Date(date).toISOString(),
            category_id: categoryId || null,
            required:
              mode === "expense" && required
                ? (required as never)
                : null,
            comment: comment || null,
          },
        },
        { onSuccess: onDone, onError },
      )
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
    <div className="form transaction-form">
      {!editing && (
        <div className="segmented" role="group" aria-label="Тип операции">
          <button
            type="button"
            aria-pressed={mode === "expense"}
            onClick={() => changeMode("expense")}
          >
            Расход
          </button>
          <button
            type="button"
            aria-pressed={mode === "income"}
            onClick={() => changeMode("income")}
          >
            Доход
          </button>
          <button
            type="button"
            aria-pressed={mode === "transfer"}
            onClick={() => changeMode("transfer")}
          >
            Перевод
          </button>
        </div>
      )}

      {editing && (
        <p className="form-note">
          Тип операции и счёт нельзя изменить. Для переноса на другой
          счёт удалите операцию и создайте новую.
        </p>
      )}

      {mode !== "transfer" && (
        <>
          <label className="field">
            <span>Счёт</span>
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              disabled={editing}
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
          <CategorySelect
            categories={categories}
            kind={ordinaryKind}
            value={categoryId}
            onChange={setCategoryId}
            emptyLabel="— без категории —"
          />
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
            <CategorySelect
              categories={categories}
              kind="expense"
              value={feeCategory}
              onChange={setFeeCategory}
              emptyLabel="— без категории —"
            />
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

      <div className="transaction-submit">
        <button type="button" onClick={submit} disabled={pending}>
          {pending
            ? "Сохраняю…"
            : editing
              ? "Сохранить изменения"
              : "Сохранить"}
        </button>
      </div>
    </div>
  )
}
