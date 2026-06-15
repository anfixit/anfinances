import { useMutation, useQueryClient } from "@tanstack/react-query"

import { updateProfile } from "@/features/users/usersApi"
import type { ProfileUpdateInput } from "@/features/users/usersApi"
import { queryKeys } from "@/lib/query/keys"

export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: ProfileUpdateInput) => updateProfile(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.me }),
  })
}
