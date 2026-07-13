import { useState } from "react"

import { useAccounts } from "@/features/accounts/hooks"
import {
  useCreateCredit,
  useUpdateCredit,
} from "@/features/credits/hooks"
import { creditFormSchema } from "@/features/credits/schemas"
import type { Credit } from "@/features/credits/types"
import { useCurrencies } from "@/features/currencies/hooks"
import { AppError } from "@/lib/api/errors"

function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === "" ? null : trimmed
}

function emptyNumberToNull(value: string): number | null {
  const trimmed = value.trim()
  return trimmed === "" ? null : Number(trimmed)
}

interface CreditFormProps {
  credit: Credit | null
  onDone: () => void
}

export function CreditForm({ credit, onDone }: CreditFormProps) {
  const accounts = useAccounts()
  const currencies = useCurrencies()
  const create = useCreateCredit()
  const update = useUpdateCredit()
  const isEdit = credit !== null

  const [name, setName] = useState(credit?.name ?? "")
  const [lender, setLender] = useState(credit?.lender ?? "")
  const [currency, setCurrency] = useState(credit?.currency_code ?? "")
  const [principalInitial, setPrincipalInitial] = useState(
    credit?.principal_initial ?? "",
  )
  const [annualRate, setAnnualRate] = useState(credit?.annual_rate ?? "")
  const [termMonths, setTermMonths] = useState(
    credit?.term_months === null || credit?.term_months === undefined
      ? ""
      : String(credit.term_months),
  )
  const [startDate, setStartDate] = useState(credit?.start_date ?? "")
  const [paymentDay, setPaymentDay] = useState(
    credit?.payment_day === null || credit?.payment_day === undefined
      ? ""
      : String(credit.payment_day),
  )
  const [linkedAccountId, setLinkedAccountId] = useState(
    credit?.linked_account_id ?? "",
  )
  const [comments, setComments] = useState(credit?.comments ?? "")
  const [formError, setFormError] = useState<string | null>(null)

  const pending = create.isPending || update.isPending
  const accountsByCurrency = (accounts.data ?? []).filter(
    (account) => account.currency_code === currency,
  )

  const onError = (err: unknown) => {
    if (!(err instanceof AppError)) {
      setFormError("Ошибка сохранения")
      return
    }
    setFormError(err.details[0]?.message ?? err.message)
  }

  const submit = () => {
    setFormError(null)

    const parsed = creditFormSchema.safeParse({
      name,
      lender: emptyToNull(lender),
      currency_code: currency,
      principal_initial: principalInitial,
      annual_rate: annualRate,
      term_months: termMonths,
      start_date: emptyToNull(startDate),
      payment_day: paymentDay,
      linked_account_id: emptyToNull(linkedAccountId),
      comments: emptyToNull(comments),
    })
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }

    const payload = {
      name: name.trim(),
      lender: emptyToNull(lender),
      principal_initial: principalInitial.trim(),
      annual_rate: emptyToNull(annualRate),
      term_months: emptyNumberToNull(termMonths),
      start_date: emptyToNull(startDate),
      payment_day: emptyNumberToNull(paymentDay),
      linked_account_id: emptyToNull(linkedAccountId),
      comments: emptyToNull(comments),
    }

    if (isEdit) {
      update.mutate(
        { id: credit.id, input: payload },
        { onSuccess: onDone, onError },
      )
      return
    }

    create.mutate(
      { ...payload, currency_code: currency },
      { onSuccess: onDone, onError },
    )
  }

  return (
    <div className="form credit-form">
      <label className="field">
        <span>Название</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>

      <label className="field">
        <span>Банк или кредитор</span>
        <input value={lender} onChange={(e) => setLender(e.target.value)} />
      </label>

      <label className="field">
        <span>Валюта{isEdit ? " (нельзя изменить)" : ""}</span>
        <select
          value={currency}
          disabled={isEdit}
          onChange={(e) => {
            setCurrency(e.target.value)
            setLinkedAccountId("")
          }}
        >
          <option value="">— выберите —</option>
          {(currencies.data ?? []).map((item) => (
            <option key={item.code} value={item.code}>
              {item.code} — {item.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Начальная сумма кредита</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={principalInitial}
          onChange={(e) => setPrincipalInitial(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Ставка годовых, %</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={annualRate}
          onChange={(e) => setAnnualRate(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Срок, месяцев</span>
        <input
          type="number"
          inputMode="numeric"
          min="1"
          step="1"
          value={termMonths}
          onChange={(e) => setTermMonths(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Дата начала</span>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
      </label>

      <label className="field">
        <span>День платежа</span>
        <input
          type="number"
          inputMode="numeric"
          min="1"
          max="31"
          step="1"
          value={paymentDay}
          onChange={(e) => setPaymentDay(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Счёт списания по умолчанию</span>
        <select
          value={linkedAccountId}
          disabled={!currency}
          onChange={(e) => setLinkedAccountId(e.target.value)}
        >
          <option value="">— не выбран —</option>
          {accountsByCurrency.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} ({account.currency_code})
            </option>
          ))}
        </select>
        {currency && accountsByCurrency.length === 0 && (
          <span className="hint">
            Нет активных счетов в валюте {currency}.
          </span>
        )}
      </label>

      <label className="field">
        <span>Комментарий</span>
        <input
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />
      </label>

      {formError && <p className="error">{formError}</p>}

      <button type="button" onClick={submit} disabled={pending}>
        {pending ? "Сохраняю…" : isEdit ? "Сохранить" : "Создать кредит"}
      </button>
    </div>
  )
}
