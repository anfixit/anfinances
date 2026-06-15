import { useState } from "react"

import {
  exportAllJson,
  exportTransactionsCsv,
  exportTransactionsXlsx,
} from "@/features/backup/backupApi"
import type { ImportResult } from "@/features/backup/backupApi"
import { useImportAll } from "@/features/backup/hooks"
import { AppError } from "@/lib/api/errors"

export function BackupPage() {
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [busy, setBusy] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const importAll = useImportAll()

  const runExport = (fn: () => Promise<void>) => {
    setExportError(null)
    setBusy(true)
    fn()
      .catch((err: unknown) => {
        setExportError(
          err instanceof AppError ? err.message : "Не удалось выгрузить",
        )
      })
      .finally(() => {
        setBusy(false)
      })
  }

  const restore = async () => {
    setRestoreError(null)
    setResult(null)
    if (!file) {
      setRestoreError("Выберите файл бэкапа")
      return
    }
    let bundle: unknown
    try {
      bundle = JSON.parse(await file.text())
    } catch {
      setRestoreError("Файл не является корректным JSON")
      return
    }
    importAll.mutate(bundle, {
      onSuccess: (res) => {
        setResult(res)
      },
      onError: (err: unknown) => {
        setRestoreError(
          err instanceof AppError ? err.message : "Не удалось восстановить",
        )
      },
    })
  }

  return (
    <>
      <h1>Данные и резервная копия</h1>

      <div className="card">
        <h2>Экспорт</h2>
        <div className="filters-row">
          <label className="field">
            <span>С даты</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label className="field">
            <span>По дату</span>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        </div>
        <p className="backup-hint">
          Период применяется к выгрузке операций (CSV/XLSX). Полный бэкап
          выгружается целиком.
        </p>
        <div className="backup-actions">
          <button
            type="button"
            className="btn-tonal"
            disabled={busy}
            onClick={() => runExport(() => exportTransactionsCsv(from, to))}
          >
            Скачать CSV
          </button>
          <button
            type="button"
            className="btn-tonal"
            disabled={busy}
            onClick={() => runExport(() => exportTransactionsXlsx(from, to))}
          >
            Скачать XLSX
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => runExport(() => exportAllJson())}
          >
            Скачать полный бэкап (JSON)
          </button>
        </div>
        {exportError && <p className="error">{exportError}</p>}
      </div>

      <div className="card">
        <h2>Восстановление</h2>
        <p className="backup-hint">
          Загрузите ранее выгруженный файл{" "}
          <code>anfinances-backup.json</code>. Импорт выполняется одной
          транзакцией: при ошибке ничего не сохранится.
        </p>
        <input
          type="file"
          accept="application/json,.json"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <div className="backup-actions">
          <button
            type="button"
            onClick={() => void restore()}
            disabled={importAll.isPending}
          >
            {importAll.isPending ? "Восстанавливаю…" : "Восстановить из бэкапа"}
          </button>
        </div>
        {restoreError && <p className="error">{restoreError}</p>}
        {result && (
          <div className="restore-result">
            <p className="ok">Восстановлено:</p>
            <ul>
              {Object.entries(result).map(([key, count]) => (
                <li key={key}>
                  {key}: {count}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </>
  )
}
