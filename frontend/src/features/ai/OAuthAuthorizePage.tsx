import { useMemo, useState } from "react"
import { Navigate, useLocation, useSearchParams } from "react-router-dom"

import { useAuth } from "@/auth/useAuth"
import { approveAuthorization } from "@/features/ai/aiApi"
import { useAuthorizeCheck } from "@/features/ai/hooks"
import { authorizeParamsFrom } from "@/features/ai/scopes"
import type { AiScope, AuthorizeCheck } from "@/features/ai/types"
import { AppError } from "@/lib/api/errors"

/** Страница согласия OAuth: сюда ассистент присылает пользователя.
 *
 * Сама ничего не решает: запрос проверяет бэкенд, он же собирает
 * адрес возврата — и с кодом, и с отказом. Страница только
 * показывает, кто просит и что, и уводит туда, куда сказал сервер.
 */
export function OAuthAuthorizePage() {
  const { status } = useAuth()
  const location = useLocation()
  const [search] = useSearchParams()
  const params = useMemo(() => authorizeParamsFrom(search), [search])
  const check = useAuthorizeCheck(params, status === "authenticated")

  if (status === "unauthenticated") {
    // После входа вернёмся сюда же, с тем же запросом.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    )
  }

  return (
    <main className="page login-page">
      <div className="login-card oauth-card">
        <p className="login-brand">anfinances</p>
        {(status === "loading" || check.isPending) && <p>Проверяю запрос…</p>}
        {check.isError && (
          <p className="error">
            Не удалось проверить запрос. Обновите страницу или начните
            подключение в ассистенте заново.
          </p>
        )}
        {check.data?.status === "error" && <CheckError check={check.data} />}
        {check.data?.status === "ok" && (
          <Consent check={check.data} params={params} />
        )}
      </div>
    </main>
  )
}

function CheckError({ check }: { check: AuthorizeCheck }) {
  return (
    <>
      <h1>Доступ не выдан</h1>
      <p className="error">{check.message}</p>
      {check.redirect_to !== null && (
        <button
          type="button"
          onClick={() => window.location.assign(check.redirect_to ?? "")}
        >
          Вернуться в приложение
        </button>
      )}
    </>
  )
}

function Consent({
  check,
  params,
}: {
  check: AuthorizeCheck
  params: ReturnType<typeof authorizeParamsFrom>
}) {
  const canWrite = check.scopes.includes("finance.write")
  // Запись — только если её включили руками: случайное «Разрешить»
  // не должно давать ассистенту права менять данные.
  const [write, setWrite] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const allow = async () => {
    setBusy(true)
    setError(null)
    const scopes: AiScope[] = write
      ? ["finance.read", "finance.write"]
      : ["finance.read"]
    try {
      window.location.assign(await approveAuthorization(params, scopes))
    } catch (err) {
      setBusy(false)
      setError(
        err instanceof AppError ? err.message : "Не удалось выдать доступ",
      )
    }
  }

  const deny = () => {
    setBusy(true)
    window.location.assign(check.deny_redirect_to ?? "/")
  }

  return (
    <>
      <h1>{check.client_name} просит доступ к anfinances</h1>
      <p className="login-lead">
        После согласия код доступа уйдёт на{" "}
        <strong>{check.redirect_host}</strong>. Разрешайте, только если
        подключение начали вы сами.
      </p>
      <div className="form">
        <label className="oauth-scope">
          <input type="checkbox" checked disabled />
          <span>Читать данные</span>
        </label>
        {canWrite && (
          <label className="oauth-scope">
            <input
              type="checkbox"
              checked={write}
              onChange={(e) => setWrite(e.target.checked)}
            />
            <span>Записывать операции, бюджеты и цели</span>
          </label>
        )}
        <p className="field-hint">
          Удалять данные, менять профиль и доступы ассистент не сможет.
          Отозвать доступ можно в любой момент в Настройках.
        </p>
        {error && <p className="error">{error}</p>}
        <div className="ai-actions">
          <button type="button" onClick={() => void allow()} disabled={busy}>
            Разрешить
          </button>
          <button
            type="button"
            className="btn-outline"
            onClick={deny}
            disabled={busy}
          >
            Отказать
          </button>
        </div>
      </div>
    </>
  )
}
