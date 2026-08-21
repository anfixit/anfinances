import { ChevronRight } from "lucide-react"
import { useState } from "react"

import { useConfirm } from "@/components/confirm-context"
import { CategoryForm } from "@/features/categories/CategoryForm"
import { compareCategoriesByName } from "@/features/categories/sort"
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
  // Свёрнуто по умолчанию: полтора десятка родителей с подкатегориями
  // не помещались на экран, а нужен обычно один.
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())

  const toggle = (id: string) => {
    setOpen((current) => {
      const next = new Set(current)
      if (!next.delete(id)) {
        next.add(id)
      }
      return next
    })
  }

  if (isPending) {
    return <p>Загрузка…</p>
  }
  if (isError || !data) {
    return <p className="error">Не удалось загрузить категории</p>
  }

  const tops = (kind: (typeof KINDS)[number]) =>
    data
      .filter((c) => c.kind === kind && c.parent_id === null)
      .sort(compareCategoriesByName)
  const childrenOf = (parentId: string) =>
    data
      .filter((c) => c.parent_id === parentId)
      .sort(compareCategoriesByName)

  return (
    <>
      <h1>Категории</h1>
      {KINDS.map((kind) => (
        <section key={kind}>
          <h2>{KIND_LABEL[kind]}</h2>
          <ul className="tree">
            {tops(kind).map((top) => {
              const kids = childrenOf(top.id)
              const expanded = open.has(top.id)
              return (
                <li key={top.id}>
                  <CategoryRow
                    category={top}
                    childCount={kids.length}
                    expanded={expanded}
                    onToggle={() => {
                      toggle(top.id)
                    }}
                  />
                  {expanded && kids.length > 0 && (
                    <ul className="tree sub">
                      {kids.map((sub) => (
                        <li key={sub.id}>
                          <CategoryRow category={sub} />
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      <h2>Новая категория</h2>
      <CategoryForm categories={data} />
    </>
  )
}

interface CategoryRowProps {
  category: Category
  /** Есть только у родителя: сколько внутри подкатегорий. */
  childCount?: number
  expanded?: boolean
  onToggle?: () => void
}

function CategoryRow({
  category,
  childCount,
  expanded = false,
  onToggle,
}: CategoryRowProps) {
  const update = useUpdateCategory()
  const archive = useArchiveCategory()
  const { confirm } = useConfirm()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(category.name)

  const remove = async () => {
    const ok = await confirm({
      title: `Удалить категорию «${category.name}»?`,
      body:
        childCount !== undefined && childCount > 0
          ? [
              `Внутри подкатегорий: ${String(childCount)}.`,
              "Категория уйдёт в архив: операции по ней останутся, но " +
                "выбрать её при вводе новой будет нельзя.",
            ]
          : [
              "Категория уйдёт в архив: операции по ней останутся, но " +
                "выбрать её при вводе новой будет нельзя.",
            ],
      confirmLabel: "Удалить",
      danger: true,
    })
    if (ok) {
      archive.mutate(category.id)
    }
  }

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

  const collapsible = onToggle !== undefined && (childCount ?? 0) > 0

  return (
    <span className="row">
      {collapsible ? (
        <button
          type="button"
          className="tree-toggle"
          aria-expanded={expanded}
          onClick={onToggle}
        >
          <ChevronRight
            className={expanded ? "tree-caret tree-caret--open" : "tree-caret"}
            aria-hidden="true"
          />
          <span className="row-name">{category.name}</span>
          <span className="tree-count">{childCount}</span>
        </button>
      ) : (
        <span className="row-name row-name--leaf">{category.name}</span>
      )}
      <button type="button" className="link" onClick={() => setEditing(true)}>
        Переименовать
      </button>
      <button
        type="button"
        className="link danger"
        onClick={() => {
          void remove()
        }}
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
