import type { Category } from "@/features/categories/types"

const CATEGORY_NAME_COLLATOR = new Intl.Collator("ru", {
  numeric: true,
  sensitivity: "base",
})

export function compareCategoriesByName(
  first: Category,
  second: Category,
): number {
  return CATEGORY_NAME_COLLATOR.compare(first.name, second.name)
}
