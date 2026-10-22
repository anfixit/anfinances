import type { ChangeEvent, InputHTMLAttributes } from "react"

import { normalizeAmount } from "@/lib/money"

type MoneyInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "inputMode"
>

/** Поле суммы: запятая и точка работают одинаково.
 *
 * Не type="number": браузеры понимают его по-разному, и на iPhone и в
 * Firefox «1234,56» молча превращалось в пустое значение. Обычное
 * текстовое поле с десятичной клавиатурой, а ввод приводится к виду,
 * который понимает сервер, ещё до того, как попадёт в состояние формы.
 */
export function MoneyInput({ onChange, ...rest }: MoneyInputProps) {
  const handle = (event: ChangeEvent<HTMLInputElement>) => {
    const normalized = normalizeAmount(event.target.value)
    if (normalized !== event.target.value) {
      event.target.value = normalized
    }
    onChange?.(event)
  }
  return (
    <input
      {...rest}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      onChange={handle}
    />
  )
}
