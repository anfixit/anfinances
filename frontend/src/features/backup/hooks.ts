import { useMutation, useQueryClient } from "@tanstack/react-query"

import { importAll } from "@/features/backup/backupApi"

export function useImportAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (bundle: unknown) => importAll(bundle),
    // Полное восстановление меняет всё — сбрасываем весь кэш.
    onSuccess: () => qc.invalidateQueries(),
  })
}
