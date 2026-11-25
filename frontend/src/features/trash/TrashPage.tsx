import { useState } from "react"

import { useRestoreFromTrash, useTrash } from "@/features/trash/hooks"
import type { DeletedKind, DeletedRecord } from "@/features/trash/types"
import { AppError } from "@/lib/api/errors"
import { formatDate } from "@/lib/datetime"

const KIND_LABELS: Record<DeletedKind, string> = {
  transaction: "Операция",
  transfer: "Перевод",
  credit_payment: "Платёж по кредиту",
}

/** Корзина: удалённые операции, переводы и платежи — с возвратом. */
export function TrashPage() {
  const trash = useTrash()

  return (
    <>
      <h1>Корзина</h1>
      <div className="card">
        <p className="set-note">
          Сюда попадают удалённые операции, переводы и платежи по кредиту —
          и с сайта, и от ИИ-ассистента. «Вернуть» ставит запись на место
          такой, какой она была.
        </p>

        {trash.isPending && <p>Загрузка…</p>}
        {trash.isError && <p className="error">Не удалось загрузить корзину</p>}
        {trash.data?.length === 0 && <p className="set-note">Корзина пуста.</p>}
        {trash.data && trash.data.length > 0 && (
          <ul className="trash-list">
            {trash.data.map((record) => (
              <li key={record.id}>
                <TrashRow record={record} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

function TrashRow({ record }: { record: DeletedRecord }) {
  const restore = useRestoreFromTrash()
  const [error, setError] = useState<string | null>(null)

  const onRestore = () => {
    setError(null)
    restore.mutate(record.id, {
      onError: (err: unknown) => {
        setError(err instanceof AppError ? err.message : "Не удалось вернуть")
      },
    })
  }

  return (
    <div className="trash-row">
      <div className="trash-row-main">
        <span>{record.summary}</span>
        <span className="trash-meta">
          {KIND_LABELS[record.kind]} · удалено {formatDate(record.deleted_at)}{" "}
          · {record.source}
        </span>
        {error && <span className="error">{error}</span>}
      </div>
      <button
        type="button"
        className="link"
        onClick={onRestore}
        disabled={restore.isPending}
      >
        {restore.isPending ? "Возвращаю…" : "Вернуть"}
      </button>
    </div>
  )
}
