import { useState } from "react"

import { useConfirm } from "@/components/confirm-context"
import { useCategories } from "@/features/categories/hooks"
import {
  useDeletePayee,
  useMergePayees,
  useNewPayees,
  usePayees,
  useRenamePayee,
} from "@/features/payees/hooks"
import type { Payee } from "@/features/payees/types"
import { categoryPath } from "@/features/categories/path"

export function PayeesPage() {
  const payees = usePayees()
  const fresh = useNewPayees()
  const categories = useCategories()

  const catById = new Map((categories.data ?? []).map((c) => [c.id, c]))
  const freshIds = new Set((fresh.data ?? []).map((p) => p.id))

  if (payees.isPending) {
    return <p>Загрузка…</p>
  }
  if (payees.isError || !payees.data) {
    return <p className="error">Не удалось загрузить получателей</p>
  }

  return (
    <>
      <h1>Получатели</h1>

      <p className="rec-help">
        Кому уходят деньги. За каждым получателем сайт запоминает
        категорию последней операции и подставляет её в следующий раз —
        поэтому выписки разносятся сами.
      </p>

      {fresh.data && fresh.data.length > 0 && (
        <div className="card">
          <h2>Новые за месяц</h2>
          <p className="allowance-note">
            Раньше не встречались. Проверьте: забытая подписка или чужое
            списание выглядят именно так.
          </p>
          <p>
            <strong>{fresh.data.map((p) => p.name).join(", ")}</strong>
          </p>
        </div>
      )}

      {payees.data.length === 0 && (
        <p>
          Получателей пока нет. Они появятся сами, как только вы
          укажете магазин при вводе траты.
        </p>
      )}

      <ul className="tree">
        {payees.data.map((payee) => (
          <li key={payee.id}>
            <PayeeRow
              payee={payee}
              isNew={freshIds.has(payee.id)}
              hint={categoryPath(catById, payee.last_category_id)}
              all={payees.data ?? []}
            />
          </li>
        ))}
      </ul>
    </>
  )
}

function PayeeRow({
  payee,
  hint,
  isNew,
  all,
}: {
  payee: Payee
  hint: string | null
  isNew: boolean
  all: Payee[]
}) {
  const rename = useRenamePayee()
  const merge = useMergePayees()
  const remove = useDeletePayee()
  const { confirm } = useConfirm()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(payee.name)
  const [mergeInto, setMergeInto] = useState("")

  const onMerge = async () => {
    const target = all.find((p) => p.id === mergeInto)
    if (target === undefined) {
      return
    }
    const ok = await confirm({
      title: `Слить «${payee.name}» в «${target.name}»?`,
      body: [
        "Все операции первого получателя перевесятся на второго, а " +
          "он сам удалится.",
        "Отменить одним действием не получится.",
      ],
      confirmLabel: "Слить",
      danger: true,
    })
    if (ok) {
      merge.mutate({ sourceId: payee.id, targetId: target.id })
    }
  }

  const onDelete = async () => {
    const ok = await confirm({
      title: `Удалить получателя «${payee.name}»?`,
      body: [
        "Операции останутся, но потеряют ссылку на него — и вместе с " +
          "ней запомненную категорию.",
      ],
      confirmLabel: "Удалить",
      danger: true,
    })
    if (ok) {
      remove.mutate(payee.id)
    }
  }

  if (editing) {
    return (
      <span className="row">
        <input value={name} onChange={(e) => setName(e.target.value)} />
        <button
          type="button"
          disabled={rename.isPending}
          onClick={() =>
            rename.mutate(
              { id: payee.id, name },
              { onSuccess: () => setEditing(false) },
            )
          }
        >
          Сохранить
        </button>
        <button
          type="button"
          className="link"
          onClick={() => setEditing(false)}
        >
          Отмена
        </button>
      </span>
    )
  }

  return (
    <span className="row">
      <span className="row-name">
        {payee.name}
        {isNew && <span className="tree-count">новый</span>}
      </span>
      <span className="acc-meta">{hint ?? "категория не запомнена"}</span>
      <span className="spacer" />
      <select
        value={mergeInto}
        onChange={(e) => {
          setMergeInto(e.target.value)
        }}
      >
        <option value="">Слить в…</option>
        {all
          .filter((p) => p.id !== payee.id)
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
      </select>
      <button
        type="button"
        className="link"
        disabled={mergeInto === "" || merge.isPending}
        onClick={() => {
          void onMerge()
        }}
      >
        Слить
      </button>
      <button type="button" className="link" onClick={() => setEditing(true)}>
        Переименовать
      </button>
      <button
        type="button"
        className="link danger"
        disabled={remove.isPending}
        onClick={() => {
          void onDelete()
        }}
      >
        Удалить
      </button>
    </span>
  )
}
