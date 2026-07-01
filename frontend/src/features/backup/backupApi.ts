import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export type ImportResult = Record<string, number>

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function rangeParams(from: string, to: string): Record<string, string> {
  const params: Record<string, string> = {}
  if (from) {
    params.from = from
  }
  if (to) {
    params.to = to
  }
  return params
}

export async function exportTransactionsCsv(
  from: string,
  to: string,
): Promise<void> {
  const res = await api.get<Blob>("/export/transactions.csv", {
    params: rangeParams(from, to),
    responseType: "blob",
  })
  triggerDownload(res.data, "transactions.csv")
}

export async function exportTransactionsXlsx(
  from: string,
  to: string,
): Promise<void> {
  const res = await api.get<Blob>("/export/transactions.xlsx", {
    params: rangeParams(from, to),
    responseType: "blob",
  })
  triggerDownload(res.data, "transactions.xlsx")
}

export async function exportAllJson(): Promise<void> {
  const res = await api.get<Blob>("/export/all.json", {
    responseType: "blob",
  })
  triggerDownload(res.data, "anfinances-backup.json")
}

export async function importAll(bundle: unknown): Promise<ImportResult> {
  return unwrap(await api.post<ApiResponse<ImportResult>>("/import/all", bundle))
}
