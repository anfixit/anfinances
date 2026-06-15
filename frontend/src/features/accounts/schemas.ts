import { z } from "zod"

export const accountFormSchema = z.object({
  name: z.string().trim().min(1, "Укажите название"),
  type: z.enum(["card", "cash", "card_credit", "savings", "investment"]),
  currency_code: z.string().trim().min(3, "Выберите валюту"),
  initial_balance: z
    .string()
    .trim()
    .refine((v) => v === "" || !Number.isNaN(Number(v)), "Должно быть числом"),
  credit_limit: z
    .string()
    .trim()
    .refine((v) => v === "" || Number(v) > 0, "Должно быть больше нуля"),
  sort_order: z
    .string()
    .trim()
    .refine((v) => v === "" || Number.isInteger(Number(v)), "Целое число"),
  color: z.string(),
  comments: z.string(),
})

export type AccountFormValues = z.infer<typeof accountFormSchema>
