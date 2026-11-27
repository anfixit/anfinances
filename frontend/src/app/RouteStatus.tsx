import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom"

/** Адреса, которого нет: раньше — английская заглушка react-router. */
export function NotFoundPage() {
  return (
    <div className="card">
      <h1>Такой страницы нет</h1>
      <p className="set-note">Возможно, адрес набран с опечаткой.</p>
      <Link className="link" to="/">
        На обзор
      </Link>
    </div>
  )
}

/** Ошибка при отрисовке или загрузке страницы. */
export function RouteErrorPage() {
  const error = useRouteError()
  // Часть приложения не догрузилась — чаще всего после деплоя, когда
  // старая вкладка просит файл прошлой сборки. Лечится перезагрузкой.
  const stale =
    error instanceof TypeError &&
    /dynamically imported module|Importing a module script/i.test(
      error.message,
    )
  const missing = isRouteErrorResponse(error) && error.status === 404

  return (
    <main className="page">
      <div className="card">
        <h1>{missing ? "Такой страницы нет" : "Что-то пошло не так"}</h1>
        <p className="set-note">
          {stale
            ? "Вышла новая версия сайта — обновите страницу."
            : "Попробуйте обновить страницу. Если не поможет — вернитесь на обзор."}
        </p>
        <p>
          <button
            type="button"
            onClick={() => {
              window.location.reload()
            }}
          >
            Обновить страницу
          </button>{" "}
          <Link className="link" to="/">
            На обзор
          </Link>
        </p>
      </div>
    </main>
  )
}
