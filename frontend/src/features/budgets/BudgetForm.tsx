import { useState } from "react"

import {
  useCreateBudget,
  useUpdateBudget,
} from "@/features/budgets/hooks"
import type { Budget } from "@/features/budgets/types"
import { AppError } from "@/lib/api/errors"

export function BudgetForm({
  month,
  categoryId,
  categoryName,
  budget,
  onDone,
}: {
  month: string
  categoryId: string
  categoryName: string
  budget: Budget | null
  onDone: () => void
}) {
  const create = useCreateBudget()
  const update = useUpdateBudget()

  const [planned, setPlanned] = useState(budget?.planned ?? "")
  const [rollover, setRollover] = useState(budget?.rollover ?? false)
  const [notes, setNotes] = useState(budget?.notes ?? "")
  const [formError, setFormError] = useState<string | null>(null)

  const pending = create.isPending || update.isPending

  const onError = (err: unknown) => {
    setFormError(err instanceof AppError ? err.message : "Ошибка сохранения")
  }

  const submit = () => {
    setFormError(null)
    const value = planned.trim()
    if (value !== "" && (Number.isNaN(Number(value)) || Number(value) < 0)) {
      setFormError("План должен быть числом не меньше нуля")
      return
    }
    const cmt = notes ? notes : null

    if (budget) {
      update.mutate(
        {
          id: budget.id,
          input: { planned: value || "0", rollover, notes: cmt },
        },
        { onSuccess: onDone, onError },
      )
    } else {
      create.mutate(
        {
          month,
          category_id: categoryId,
          planned: value || "0",
          rollover,
          notes: cmt,
        },
        { onSuccess: onDone, onError },
      )
    }
  }

  return (
    <div className="form">
      <div className="field">
        <span>Категория</span>
        <strong>{categoryName}</strong>
      </div>

      <label className="field">
        <span>План на месяц (₽)</span>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={planned}
          onChange={(e) => setPlanned(e.target.value)}
        />
      </label>

      <label className="inline">
        <input
          type="checkbox"
          checked={rollover}
          onChange={(e) => setRollover(e.target.checked)}
        />
        <span>Переносить остаток на следующий месяц</span>
      </label>

      <label className="field">
        <span>Заметка</span>
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>

      {formError && <p className="error">{formError}</p>}

      <button type="button" onClick={submit} disabled={pending}>
        {pending ? "Сохраняю…" : budget ? "Сохранить" : "Задать лимит"}
      </button>
    </div>
  )
}
