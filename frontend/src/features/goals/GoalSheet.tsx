import { useState } from "react"

import { useConfirm } from "@/components/confirm-context"
import type { Category } from "@/features/categories/types"
import { useDeleteGoal, useGoals, useUpsertGoal } from "@/features/goals/hooks"
import type { GoalKind } from "@/features/goals/types"
import { AppError } from "@/lib/api/errors"
import { formatMoney } from "@/lib/money"

/** Первое число месяца через N месяцев — типичный срок цели. */
function inMonths(count: number): string {
  const d = new Date()
  const target = new Date(d.getFullYear(), d.getMonth() + count, 1)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-01`
}

export function GoalSheet({
  category,
  month,
  onDone,
}: {
  category: Category
  month: string
  onDone: () => void
}) {
  const goals = useGoals(month)
  const existing = (goals.data ?? []).find(
    (g) => g.category_id === category.id,
  )

  const [kind, setKind] = useState<GoalKind>(existing?.kind ?? "by_date")
  const [amount, setAmount] = useState(existing?.amount ?? "")
  const [target, setTarget] = useState(
    existing?.target_date ?? inMonths(6),
  )
  const [error, setError] = useState<string | null>(null)

  const save = useUpsertGoal()
  const remove = useDeleteGoal()
  const { confirm } = useConfirm()

  const onError = (e: unknown) => {
    setError(e instanceof AppError ? e.message : "Не получилось")
  }

  const submit = () => {
    setError(null)
    save.mutate(
      {
        category_id: category.id,
        kind,
        amount: amount.trim(),
        target_date: kind === "by_date" ? target : null,
      },
      { onSuccess: onDone, onError },
    )
  }

  const drop = async () => {
    const ok = await confirm({
      title: `Убрать цель по категории «${category.name}»?`,
      body: [
        "Копилка и накопленное останутся — пропадёт только подсказка, " +
          "сколько класть в этом месяце.",
      ],
      confirmLabel: "Убрать цель",
      danger: true,
    })
    if (ok) {
      remove.mutate(category.id, { onSuccess: onDone, onError })
    }
  }

  return (
    <div className="form">
      <p className="hint">
        Цель отвечает на вопрос «сколько положить в этом месяце».
        Считается от уже накопленного: если полконверта собрано, взнос
        падает сам.
      </p>

      <div className="segmented">
        <button
          type="button"
          aria-pressed={kind === "by_date"}
          onClick={() => setKind("by_date")}
        >
          Накопить к дате
        </button>
        <button
          type="button"
          aria-pressed={kind === "monthly"}
          onClick={() => setKind("monthly")}
        >
          Каждый месяц
        </button>
      </div>

      <label className="field">
        <span>{kind === "by_date" ? "Сколько нужно" : "Сколько в месяц"}</span>
        <input
          inputMode="decimal"
          value={amount}
          placeholder="0.00"
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>

      {kind === "by_date" && (
        <label className="field">
          <span>К какому числу</span>
          <input
            type="date"
            value={target}
            onChange={(e) => setTarget(e.target.value || inMonths(6))}
          />
        </label>
      )}

      {existing !== undefined && (
        <div className="card card--inset">
          <div className="acc-row">
            <span className="acc-name">Накоплено</span>
            <span className="num">
              {formatMoney(existing.accumulated, "RUB")}
            </span>
          </div>
          <div className="acc-row">
            <span className="acc-name">
              Взнос этого месяца
              {existing.kind === "by_date" &&
                ` (осталось месяцев: ${String(existing.months_left)})`}
            </span>
            <span className="num">
              {formatMoney(existing.need_this_month, "RUB")}
            </span>
          </div>
          <div className="acc-row">
            <span className="acc-name">Ещё не запланировано</span>
            <span
              className={
                Number(existing.still_to_add) > 0 ? "num expense" : "num"
              }
            >
              {formatMoney(existing.still_to_add, "RUB")}
            </span>
          </div>
        </div>
      )}

      {error !== null && <p className="error">{error}</p>}

      <div className="transaction-submit">
        <button
          type="button"
          onClick={submit}
          disabled={amount.trim() === "" || save.isPending}
        >
          Сохранить
        </button>
        {existing !== undefined && (
          <button
            type="button"
            className="link danger"
            disabled={remove.isPending}
            onClick={() => {
              void drop()
            }}
          >
            Убрать цель
          </button>
        )}
        <button type="button" className="link" onClick={onDone}>
          Закрыть
        </button>
      </div>
    </div>
  )
}
