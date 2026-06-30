import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import type { Account } from "@/features/accounts/types"
import { CategorySelect } from "@/features/categories/CategorySelect"
import { useCategories } from "@/features/categories/hooks"
import {
  useCreateTransaction,
  useCreateTransfer,
  useUpdateTransaction,
  useUpdateTransfer,
} from "@/features/transactions/hooks"
import {
  ordinaryTxSchema,
  transferTxSchema,
} from "@/features/transactions/schemas"
import type {
  Transaction,
  Transfer,
} from "@/features/transactions/types"
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
  transfer?: Transfer
}

export function TransactionSheet({
  onDone,
  transaction,
  transfer,
}: TransactionSheetProps) {
  const accountsQ = useAccounts()
  const categoriesQ = useCategories()
  const createTx = useCreateTransaction()
  const createTransfer = useCreateTransfer()
  const updateTx = useUpdateTransaction()
  const updateTransfer = useUpdateTransfer()
  const editing = transaction !== undefined || transfer !== undefined
  const sourceLeg = transfer?.legs.find((leg) => Number(leg.amount) < 0)
  const destinationLeg = transfer?.legs.find(
    (leg) => Number(leg.amount) > 0,
  )

  const [mode, setMode] = useState<Mode>(() => {
    if (transfer) {
      return "transfer"
    }
    return transaction?.kind === "income" ? "income" : "expense"
  })
  const [date, setDate] = useState<string>(() => {
    const value = transaction?.date ?? sourceLeg?.date
    return value ? toLocalInput(value) : nowLocalInput()
  })
  const [comment, setComment] = useState(
    transaction?.comment ?? sourceLeg?.comment ?? "",
  )
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
  const [fromId, setFromId] = useState(sourceLeg?.account_id ?? "")
  const [toId, setToId] = useState(destinationLeg?.account_id ?? "")
  const [amountFrom, setAmountFrom] = useState(() => {
    const value = sourceLeg?.amount ?? ""
    return value.startsWith("-") ? value.slice(1) : value
  })
  const [amountTo, setAmountTo] = useState(
    destinationLeg?.amount ?? "",
  )
  const [feeAmount, setFeeAmount] = useState(() => {
    const value = transfer?.fee?.amount ?? ""
    return value.startsWith("-") ? value.slice(1) : value
  })
  const [feeCategory, setFeeCategory] = useState(
    transfer?.fee?.category_id ?? "",
  )

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
    createTx.isPending ||
    createTransfer.isPending ||
    updateTx.isPending ||
    updateTransfer.isPending

  const onError = (err: unknown) => {
    if (!(err instanceof AppError)) {
      setFormError("Ошибка сохранения")
      return
    }
    const detail = err.details[0]?.message
    setFormError(detail ?? err.message)
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
    const normalizedFee =
      feeAmount.trim() !== "" && Number(feeAmount) > 0
        ? feeAmount.trim()
        : null
    const parsed = transferTxSchema.safeParse({
      from_account_id: fromId,
      to_account_id: toId,
      amount_from: amountFrom,
      amount_to: effectiveTo,
      date,
      fee_amount: normalizedFee,
      fee_category_id: normalizedFee ? feeCategory || null : null,
      comment: comment || null,
    })
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }
    const input = {
      from_account_id: fromId,
      to_account_id: toId,
      amount_from: amountFrom.trim(),
      amount_to: effectiveTo.trim(),
      date: new Date(date).toISOString(),
      comment: comment || null,
      fee_amount: normalizedFee,
      fee_category_id: normalizedFee ? feeCategory || null : null,
    }
    if (transfer) {
      updateTransfer.mutate(
        { id: transfer.id, input },
        { onSuccess: onDone, onError },
      )
      return
    }
    createTransfer.mutate(input, { onSuccess: onDone, onError })
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

      {transaction && (
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
              onChange={(e) => {
                setFeeAmount(e.target.value)
                if (Number(e.target.value) <= 0) {
                  setFeeCategory("")
                }
              }}
            />
          </label>
          {Number(feeAmount) > 0 && (
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
