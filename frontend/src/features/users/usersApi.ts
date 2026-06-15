import type { User } from "@/auth/types"
import { api, unwrap } from "@/lib/api/client"
import type { ApiResponse } from "@/types/api"

export interface ProfileUpdateInput {
  name?: string
  timezone?: string
  default_currency?: string
  locale?: string
}

export async function updateProfile(
  input: ProfileUpdateInput,
): Promise<User> {
  return unwrap(await api.patch<ApiResponse<User>>("/users/me", input))
}
