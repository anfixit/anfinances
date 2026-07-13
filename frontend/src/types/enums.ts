// Зеркало app/core/enums.py. Строковые значения совпадают с бэком.
export type AccountType =
  | "card"
  | "cash"
  | "card_credit"
  | "savings"
  | "investment"

export type CategoryKind = "expense" | "income" | "transfer"
export type RequiredKind = "required" | "optional"
export type TransactionKind =
  | "expense"
  | "income"
  | "transfer"
  | "credit_payment"
