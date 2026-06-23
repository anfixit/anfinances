import type { Category } from "@/features/categories/types"

// Разделитель пути «Родитель → Подкатегория».
export const CATEGORY_PATH_SEP = " → "

// Путь категории для подписи в списках: «Родитель → Подкатегория»
// для подкатегории, просто имя — для верхнего уровня. Возвращает
// null, если категория не найдена (например, в архиве и отсутствует
// в активном списке) — вызывающий код сам решает, что показать.
export function categoryPath(
  byId: ReadonlyMap<string, Category>,
  categoryId: string | null,
): string | null {
  if (categoryId === null) {
    return null
  }
  const category = byId.get(categoryId)
  if (category === undefined) {
    return null
  }
  if (category.parent_id === null) {
    return category.name
  }
  const parent = byId.get(category.parent_id)
  if (parent === undefined) {
    return category.name
  }
  return `${parent.name}${CATEGORY_PATH_SEP}${category.name}`
}
