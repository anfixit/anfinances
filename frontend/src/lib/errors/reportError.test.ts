import { describe, expect, it } from "vitest"

import { AppError } from "@/lib/api/errors"
import { reportError, subscribeToErrors } from "@/lib/errors/reportError"

describe("reportError", () => {
  it("передаёт подписчику текст ошибки сервера", () => {
    const seen: string[] = []
    const stop = subscribeToErrors((m) => seen.push(m))

    reportError(
      new AppError({
        code: "VALIDATION_ERROR",
        message: "Счёт «Старая карта» в архиве",
      }),
    )
    stop()

    expect(seen).toEqual(["Счёт «Старая карта» в архиве"])
  })

  it("на сетевую ошибку показывает понятный текст", () => {
    const seen: string[] = []
    const stop = subscribeToErrors((m) => seen.push(m))

    reportError(new TypeError("Failed to fetch"))
    stop()

    expect(seen[0]).toContain("Проверьте связь")
  })

  it("после отписки сообщений не шлёт", () => {
    const seen: string[] = []
    subscribeToErrors((m) => seen.push(m))()

    reportError(new Error("x"))

    expect(seen).toEqual([])
  })
})
