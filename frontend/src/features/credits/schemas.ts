import { z } from "zod"

const positiveMoney = z
  .string()
  .trim()
  .min(1, "Укажите сумму")
  .refine((v) => Number(v) > 0, "Сумма должна быть больше нуля")

const nonNegativeMoney = z
  .string()
  .trim()
  .min(1, "Укажите сумму")
  .refine((v) => Number(v) >= 0, "Сумма не может быть отрицательной")

const optionalMoney = z
  .string()
  .trim()
  .refine(
    (v) => v === "" || Number(v) >= 0,
    "Сумма не может быть отрицательной",
  )


function moneyToMinor(value: string): number {
  return Math.round(Number(value) * 100)
}

const optionalPositiveInteger = z
  .string()
  .trim()
  .refine(
    (v) => v === "" || (Number.isInteger(Number(v)) && Number(v) > 0),
    "Укажите целое число больше нуля",
  )

const optionalPaymentDay = z
  .string()
  .trim()
  .refine(
    (v) =>
      v === "" ||
      (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 31),
    "День платежа должен быть от 1 до 31",
  )

export const creditFormSchema = z.object({
  name: z.string().trim().min(1, "Укажите название"),
  lender: z.string().nullable(),
  currency_code: z.string().length(3, "Выберите валюту"),
  principal_initial: positiveMoney,
  annual_rate: optionalMoney,
  term_months: optionalPositiveInteger,
  start_date: z.string().nullable(),
  payment_day: optionalPaymentDay,
  linked_account_id: z.string().nullable(),
  comments: z.string().nullable(),
})

export const creditPaymentFormSchema = z
  .object({
    payment_account_id: z.string().min(1, "Выберите счёт оплаты"),
    date: z.string().min(1, "Укажите дату"),
    total_amount: positiveMoney,
    principal_amount: nonNegativeMoney,
    interest_amount: nonNegativeMoney,
    fee_amount: nonNegativeMoney,
    interest_category_id: z.string().nullable(),
    fee_category_id: z.string().nullable(),
    comment: z.string().nullable(),
  })
  .refine(
    (data) =>
      moneyToMinor(data.total_amount) ===
      moneyToMinor(data.principal_amount) +
        moneyToMinor(data.interest_amount) +
        moneyToMinor(data.fee_amount),
    {
      message: "Сумма платежа должна равняться телу, процентам и комиссии",
      path: ["total_amount"],
    },
  )
