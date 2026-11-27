import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Моки объявляем через vi.hoisted: vi.mock поднимается выше импортов.
const { postMock, setTokenMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  setTokenMock: vi.fn(),
}))

vi.mock("axios", () => ({
  default: { create: () => ({ post: postMock }) },
}))
vi.mock("@/auth/tokenStore", () => ({ setAccessToken: setTokenMock }))

const { refreshAccessToken } = await import("@/lib/api/refresh")

function answers(token: string): void {
  postMock.mockResolvedValue({ data: { data: { access_token: token } } })
}

beforeEach(() => {
  postMock.mockReset()
  setTokenMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("обновление сессии", () => {
  it("параллельные вызовы делят один запрос", async () => {
    // Два запроса, получившие 401 одновременно, не должны слать два
    // refresh: cookie у них одна, и сервер принял бы второй за кражу
    // токена — то есть разлогинил бы все устройства.
    answers("t1")

    const both = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
    ])

    expect(postMock).toHaveBeenCalledTimes(1)
    expect(postMock).toHaveBeenCalledWith("/auth/refresh")
    expect(both).toEqual(["t1", "t1"])
    expect(setTokenMock).toHaveBeenCalledWith("t1")
  })

  it("следующее обновление идёт в сеть заново", async () => {
    // Иначе вкладка навсегда осталась бы с первым токеном.
    answers("t1")

    await refreshAccessToken()
    await refreshAccessToken()

    expect(postMock).toHaveBeenCalledTimes(2)
  })

  it("провал не запирает обновление навсегда", async () => {
    postMock.mockRejectedValueOnce(new Error("нет сети"))

    await expect(refreshAccessToken()).rejects.toThrow("нет сети")

    answers("t2")

    await expect(refreshAccessToken()).resolves.toBe("t2")
    expect(postMock).toHaveBeenCalledTimes(2)
  })

  it("между вкладками идёт под общим замком", async () => {
    // Вкладка, дождавшаяся замка, шлёт запрос уже с новой cookie,
    // поэтому запрос обязан быть внутри замка, а не рядом с ним.
    const order: string[] = []
    postMock.mockImplementation(() => {
      order.push("запрос")
      return Promise.resolve({ data: { data: { access_token: "t3" } } })
    })
    vi.stubGlobal("navigator", {
      locks: {
        request: async (name: string, body: () => Promise<string>) => {
          order.push(`замок:${name}`)
          const result = await body()
          order.push("замок отпущен")
          return result
        },
      },
    })

    await expect(refreshAccessToken()).resolves.toBe("t3")

    expect(order).toEqual([
      "замок:anfinances-refresh",
      "запрос",
      "замок отпущен",
    ])
  })
})
