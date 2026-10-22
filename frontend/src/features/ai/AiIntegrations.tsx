import { useState } from "react"

import { useConfirm } from "@/components/confirm-context"
import {
  useAiConnections,
  useCreatePersonalToken,
  useRevokeConnection,
} from "@/features/ai/hooks"
import { scopesLabel } from "@/features/ai/scopes"
import type { AiConnection, AiScope } from "@/features/ai/types"
import { AppError } from "@/lib/api/errors"
import { formatDate } from "@/lib/datetime"

type Access = "read" | "write"

const ACCESS_SCOPES: Record<Access, AiScope[]> = {
  read: ["finance.read"],
  write: ["finance.read", "finance.write"],
}

/** Раздел настроек «ИИ-интеграции»: подключения и личные токены. */
export function AiIntegrations() {
  const connections = useAiConnections()

  return (
    <div className="card">
      <h2>ИИ-интеграции</h2>
      <p className="set-note">
        Адрес для коннектора в ChatGPT и Claude:{" "}
        <code className="ai-code">{window.location.origin}/mcp</code>.
        Ассистент попросит войти сюда и подтвердить доступ. Удалять
        данные, менять профиль и доступы он не может ни при каких
        правах.
      </p>

      {connections.isPending && <p>Загрузка…</p>}
      {connections.isError && (
        <p className="error">Не удалось загрузить подключения</p>
      )}
      {connections.data?.length === 0 && (
        <p className="set-note">Подключений пока нет.</p>
      )}
      {connections.data && connections.data.length > 0 && (
        <ul className="ai-list">
          {connections.data.map((conn) => (
            <li key={conn.id}>
              <ConnectionRow conn={conn} />
            </li>
          ))}
        </ul>
      )}

      <PersonalTokenForm />
    </div>
  )
}

function ConnectionRow({ conn }: { conn: AiConnection }) {
  const revoke = useRevokeConnection()
  const { confirm } = useConfirm()

  const onRevoke = async () => {
    const ok = await confirm({
      title: `Отозвать доступ «${conn.name}»?`,
      body: [
        conn.kind === "oauth"
          ? "Ассистент сразу потеряет доступ к данным. Чтобы вернуть его, " +
            "подключение придётся пройти заново."
          : "Токен перестанет работать сразу. Вернуть его нельзя — только " +
            "создать новый.",
      ],
      confirmLabel: "Отозвать",
      danger: true,
    })
    if (ok) {
      revoke.mutate(conn.id)
    }
  }

  return (
    <div className="ai-row">
      <div className="ai-row-main">
        <strong>{conn.name}</strong>
        <span className="ai-meta">
          {conn.kind === "oauth" ? "OAuth" : "Личный токен"} ·{" "}
          {scopesLabel(conn.scopes)}
        </span>
        <span className="ai-meta">
          Создано {formatDate(conn.created_at)} · {lastUsed(conn)}
        </span>
      </div>
      <button
        type="button"
        className="link danger"
        onClick={() => void onRevoke()}
        disabled={revoke.isPending}
      >
        Отозвать
      </button>
    </div>
  )
}

function lastUsed(conn: AiConnection): string {
  return conn.last_used_at === null
    ? "ещё не использовалось"
    : `использовалось ${formatDate(conn.last_used_at)}`
}

function PersonalTokenForm() {
  const create = useCreatePersonalToken()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [access, setAccess] = useState<Access>("read")
  const [error, setError] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const submit = () => {
    setError(null)
    if (name.trim() === "") {
      setError("Назовите токен — по имени его потом узнать в списке")
      return
    }
    create.mutate(
      { name: name.trim(), scopes: ACCESS_SCOPES[access] },
      {
        onSuccess: (created) => {
          setToken(created.token)
          setCopied(false)
          setName("")
          setOpen(false)
        },
        onError: (err: unknown) => {
          setError(
            err instanceof AppError ? err.message : "Не удалось создать токен",
          )
        },
      },
    )
  }

  const copy = async () => {
    if (token === null) {
      return
    }
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
    } catch {
      setError("Не удалось скопировать — выделите токен и скопируйте вручную")
    }
  }

  return (
    <div className="ai-token">
      {token !== null && (
        <div className="ai-token-once" role="status">
          <p>
            <strong>Скопируйте токен сейчас.</strong> Больше он показан не
            будет: на сервере хранится только его отпечаток.
          </p>
          <code className="ai-token-value">{token}</code>
          <div className="ai-actions">
            <button type="button" onClick={() => void copy()}>
              {copied ? "Скопировано" : "Скопировать"}
            </button>
            <button
              type="button"
              className="btn-text"
              onClick={() => setToken(null)}
            >
              Готово
            </button>
          </div>
        </div>
      )}

      {!open && (
        <button
          type="button"
          className="btn-tonal"
          onClick={() => {
            setOpen(true)
            setError(null)
          }}
        >
          Создать личный токен
        </button>
      )}

      {open && (
        <div className="form">
          <label className="field">
            <span>Название</span>
            <input
              value={name}
              maxLength={100}
              placeholder="Например, Claude Code на ноутбуке"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div className="field">
            <span>Доступ</span>
            <div className="segmented" role="group" aria-label="Доступ">
              <button
                type="button"
                aria-pressed={access === "read"}
                onClick={() => setAccess("read")}
              >
                Только чтение
              </button>
              <button
                type="button"
                aria-pressed={access === "write"}
                onClick={() => setAccess("write")}
              >
                Чтение и запись
              </button>
            </div>
            <span className="field-hint">
              Запись — это новые операции, бюджеты и цели. Удалять токен не
              сможет ничего.
            </span>
          </div>
          {error && <p className="error">{error}</p>}
          <div className="ai-actions">
            <button
              type="button"
              onClick={submit}
              disabled={create.isPending}
            >
              {create.isPending ? "Создаю…" : "Создать"}
            </button>
            <button
              type="button"
              className="btn-text"
              onClick={() => setOpen(false)}
            >
              Отмена
            </button>
          </div>
        </div>
      )}
      {!open && error && <p className="error">{error}</p>}
    </div>
  )
}
