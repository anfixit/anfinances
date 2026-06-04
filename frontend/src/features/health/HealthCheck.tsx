import { useQuery } from "@tanstack/react-query"

import { fetchHealth } from "@/features/health/healthApi"
import { queryKeys } from "@/lib/query/keys"

export function HealthCheck() {
  const { data, isPending, isError } = useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
  })

  return (
    <main className="page">
      <h1>anfinances</h1>
      <p>Каркас фронта (M0). Проверка связи с API:</p>
      {isPending && <p>Проверяю…</p>}
      {isError && <p className="error">API недоступен</p>}
      {data && <p className="ok">API: {data.status}</p>}
    </main>
  )
}
