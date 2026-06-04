import { api } from "@/lib/api/client"

// /health/live — публичный, отвечает вне конверта ApiResponse.
export interface HealthStatus {
  status: string
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await api.get<HealthStatus>("/health/live")
  return res.data
}
