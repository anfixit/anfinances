import type { CategoryKind } from "@/types/enums"

// Зеркало CategoryRead (app/domains/categories/schemas.py).
export interface Category {
  id: string
  name: string
  kind: CategoryKind
  parent_id: string | null
  icon: string | null
  sort_order: number
  is_archived: boolean
  created_at: string
  updated_at: string
}
