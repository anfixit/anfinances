import { useState } from "react"

import { useCategories } from "@/features/categories/hooks"
import { useCurrencies } from "@/features/currencies/hooks"
import {
  useCreateRecurring,
  useUpdateRecurring,
} from "@/features/recurring/hooks"
import type { Recurring } from "@/features/recurring/types"
import { AppError } from "@/lib/api/errors"

export function RecurringForm({
  item,
  onDone,
}: {
  item: Recurring | null
  onDone: () => void
}) {
  const categoriesQ = useCategories()
  const currenciesQ = useCurrencies()
  const create = useCreateRecurring()
  const update = useUpdateRecurring()

  const isEdit = item !== null

  const [name, setName] = useState(item?.name ?? "")
  const [categoryId, setCategoryId] = useState(item?.category_id ?? "")
  const [amount, setAmount] = useState(item?.monthly_amount ?? "")
  const [currency, setCurrency] = useState(item?.currency_code ?? "RUB")
  const [required, setRequired] = useState(
    item ? item.required !== "optional" : true,
  )
  const [comments, setComments] = useState(item?.comments ?? "")
  const [formError, setFormError] = useState<string | null>(null)

  const pending = create.isPending || update.isPending

  const expenseCats = (categoriesQ.data ?? []).filter(
    (c) => c.kind === "expense",
  )

  const onError = (err: unknown) => {
    setFormError(err instanceof AppError ? err.message : "Ошибка сохранения")
  }

  const submit = () => {
    setFormError(null)
    if (!name.trim()) {
      setFormError("Укажите название")
      return
    }
    if (!categoryId) {
      setFormError("Выберите категорию")
      return
    }
    const value = amount.trim()
    if (Number.isNaN(Number(value)) || Number(value) <= 0) {
      setFormError("Сумма должна быть больше нуля")
      return
    }
    const req = required ? "required" : "optional"
    const cmt = comments ? comments : null

    if (isEdit) {
      update.mutate(
        {
          id: item.id,
          input: {
            required: req,
            category_id: categoryId,
            name,
            monthly_amount: value,
            currency_code: currency,
            comments: cmt,
          },
        },
        { onSuccess: onDone, onError },
      )
    } else {
      create.mutate(
        {
          required: req,
          category_id: categoryId,
          name,
          monthly_amount: value,
          currency_code: currency,
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
        <span>Категория (расход)</span>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
        >
          <option value="">— выберите —</option>
          {expenseCats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Сумма в месяц</span>
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
        <span>Валюта</span>
        <select
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
        >
          {(currenciesQ.data ?? []).map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </label>

      <label className="inline">
        <input
          type="checkbox"
          checked={required}
          onChange={(e) => setRequired(e.target.checked)}
        />
        <span>Обязательный платёж</span>
      </label>

      <label className="field">
        <span>Заметка</span>
        <input
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />
      </label>

      {formError && <p className="error">{formError}</p>}

      <button type="button" onClick={submit} disabled={pending}>
        {pending ? "Сохраняю…" : isEdit ? "Сохранить" : "Добавить"}
      </button>
    </div>
  )
}
