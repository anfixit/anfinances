import { useState } from "react"

import { useMoveBudget } from "@/features/budgets/hooks"
import type { Budget } from "@/features/budgets/types"
import type { Category } from "@/features/categories/types"
import { Sheet } from "@/components/Sheet"
import { formatMoney } from "@/lib/money"

interface Donor {
  category: Category
  budget: Budget
  left: number
}

interface Props {
  month: string
  targetName: string
  targetCategoryId: string
  shortfall: number
  donors: Donor[]
  onClose: () => void
}

/**
 * Закрыть перерасход из другой категории — третье правило ВНБ.
 *
 * Донорами предлагаются только категории с неистраченным остатком:
 * взять из той, что сама в минусе, значит переложить дыру, а не
 * закрыть её.
 */
export function MoveSheet({
  month,
  targetName,
  targetCategoryId,
  shortfall,
  donors,
  onClose,
}: Props) {
  const move = useMoveBudget()
  const [from, setFrom] = useState<string>(donors[0]?.category.id ?? "")
  const [amount, setAmount] = useState<string>(String(shortfall))
  const [error, setError] = useState<string | null>(null)

  const donor = donors.find((d) => d.category.id === from)
  const value = Number(amount.replace(",", "."))
  const tooMuch = donor !== undefined && value > donor.left

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!donor || !(value > 0)) {
      setError("Выберите категорию и сумму больше нуля.")
      return
    }
    move.mutate(
      {
        month,
        from_category_id: donor.category.id,
        to_category_id: targetCategoryId,
        amount: String(value),
      },
      {
        onSuccess: onClose,
        onError: () => {
          setError("Не удалось перенести. Попробуйте ещё раз.")
        },
      },
    )
  }

  return (
    <Sheet open title={`Покрыть «${targetName}»`} onClose={onClose}>
      {donors.length === 0 ? (
        <p>
          Взять неоткуда: во всех категориях план уже исчерпан. Придётся
          увеличить лимит и признать, что месяц идёт дороже плана.
        </p>
      ) : (
        <form onSubmit={submit}>
          <p className="allowance-note">
            Перерасход {formatMoney(String(shortfall), "RUB")}. Деньги не
            появятся — они просто сменят назначение.
          </p>

          <label className="field">
            <span>Взять из категории</span>
            <select value={from} onChange={(e) => setFrom(e.target.value)}>
              {donors.map((d) => (
                <option key={d.category.id} value={d.category.id}>
                  {d.category.name} — свободно{" "}
                  {formatMoney(String(d.left), "RUB")}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Сумма</span>
            <input
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>

          {tooMuch && donor && (
            <p className="error">
              В этой категории свободно только{" "}
              {formatMoney(String(donor.left), "RUB")}.
            </p>
          )}
          {error && <p className="error">{error}</p>}

          <button
            type="submit"
            className="btn-filled"
            disabled={move.isPending || tooMuch}
          >
            {move.isPending ? "Переношу…" : "Перенести"}
          </button>
        </form>
      )}
    </Sheet>
  )
}
