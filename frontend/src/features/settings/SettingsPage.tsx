import { useState } from "react"
import { Link } from "react-router-dom"

import { useAuth } from "@/auth/useAuth"
import { ThemeToggle } from "@/components/ThemeToggle"
import { useCurrencies } from "@/features/currencies/hooks"
import { useUpdateProfile } from "@/features/users/hooks"
import { AppError } from "@/lib/api/errors"

const LOCALES = [
  { value: "ru", label: "Русский" },
  { value: "en", label: "English" },
]

export function SettingsPage() {
  const { user } = useAuth()
  const currencies = useCurrencies()
  const update = useUpdateProfile()

  const [name, setName] = useState(user?.name ?? "")
  const [timezone, setTimezone] = useState(user?.timezone ?? "")
  const [currency, setCurrency] = useState(user?.default_currency ?? "RUB")
  const [locale, setLocale] = useState(user?.locale ?? "ru")
  const [saved, setSaved] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  if (!user) {
    return <p>Загрузка…</p>
  }

  const save = () => {
    setSaved(false)
    setFormError(null)
    update.mutate(
      {
        name,
        timezone: timezone || "UTC",
        default_currency: currency,
        locale,
      },
      {
        onSuccess: () => {
          setSaved(true)
        },
        onError: (err: unknown) => {
          setFormError(
            err instanceof AppError ? err.message : "Не удалось сохранить",
          )
        },
      },
    )
  }

  return (
    <>
      <h1>Настройки</h1>

      <div className="card">
        <h2>Профиль</h2>
        <div className="form">
          <label className="field">
            <span>Имя</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span>Часовой пояс</span>
            <input
              value={timezone}
              placeholder="Europe/Moscow"
              onChange={(e) => setTimezone(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Валюта по умолчанию</span>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              {(currencies.data ?? []).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Язык</span>
            <select
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
            >
              {LOCALES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          {formError && <p className="error">{formError}</p>}
          {saved && <p className="ok">Сохранено</p>}

          <button type="button" onClick={save} disabled={update.isPending}>
            {update.isPending ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>Аккаунт</h2>
        <div className="set-row">
          <span className="set-label">Email</span>
          <span>{user.email}</span>
        </div>
        <div className="set-row">
          <span className="set-label">Почта подтверждена</span>
          <span>{user.is_verified ? "да" : "нет"}</span>
        </div>
        <div className="set-row">
          <span className="set-label">Тема</span>
          <ThemeToggle />
        </div>
      </div>

      <div className="card">
        <h2>Данные</h2>
        <div className="set-row">
          <span className="set-label">Экспорт и резервная копия</span>
          <Link className="link" to="/backup">
            Открыть
          </Link>
        </div>
        <div className="set-row">
          <span className="set-label">Набор валют</span>
          <Link className="link" to="/currencies">
            Открыть
          </Link>
        </div>
      </div>
    </>
  )
}
