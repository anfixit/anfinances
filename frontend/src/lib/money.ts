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

// Numeric(18,4) на бэке → масштаб 10^4 минорных единиц.
const MONEY_SCALE = 10000

// Сумма денежных строк без накопления ошибки IEEE754: каждое значение
// округляем до целых минорных единиц и складываем целыми, делим один
// раз в конце. Возвращает число (для отображения и долей-процентов).
export function sumMoney(amounts: readonly Money[]): number {
  let minor = 0
  for (const amount of amounts) {
    minor += Math.round(Number(amount) * MONEY_SCALE)
  }
  return minor / MONEY_SCALE
}
