import { useState } from "react"

import type { Currency, UserCurrency } from "@/features/currencies/types"
import {
  useCurrencies,
  useMyCurrencies,
  useRates,
  useRefreshRates,
  useSetMyCurrencies,
} from "@/features/currencies/hooks"
import { AppError } from "@/lib/api/errors"
import { formatDate } from "@/lib/datetime"

interface Row {
  currency_code: string
  is_default: boolean
}

export function CurrenciesPage() {
  const registry = useCurrencies()
  const mine = useMyCurrencies()
  const rates = useRates()
  const refresh = useRefreshRates()

  if (registry.isPending || mine.isPending) {
    return <p>Загрузка…</p>
  }
  if (registry.isError || !registry.data || mine.isError || !mine.data) {
    return <p className="error">Не удалось загрузить валюты</p>
  }

  return (
    <>
      <h1>Валюты</h1>

      <h2>Мои валюты</h2>
      <CurrencySetEditor initial={mine.data} registry={registry.data} />

      <h2>Курсы (к рублю)</h2>
      <p>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
        >
          {refresh.isPending ? "Обновляю…" : "Обновить курсы"}
        </button>
      </p>
      {rates.data && (
        <table className="rates">
          <thead>
            <tr>
              <th>Валюта</th>
              <th>Курс</th>
              <th>Обновлено</th>
            </tr>
          </thead>
          <tbody>
            {rates.data.map((r) => (
              <tr key={`${r.base_code}-${r.quote_code}`}>
                <td>{r.base_code}</td>
                <td>{r.rate}</td>
                <td>{formatDate(r.fetched_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function CurrencySetEditor({
  initial,
  registry,
}: {
  initial: UserCurrency[]
  registry: Currency[]
}) {
  const save = useSetMyCurrencies()
  // Инициализируем рабочий набор из пропа один раз (компонент
  // монтируется уже с загруженными данными — без эффекта).
  const [rows, setRows] = useState<Row[]>(() =>
    [...initial]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((c) => ({
        currency_code: c.currency_code,
        is_default: c.is_default,
      })),
  )

  const used = new Set(rows.map((r) => r.currency_code))
  const available = registry.filter((c) => !used.has(c.code))
  const nameOf = (code: string) =>
    registry.find((c) => c.code === code)?.name ?? code

  const add = (code: string) =>
    setRows((rs) => [...rs, { currency_code: code, is_default: false }])
  const remove = (code: string) =>
    setRows((rs) => rs.filter((r) => r.currency_code !== code))
  const setDefault = (code: string) =>
    setRows((rs) =>
      rs.map((r) => ({ ...r, is_default: r.currency_code === code })),
    )
  const move = (index: number, dir: -1 | 1) =>
    setRows((rs) => {
      const j = index + dir
      if (j < 0 || j >= rs.length) return rs
      const copy = [...rs]
      const a = copy[index]
      const b = copy[j]
      if (a && b) {
        copy[index] = b
        copy[j] = a
      }
      return copy
    })

  const onSave = () => {
    save.mutate(
      rows.map((r, i) => ({
        currency_code: r.currency_code,
        is_default: r.is_default,
        sort_order: i,
      })),
    )
  }

  return (
    <>
      <ul className="tree">
        {rows.map((r, i) => (
          <li key={r.currency_code} className="row">
            <span className="row-name">
              {r.currency_code} — {nameOf(r.currency_code)}
            </span>
            <label className="inline">
              <input
                type="radio"
                name="default-currency"
                checked={r.is_default}
                onChange={() => setDefault(r.currency_code)}
              />
              основная
            </label>
            <button type="button" className="link" onClick={() => move(i, -1)}>
              ↑
            </button>
            <button type="button" className="link" onClick={() => move(i, 1)}>
              ↓
            </button>
            <button
              type="button"
              className="link danger"
              onClick={() => remove(r.currency_code)}
            >
              убрать
            </button>
          </li>
        ))}
      </ul>

      {available.length > 0 && (
        <select
          value=""
          onChange={(e) => {
            if (e.target.value) add(e.target.value)
          }}
        >
          <option value="">+ добавить валюту</option>
          {available.map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      )}

      <p className="row">
        <button type="button" onClick={onSave} disabled={save.isPending}>
          {save.isPending ? "Сохраняю…" : "Сохранить набор"}
        </button>
        {save.isError && (
          <span className="error">
            {save.error instanceof AppError ? save.error.message : "Ошибка"}
          </span>
        )}
        {save.isSuccess && <span className="ok">Сохранено</span>}
      </p>
    </>
  )
}
