import type { IsoDate, Money } from "@/types/api"
import type { RequiredKind } from "@/types/enums"

// Зеркало RecurringRead (app/domains/recurring/schemas.py). План-минимум.
export interface Recurring {
  id: string
  required: RequiredKind | null
  category_id: string
  name: string
  monthly_amount: Money | null
  currency_code: string | null
  amount_rub: Money | null
  comments: string | null
  is_archived: boolean
  created_at: IsoDate
  updated_at: IsoDate
}
