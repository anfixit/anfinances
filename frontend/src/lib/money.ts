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

// U+2212 «−» — так минус ставят в банковских выписках и Word.
const TYPOGRAPHIC_MINUS = String.fromCharCode(0x2212)

/** Привести введённую сумму к виду, который понимает сервер.
 *
 * Запятая и точка — одинаково десятичный разделитель; пробелы между
 * тысячами (и неразрывные, которые прилетают при копировании из
 * банка) убираются; типографский минус «−» становится обычным. Если
 * есть и точка, и запятая — «1.234,56» или «1,234.56», — десятичный
 * разделитель последний, остальные были разрядами. Неразрывные
 * пробелы ловит сам \s.
 */
export function normalizeAmount(raw: string): string {
  const compact = raw
    .replace(/[\s']/g, "")
    .split(TYPOGRAPHIC_MINUS)
    .join("-")
  const last = Math.max(compact.lastIndexOf(","), compact.lastIndexOf("."))
  if (last === -1) {
    return compact
  }
  const whole = compact.slice(0, last).replace(/[.,]/g, "")
  return `${whole}.${compact.slice(last + 1)}`
}
