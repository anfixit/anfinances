import { AxiosError } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Моки объявляем через vi.hoisted: vi.mock поднимается выше импортов.
const { refreshMock, notifyMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(() => Promise.resolve("new-token")),
  notifyMock: vi.fn(),
}))

vi.mock("@/lib/api/refresh", () => ({ refreshAccessToken: refreshMock }))
vi.mock("@/auth/tokenStore", () => ({
  getAccessToken: () => null,
  notifyAuthExpired: notifyMock,
}))

const { api } = await import("@/lib/api/client")

// Адаптер вместо сети: записывает, кого спросили, и всем отвечает 401.
function unauthorized(): string[] {
  const calls: string[] = []
  api.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    calls.push(config.url ?? "")
    const response = {
      status: 401,
      statusText: "Unauthorized",
      data: {},
      headers: {},
      config,
    } as AxiosResponse
    return Promise.reject(
      new AxiosError(
        "Unauthorized",
        AxiosError.ERR_BAD_REQUEST,
        config,
        null,
        response,
      ),
    )
  }
  return calls
}

beforeEach(() => {
  refreshMock.mockClear()
  notifyMock.mockClear()
})

afterEach(() => {
  delete api.defaults.adapter
})

describe("перехватчик 401", () => {
  it("вход не повторяет и сессию не трогает", async () => {
    // 401 на входе — это «неверный пароль», а не «токен протух».
    // Повтор тратил вторую попытку из лимита 10/минуту, и пять
    // опечаток подряд давали 429 вместо понятной ошибки.
    const calls = unauthorized()

    await expect(
      api.post("/auth/login", { email: "a@b.c", password: "wrong" }),
    ).rejects.toBeInstanceOf(Error)

    expect(calls).toEqual(["/auth/login"])
    expect(refreshMock).not.toHaveBeenCalled()
    expect(notifyMock).not.toHaveBeenCalled()
  })

  it("refresh не повторяет, но уводит на вход", async () => {
    const calls = unauthorized()

    await expect(api.post("/auth/refresh")).rejects.toBeInstanceOf(Error)

    expect(calls).toEqual(["/auth/refresh"])
    expect(refreshMock).not.toHaveBeenCalled()
    expect(notifyMock).toHaveBeenCalledTimes(1)
  })

  it("обычный запрос обновляет сессию и повторяет ровно один раз", async () => {
    const calls = unauthorized()

    await expect(api.get("/accounts")).rejects.toBeInstanceOf(Error)

    expect(calls).toEqual(["/accounts", "/accounts"])
    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
