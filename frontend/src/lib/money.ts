import type { Money } from "@/types/api"

// Деньги приходят строками (Decimal на бэке). Number() здесь — только
// для отображения; арифметику над деньгами клиент не делает.
export function formatMoney(
  amount: Money,
  currency: string,
  locale = "ru-RU",
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
  }).format(Number(amount))
}
