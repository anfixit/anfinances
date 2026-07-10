import type { IsoDate, Money } from "@/types/api"
import type { RequiredKind, TransactionKind } from "@/types/enums"

// Зеркало TransactionRead (app/domains/transactions/schemas.py).
export interface Transaction {
  id: string
  account_id: string
  transfer_id: string | null
  kind: TransactionKind
  required: RequiredKind | null
  amount: Money
  currency_code: string
  amount_rub: Money
  exchange_rate: Money
  category_id: string | null
  category_name_snapshot: string | null
  subcategory_name_snapshot: string | null
  account_name_snapshot: string | null
  to_account_name_snapshot: string | null
  date: IsoDate
  comment: string | null
  created_at: IsoDate
  updated_at: IsoDate
}

// Зеркало TransferRead: пара ног + опциональная нога-комиссия.
export interface Transfer {
  id: string
  legs: Transaction[]
  fee: Transaction | null
}

// meta.next_cursor бэкенда: (date, id) последней строки страницы.
export interface TransactionCursor {
  cursor_date: string
  cursor_id: string
}

export interface TransactionFilters {
  date_from?: string
  date_to?: string
  account_id?: string
  category_id?: string
  kind?: TransactionKind
}
