import { z } from "zod"

const positiveMoney = z
  .string()
  .trim()
  .min(1, "Укажите сумму")
  .refine((v) => Number(v) > 0, "Сумма должна быть больше нуля")

export const ordinaryTxSchema = z.object({
  account_id: z.string().min(1, "Выберите счёт"),
  amount: positiveMoney,
  date: z.string().min(1, "Укажите дату"),
  category_id: z.string().nullable(),
  required: z.enum(["required", "optional"]).nullable(),
  comment: z.string().nullable(),
})

export const transferTxSchema = z
  .object({
    from_account_id: z.string().min(1, "Выберите счёт списания"),
    to_account_id: z.string().min(1, "Выберите счёт зачисления"),
    amount_from: positiveMoney,
    amount_to: positiveMoney,
    date: z.string().min(1, "Укажите дату"),
    fee_amount: z.string().nullable(),
    fee_category_id: z.string().nullable(),
    comment: z.string().nullable(),
  })
  .refine((d) => d.from_account_id !== d.to_account_id, {
    message: "Счёт списания и зачисления должны различаться",
    path: ["to_account_id"],
  })
