import { useMutation, useQueryClient } from "@tanstack/react-query"

import { useAuth } from "@/auth/useAuth"
import { updateProfile } from "@/features/users/usersApi"
import type { ProfileUpdateInput } from "@/features/users/usersApi"

export function useUpdateProfile() {
  const qc = useQueryClient()
  const { updateUser } = useAuth()
  return useMutation({
    mutationFn: (input: ProfileUpdateInput) => updateProfile(input),
    onSuccess: (user) => {
      // Ответ сервера — уже сохранённый профиль: кладём его в контекст,
      // иначе радиокнопка основной валюты и поля настроек показывали
      // старое, а следующее сохранение откатывало часовой пояс.
      updateUser(user)
      // От пояса и основной валюты зависят все суммы и границы месяцев.
      void qc.invalidateQueries()
    },
  })
}
