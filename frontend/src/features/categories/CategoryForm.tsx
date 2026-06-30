import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm, useWatch } from "react-hook-form"

import { useCreateCategory } from "@/features/categories/hooks"
import { compareCategoriesByName } from "@/features/categories/sort"
import { categoryFormSchema } from "@/features/categories/schemas"
import type { CategoryFormInput } from "@/features/categories/schemas"
import type { Category } from "@/features/categories/types"
import { AppError } from "@/lib/api/errors"

export function CategoryForm({ categories }: { categories: Category[] }) {
  const create = useCreateCategory()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<CategoryFormInput>({
    resolver: zodResolver(categoryFormSchema),
    defaultValues: { name: "", kind: "expense", parent_id: "" },
  })

  const kind = useWatch({ control, name: "kind" })
  const parentId = useWatch({ control, name: "parent_id" })
  const parentOptions = categories
    .filter((c) => c.kind === kind && c.parent_id === null)
    .sort(compareCategoriesByName)

  const submit = handleSubmit((values) => {
    setFormError(null)
    const parent = values.parent_id
      ? categories.find((c) => c.id === values.parent_id)
      : undefined
    create.mutate(
      {
        name: values.name,
        kind: parent ? parent.kind : values.kind,
        parent_id: values.parent_id || null,
      },
      {
        onSuccess: () => reset({ name: "", kind: values.kind, parent_id: "" }),
        onError: (err) =>
          setFormError(err instanceof AppError ? err.message : "Ошибка"),
      },
    )
  })

  return (
    <form className="form" onSubmit={(e) => void submit(e)}>
      <label className="field">
        <span>Название</span>
        <input {...register("name")} />
        {errors.name && <span className="error">{errors.name.message}</span>}
      </label>
      <label className="field">
        <span>Тип</span>
        <select {...register("kind")} disabled={Boolean(parentId)}>
          <option value="expense">Расход</option>
          <option value="income">Доход</option>
        </select>
      </label>
      <label className="field">
        <span>Родитель (необязательно)</span>
        <select {...register("parent_id")}>
          <option value="">— без родителя —</option>
          {parentOptions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {formError && <p className="error">{formError}</p>}
      <button type="submit" disabled={create.isPending}>
        {create.isPending ? "Добавляю…" : "Добавить"}
      </button>
    </form>
  )
}
