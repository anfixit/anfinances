import type { IsoDate, Money } from "@/types/api"

// Зеркало PayeeRead (app/domains/payees/schemas.py).
export interface Payee {
  id: string
  name: string
  last_category_id: string | null
  // Маркетплейс: категория зависит от товара, память не пишется.
  varied_categories: boolean
  created_at: IsoDate
  updated_at: IsoDate
}

export interface PayeeSpending {
  payee_id: string
  name: string
  amount_rub: Money
  operations: number
}

export interface SpendingByPayee {
  month: string
  items: PayeeSpending[]
  total_rub: Money
  // Имена, что ждут подтверждения: в items их нет.
  unsorted_names: number
  unsorted_amount: Money
}

export type CandidateStatus = "pending" | "rejected"

// Зеркало PayeeCandidateRead: невиданное имя, ждущее решения.
export interface Candidate {
  id: string
  name: string
  times_seen: number
  amount: Money
  first_seen_at: string
  last_seen_at: string
  status: CandidateStatus
}
