import { z } from "zod"

export const loginSchema = z.object({
  email: z.email("Неверный email"),
  password: z.string().min(1, "Введите пароль"),
})

export type LoginInput = z.infer<typeof loginSchema>
