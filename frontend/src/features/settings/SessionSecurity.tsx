import { useState } from "react"
import type { FormEvent } from "react"

import { changePassword, logoutEverywhere } from "@/auth/authApi"
import { setAccessToken } from "@/auth/tokenStore"
import { useAuth } from "@/auth/useAuth"
import { useConfirm } from "@/components/confirm-context"
import { AppError } from "@/lib/api/errors"
import { reportError } from "@/lib/errors/reportError"

/** Раздел настроек «Вход и сессии»: смена пароля и выход везде. */
export function SessionSecurity() {
  return (
    <div className="card">
      <h2>Вход и сессии</h2>
      <PasswordForm />
      <LogoutEverywhere />
    </div>
  )
}

function PasswordForm() {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [repeat, setRepeat] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setDone(false)
    if (next !== repeat) {
      setError("Новый пароль и повтор не совпадают.")
      return
    }
    setBusy(true)
    try {
      // Сервер завершил остальные сессии и выдал этому устройству
      // свежий токен — подставляем его, чтобы не вылететь самим.
      setAccessToken(await changePassword(current, next))
      setCurrent("")
      setNext("")
      setRepeat("")
      setDone(true)
    } catch (err) {
      setError(
        err instanceof AppError ? err.message : "Не удалось сменить пароль",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={(e) => void submit(e)}>
      <label className="field">
        <span>Текущий пароль</span>
        <input
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
        />
      </label>
      <label className="field">
        <span>Новый пароль</span>
        <input
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          required
        />
      </label>
      <label className="field">
        <span>Новый пароль ещё раз</span>
        <input
          type="password"
          autoComplete="new-password"
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
          required
        />
      </label>
      <p className="set-note">
        Не короче 15 символов; подойдёт фраза из нескольких слов. После
        смены остальные устройства выйдут. Телеграм-бот входит тем же
        паролем: обновите секрет SINGLE_USER_PASSWORD в GitHub и
        выкатите — иначе бот перестанет записывать.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {done && <p className="ok">Пароль сменён, остальные устройства вышли.</p>}
      <button type="submit" disabled={busy}>
        {busy ? "Меняю…" : "Сменить пароль"}
      </button>
    </form>
  )
}

function LogoutEverywhere() {
  const { confirm } = useConfirm()
  const { logout } = useAuth()
  const [busy, setBusy] = useState(false)

  const run = async () => {
    const ok = await confirm({
      title: "Выйти на всех устройствах?",
      body: [
        "Завершатся все сессии — на телефоне, в других браузерах и здесь. " +
          "Войти заново можно паролем.",
        "Пригодится, если потеряли телефон или вошли с чужого компьютера.",
      ],
      confirmLabel: "Выйти везде",
      danger: true,
    })
    if (!ok) {
      return
    }
    setBusy(true)
    try {
      await logoutEverywhere()
      await logout()
    } catch (err) {
      reportError(err)
      setBusy(false)
    }
  }

  return (
    <div className="set-row">
      <span className="set-label">Все устройства</span>
      <button
        type="button"
        className="link danger"
        onClick={() => void run()}
        disabled={busy}
      >
        Выйти на всех устройствах
      </button>
    </div>
  )
}
