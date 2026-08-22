import type { IsoDate, Money } from "@/types/api"

export type GoalKind = "monthly" | "by_date"

// Зеркало GoalRead (app/domains/goals/schemas.py).
export interface Goal {
  id: string
  category_id: string
  kind: GoalKind
  amount: Money
  target_date: string | null
  accumulated: Money
  need_this_month: Money
  planned_this_month: Money
  still_to_add: Money
  months_left: number
  is_reached: boolean
  created_at: IsoDate
  updated_at: IsoDate
}

export interface GoalUpsertInput {
  category_id: string
  kind: GoalKind
  amount: string
  target_date?: string | null
}
