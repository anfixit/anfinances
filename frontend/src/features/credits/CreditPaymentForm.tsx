import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import { CategorySelect } from "@/features/categories/CategorySelect"
import { useCategories } from "@/features/categories/hooks"
import { useCreateCreditPayment } from "@/features/credits/hooks"
import { creditPaymentFormSchema } from "@/features/credits/schemas"
import type { Credit } from "@/features/credits/types"
import { AppError } from "@/lib/api/errors"

function toLocalInput(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function nowLocalInput(): string {
  return toLocalInput(new Date())
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === "" ? null : trimmed
}

interface CreditPaymentFormProps {
  credit: Credit
  onDone: () => void
}

export function CreditPaymentForm({
  credit,
  onDone,
}: CreditPaymentFormProps) {
  const accounts = useAccounts()
  const categories = useCategories()
  const createPayment = useCreateCreditPayment()

  const [paymentAccountId, setPaymentAccountId] = useState(
    credit.linked_account_id ?? "",
  )
  const [date, setDate] = useState(nowLocalInput())
  const [totalAmount, setTotalAmount] = useState("")
  const [principalAmount, setPrincipalAmount] = useState("")
  const [interestAmount, setInterestAmount] = useState("0")
  const [feeAmount, setFeeAmount] = useState("0")
  const [interestCategoryId, setInterestCategoryId] = useState("")
  const [feeCategoryId, setFeeCategoryId] = useState("")
  const [comment, setComment] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  const accountsByCurrency = (accounts.data ?? []).filter(
    (account) => account.currency_code === credit.currency_code,
  )
  const canChooseInterestCategory = Number(interestAmount) > 0
  const canChooseFeeCategory = Number(feeAmount) > 0

  const onError = (err: unknown) => {
    if (!(err instanceof AppError)) {
      setFormError("Ошибка сохранения")
      return
    }
    setFormError(err.details[0]?.message ?? err.message)
  }

  const submit = () => {
    setFormError(null)
    const payload = {
      payment_account_id: paymentAccountId,
      date,
      total_amount: totalAmount,
      principal_amount: principalAmount || "0",
      interest_amount: interestAmount || "0",
      fee_amount: feeAmount || "0",
      interest_category_id: canChooseInterestCategory
        ? emptyToNull(interestCategoryId)
        : null,
      fee_category_id: canChooseFeeCategory ? emptyToNull(feeCategoryId) : null,
      comment: emptyToNull(comment),
    }
    const parsed = creditPaymentFormSchema.safeParse(payload)
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }

    createPayment.mutate(
      {
        creditId: credit.id,
        input: {
          ...payload,
          date: new Date(date).toISOString(),
        },
      },
      { onSuccess: onDone, onError },
    )
  }

  if (accounts.isPending || categories.isPending) {
    return <p>Загрузка…</p>
  }
  if (!accounts.data || !categories.data) {
    return <p className="error">Не удалось загрузить справочники</p>
  }

  return (
    <div className="form credit-payment-form">
      <p className="form-note">
        Тело кредита уменьшит долг. Проценты и комиссии останутся
        расходной частью платежа.
      </p>

      <label className="field">
        <span>Счёт оплаты</span>
        <select
          value={paymentAccountId}
          onChange={(e) => setPaymentAccountId(e.target.value)}
        >
          <option value="">— выберите —</option>
          {accountsByCurrency.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} ({account.currency_code})
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Дата и время</span>
        <input
          type="datetime-local"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Сумма платежа</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={totalAmount}
          onChange={(e) => setTotalAmount(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Тело кредита</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={principalAmount}
          onChange={(e) => setPrincipalAmount(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Проценты</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={interestAmount}
          onChange={(e) => {
            setInterestAmount(e.target.value)
            if (Number(e.target.value) <= 0) {
              setInterestCategoryId("")
            }
          }}
        />
      </label>

      {canChooseInterestCategory && (
        <CategorySelect
          categories={categories.data}
          kind="expense"
          value={interestCategoryId}
          onChange={setInterestCategoryId}
          emptyLabel="— без категории —"
        />
      )}

      <label className="field">
        <span>Комиссия</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={feeAmount}
          onChange={(e) => {
            setFeeAmount(e.target.value)
            if (Number(e.target.value) <= 0) {
              setFeeCategoryId("")
            }
          }}
        />
      </label>

      {canChooseFeeCategory && (
        <CategorySelect
          categories={categories.data}
          kind="expense"
          value={feeCategoryId}
          onChange={setFeeCategoryId}
          emptyLabel="— без категории —"
        />
      )}

      <label className="field">
        <span>Комментарий</span>
        <input value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>

      {formError && <p className="error">{formError}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={createPayment.isPending}
      >
        {createPayment.isPending ? "Сохраняю…" : "Сохранить платёж"}
      </button>
    </div>
  )
}
