import { useState } from "react"

import { useCategories } from "@/features/categories/hooks"
import { RecurringForm } from "@/features/recurring/RecurringForm"
import {
  useArchiveRecurring,
  useGenerateFromCategories,
  useRecurring,
} from "@/features/recurring/hooks"
import type { Recurring } from "@/features/recurring/types"
import { Sheet } from "@/components/Sheet"
import { formatMoney } from "@/lib/money"

export function RecurringPage() {
  const recurring = useRecurring()
  const categoriesQ = useCategories()
  const archive = useArchiveRecurring()
  const generate = useGenerateFromCategories()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editing, setEditing] = useState<Recurring | null>(null)

  const catById = new Map((categoriesQ.data ?? []).map((c) => [c.id, c]))
  const items = recurring.data ?? []
  const totalRub = items.reduce((sum, i) => sum + Number(i.amount_rub ?? 0), 0)

  const openCreate = () => {
    setEditing(null)
    setSheetOpen(true)
  }
  const openEdit = (item: Recurring) => {
    setEditing(item)
    setSheetOpen(true)
  }
  const close = () => {
    setSheetOpen(false)
  }

  const remove = (item: Recurring) => {
    if (window.confirm(`Убрать «${item.name}» из плана-минимума?`)) {
      archive.mutate(item.id)
    }
  }

  const onGenerate = () => {
    generate.mutate(undefined, {
      onSuccess: (created) => {
        window.alert(
          created.length > 0
            ? `Добавлено записей: ${String(created.length)}`
            : "Новых категорий для плана не найдено.",
        )
      },
    })
  }

  return (
    <>
      <div className="page-head">
        <h1>План-минимум</h1>
        <button type="button" onClick={openCreate}>
          + Добавить
        </button>
      </div>

      <p className="rec-help">
        Обязательные ежемесячные траты по категориям. Итого в месяц:{" "}
        <strong className="num">{formatMoney(String(totalRub), "RUB")}</strong>
      </p>

      <p>
        <button
          type="button"
          className="btn-outline"
          onClick={onGenerate}
          disabled={generate.isPending}
        >
          {generate.isPending ? "Считаю…" : "Сгенерировать из категорий"}
        </button>
      </p>

      {recurring.isPending && <p>Загрузка…</p>}
      {recurring.isError && <p className="error">Не удалось загрузить план</p>}
      {recurring.isSuccess && items.length === 0 && (
        <p>План пуст. Добавьте обязательные траты или сгенерируйте из истории.</p>
      )}

      <ul className="rec-list">
        {items.map((item) => {
          const cat = catById.get(item.category_id)
          const showRub =
            item.currency_code !== "RUB" && item.amount_rub !== null
          return (
            <li key={item.id} className="rec-row">
              <div className="rec-info">
                <span className="rec-name">{item.name}</span>
                <span className="rec-meta">
                  {cat?.name ?? "—"}
                  {item.required === "optional" ? " · необязательный" : ""}
                </span>
              </div>
              <span className="num rec-amount">
                {formatMoney(item.monthly_amount ?? "0", item.currency_code ?? "RUB")}
                {showRub && (
                  <span className="rec-rub">
                    {" "}
                    ({formatMoney(item.amount_rub ?? "0", "RUB")})
                  </span>
                )}
              </span>
              <button
                type="button"
                className="link"
                onClick={() => openEdit(item)}
              >
                Изменить
              </button>
              <button
                type="button"
                className="link danger"
                onClick={() => remove(item)}
              >
                Убрать
              </button>
            </li>
          )
        })}
      </ul>

      <Sheet
        open={sheetOpen}
        title={editing ? "Изменить платёж" : "Новый регулярный платёж"}
        onClose={close}
      >
        <RecurringForm
          key={editing?.id ?? "new"}
          item={editing}
          onDone={close}
        />
      </Sheet>
    </>
  )
}
