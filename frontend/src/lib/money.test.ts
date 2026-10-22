import { describe, expect, it } from "vitest"

import { normalizeAmount } from "@/lib/money"

const NBSP = String.fromCharCode(0xa0)
const NARROW_NBSP = String.fromCharCode(0x202f)
const MINUS = String.fromCharCode(0x2212)

describe("normalizeAmount", () => {
  it("запятая и точка — одинаково", () => {
    expect(normalizeAmount("1234,56")).toBe("1234.56")
    expect(normalizeAmount("1234.56")).toBe("1234.56")
  })

  it("запятая посреди ввода не ломает поле", () => {
    expect(normalizeAmount("12,")).toBe("12.")
  })

  it("пробелы между разрядами, в том числе неразрывные из банка", () => {
    expect(normalizeAmount("1 234,56")).toBe("1234.56")
    expect(normalizeAmount(`1${NBSP}234${NARROW_NBSP}567,8`)).toBe("1234567.8")
  })

  it("остаток по кредитке — с минусом, и с типографским тоже", () => {
    expect(normalizeAmount("-30 683,59")).toBe("-30683.59")
    expect(normalizeAmount(`${MINUS}30 683,59`)).toBe("-30683.59")
  })

  it("точка и запятая вместе — последний знак десятичный", () => {
    expect(normalizeAmount("1.234,56")).toBe("1234.56")
    expect(normalizeAmount("1,234.56")).toBe("1234.56")
  })

  it("целое число не трогает", () => {
    expect(normalizeAmount("300")).toBe("300")
  })
})
