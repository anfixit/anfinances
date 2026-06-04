import { z } from "zod"

export const categoryFormSchema = z.object({
  name: z.string().min(1, "Введите название"),
  kind: z.enum(["expense", "income"]),
  parent_id: z.string(),
})

export type CategoryFormInput = z.infer<typeof categoryFormSchema>
