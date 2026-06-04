import { useAuth } from "@/auth/useAuth"

export function HomePage() {
  const { user, logout } = useAuth()

  return (
    <main className="page">
      <h1>anfinances</h1>
      <p>Вы вошли как {user?.email}.</p>
      <p>M1 — каркас auth готов. Дальше: справочники, транзакции.</p>
      <button type="button" onClick={() => void logout()}>
        Выйти
      </button>
    </main>
  )
}
