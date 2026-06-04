import { useState } from "react"

import {
  useCreateAccount,
  useUpdateAccount,
} from "@/features/accounts/hooks"
import { accountFormSchema } from "@/features/accounts/schemas"
import type { Account } from "@/features/accounts/types"
import { useCurrencies } from "@/features/currencies/hooks"
import { AppError } from "@/lib/api/errors"
import type { AccountType } from "@/types/enums"

export const TYPE_LABELS: Record<AccountType, string> = {
  card: "Карта",
  cash: "Наличные",
  card_credit: "Кредитная карта",
  savings: "Накопительный",
  investment: "Инвестиции",
}

export function AccountForm({
  account,
  onDone,
}: {
  account: Account | null
  onDone: () => void
}) {
  const currencies = useCurrencies()
  const create = useCreateAccount()
  const update = useUpdateAccount()

  const isEdit = account !== null

  const [name, setName] = useState(account?.name ?? "")
  const [type, setType] = useState<AccountType>(account?.type ?? "card")
  const [currency, setCurrency] = useState(account?.currency_code ?? "")
  const [initial, setInitial] = useState(account?.initial_balance ?? "")
  const [creditLimit, setCreditLimit] = useState(account?.credit_limit ?? "")
  const [color, setColor] = useState(account?.color ?? "#4b53c9")
  const [sortOrder, setSortOrder] = useState(String(account?.sort_order ?? 0))
  const [comments, setComments] = useState(account?.comments ?? "")
  const [formError, setFormError] = useState<string | null>(null)

  const pending = create.isPending || update.isPending

  const onError = (err: unknown) => {
    setFormError(err instanceof AppError ? err.message : "Ошибка сохранения")
  }

  const submit = () => {
    setFormError(null)
    const parsed = accountFormSchema.safeParse({
      name,
      type,
      currency_code: currency,
      initial_balance: initial,
      credit_limit: creditLimit,
      sort_order: sortOrder,
      color,
      comments,
    })
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Проверьте поля")
      return
    }

    const order = sortOrder ? Number(sortOrder) : 0
    const limit = creditLimit ? creditLimit : null
    const cmt = comments ? comments : null

    if (isEdit) {
      update.mutate(
        {
          id: account.id,
          input: {
            name,
            type,
            initial_balance: initial || "0",
            credit_limit: limit,
            color,
            sort_order: order,
            comments: cmt,
          },
        },
        { onSuccess: onDone, onError },
      )
    } else {
      create.mutate(
        {
          name,
          type,
          currency_code: currency,
          initial_balance: initial || "0",
          credit_limit: limit,
          color,
          sort_order: order,
          comments: cmt,
        },
        { onSuccess: onDone, onError },
      )
    }
  }

  return (
    <div className="form">
      <label className="field">
        <span>Название</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>

      <label className="field">
        <span>Тип</span>
        <select
          value={type}
          onChange={(e) => setType(e.target.value as AccountType)}
        >
          {(Object.keys(TYPE_LABELS) as AccountType[]).map((t) => (
            <option key={t} value={t}>
              {TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Валюта{isEdit ? " (нельзя изменить)" : ""}</span>
        <select
          value={currency}
          disabled={isEdit}
          onChange={(e) => setCurrency(e.target.value)}
        >
          <option value="">— выберите —</option>
          {(currencies.data ?? []).map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Начальный баланс</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.01"
          value={initial}
          onChange={(e) => setInitial(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Кредитный лимит (необязательно)</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          value={creditLimit}
          onChange={(e) => setCreditLimit(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Цвет</span>
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Порядок</span>
        <input
          type="number"
          step="1"
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
        />
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
        {pending ? "Сохраняю…" : isEdit ? "Сохранить" : "Создать счёт"}
      </button>
    </div>
  )
}
