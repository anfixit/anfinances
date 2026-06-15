import { useState } from "react"

import { CategoryForm } from "@/features/categories/CategoryForm"
import {
  useArchiveCategory,
  useCategories,
  useUpdateCategory,
} from "@/features/categories/hooks"
import type { Category } from "@/features/categories/types"
import { AppError } from "@/lib/api/errors"

const KINDS = ["expense", "income"] as const
const KIND_LABEL: Record<(typeof KINDS)[number], string> = {
  expense: "Расходы",
  income: "Доходы",
}

export function CategoriesPage() {
  const { data, isPending, isError } = useCategories()

  if (isPending) {
    return <p>Загрузка…</p>
  }
  if (isError || !data) {
    return <p className="error">Не удалось загрузить категории</p>
  }

  const tops = (kind: (typeof KINDS)[number]) =>
    data.filter((c) => c.kind === kind && c.parent_id === null)
  const childrenOf = (parentId: string) =>
    data.filter((c) => c.parent_id === parentId)

  return (
    <>
      <h1>Категории</h1>
      {KINDS.map((kind) => (
        <section key={kind}>
          <h2>{KIND_LABEL[kind]}</h2>
          <ul className="tree">
            {tops(kind).map((top) => (
              <li key={top.id}>
                <CategoryRow category={top} />
                <ul className="tree sub">
                  {childrenOf(top.id).map((sub) => (
                    <li key={sub.id}>
                      <CategoryRow category={sub} />
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <h2>Новая категория</h2>
      <CategoryForm categories={data} />
    </>
  )
}

function CategoryRow({ category }: { category: Category }) {
  const update = useUpdateCategory()
  const archive = useArchiveCategory()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(category.name)

  if (editing) {
    return (
      <span className="row">
        <input value={name} onChange={(e) => setName(e.target.value)} />
        <button
          type="button"
          onClick={() =>
            update.mutate(
              { id: category.id, input: { name } },
              { onSuccess: () => setEditing(false) },
            )
          }
          disabled={update.isPending}
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
      <span className="row-name">{category.name}</span>
      <button type="button" className="link" onClick={() => setEditing(true)}>
        Переименовать
      </button>
      <button
        type="button"
        className="link danger"
        onClick={() => archive.mutate(category.id)}
        disabled={archive.isPending}
      >
        Удалить
      </button>
      {archive.isError && (
        <span className="error">
          {archive.error instanceof AppError
            ? archive.error.message
            : "Ошибка"}
        </span>
      )}
    </span>
  )
}
