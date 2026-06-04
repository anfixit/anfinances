import type {
  ByCategory,
  Cashflow,
  Dashboard,
} from "@/features/summary/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export async function getDashboard(): Promise<Dashboard> {
  return unwrap(await api.get<ApiResponse<Dashboard>>("/summary/dashboard"))
}

export async function getCashflow(
  from: string,
  to: string,
): Promise<Cashflow> {
  return unwrap(
    await api.get<ApiResponse<Cashflow>>("/summary/cashflow", {
      params: { from, to },
    }),
  )
}

export async function getByCategory(month: string): Promise<ByCategory> {
  return unwrap(
    await api.get<ApiResponse<ByCategory>>("/summary/by-category", {
      params: { month },
    }),
  )
}
