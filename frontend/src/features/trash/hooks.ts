import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { listTrash, restoreFromTrash } from "@/features/trash/trashApi"
import { queryKeys } from "@/lib/query/keys"

export function useTrash() {
  return useQuery({
    queryKey: queryKeys.trash,
    queryFn: listTrash,
  })
}

export function useRestoreFromTrash() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => restoreFromTrash(id),
    onSuccess: () => {
      // Вернулась операция, перевод или платёж — меняются остатки,
      // сводка, бюджет и долг по кредиту.
      void qc.invalidateQueries({ queryKey: queryKeys.trash })
      void qc.invalidateQueries({ queryKey: ["transactions"] })
      void qc.invalidateQueries({ queryKey: ["transfers"] })
      void qc.invalidateQueries({ queryKey: ["summary"] })
      void qc.invalidateQueries({ queryKey: ["budgets"] })
      void qc.invalidateQueries({ queryKey: queryKeys.accounts })
      void qc.invalidateQueries({ queryKey: queryKeys.credits })
    },
  })
}
