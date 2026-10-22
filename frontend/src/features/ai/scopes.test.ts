import { describe, expect, it } from "vitest"

import {
  authorizeParamsFrom,
  safeReturnPath,
  scopesLabel,
} from "@/features/ai/scopes"

describe("authorizeParamsFrom", () => {
  it("берёт только параметры OAuth и ничего не придумывает", () => {
    const search = new URLSearchParams(
      "client_id=https%3A%2F%2Fclaude.ai%2Fx&state=s1&extra=1&scope=",
    )
    expect(authorizeParamsFrom(search)).toEqual({
      client_id: "https://claude.ai/x",
      state: "s1",
      scope: "",
    })
  })
})

describe("scopesLabel", () => {
  it("запись включает чтение", () => {
    expect(scopesLabel(["finance.read"])).toBe("Только чтение")
    expect(scopesLabel(["finance.read", "finance.write"])).toBe(
      "Чтение и запись",
    )
  })
})

describe("safeReturnPath", () => {
  it("пропускает только свои пути", () => {
    expect(safeReturnPath("/oauth/authorize?client_id=x")).toBe(
      "/oauth/authorize?client_id=x",
    )
    expect(safeReturnPath("//evil.example/x")).toBe("/")
    expect(safeReturnPath("/\\evil.example")).toBe("/")
    expect(safeReturnPath("https://evil.example")).toBe("/")
    expect(safeReturnPath(undefined)).toBe("/")
  })
})
