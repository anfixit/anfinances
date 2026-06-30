import { useMemo } from "react"

import { compareCategoriesByName } from "@/features/categories/sort"
import type { Category } from "@/features/categories/types"
import type { CategoryKind } from "@/types/enums"

// Каскадный выбор категории: верхний уровень + необязательная
// подкатегория. Полностью контролируемый — состояние не держит, а
// выводит выбор из единственного `value` (id листа или родителя).
//
// Правило (вариант 1): подкатегория необязательна. Если выбран
// только родитель, операция идёт на него; выбор подкатегории
// уточняет до листа.
//
// Бэкенд хранит один `category_id`, поэтому наружу компонент отдаёт
// тоже один id — это сохраняет совместимость со всеми формами.

interface CategorySelectProps {
  categories: readonly Category[]
  kind: Extract<CategoryKind, "expense" | "income">
  value: string
  onChange: (categoryId: string) => void
  // Текст «пустого» варианта родителя. Если не задан — выбор
  // категории обязателен (пустого варианта нет).
  emptyLabel?: string
  disabled?: boolean
}

export function CategorySelect({
  categories,
  kind,
  value,
  onChange,
  emptyLabel,
  disabled = false,
}: CategorySelectProps) {
  const byId = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories],
  )

  const parents = useMemo(
    () =>
      categories
        .filter((c) => c.kind === kind && c.parent_id === null)
        .sort(compareCategoriesByName),
    [categories, kind],
  )

  // Выводим выбранного родителя и подкатегорию из value.
  const selected = value ? byId.get(value) : undefined
  const parentId =
    selected === undefined
      ? ""
      : selected.parent_id === null
        ? selected.id
        : selected.parent_id
  const subId =
    selected !== undefined && selected.parent_id !== null ? selected.id : ""

  const children = useMemo(
    () =>
      parentId
        ? categories
            .filter((c) => c.parent_id === parentId)
            .sort(compareCategoriesByName)
        : [],
    [categories, parentId],
  )

  const onParentChange = (next: string) => {
    // Смена родителя сбрасывает подкатегорию: операция идёт на
    // сам родитель, пока не уточнят лист.
    onChange(next)
  }

  const onSubChange = (next: string) => {
    // Пустая подкатегория — остаёмся на родителе.
    onChange(next || parentId)
  }

  return (
    <>
      <label className="field">
        <span>Категория</span>
        <select
          value={parentId}
          disabled={disabled}
          onChange={(e) => onParentChange(e.target.value)}
        >
          {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
          {parents.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>
          Подкатегория <span className="hint">(необязательно)</span>
        </span>
        <select
          value={subId}
          disabled={disabled || children.length === 0}
          onChange={(e) => onSubChange(e.target.value)}
        >
          <option value="">— вся категория —</option>
          {children.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}
