// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Candidate, Payee } from "@/features/payees/types"

vi.mock("@/features/categories/hooks", () => ({
  useCategories: () => ({ data: [], isPending: false }),
}))
const confirmMock = vi.fn()
vi.mock("@/components/confirm-context", () => ({
  useConfirm: () => ({ confirm: confirmMock }),
}))

const accept = vi.fn()
const reject = vi.fn()
const unreject = vi.fn()
const removePayee = vi.fn()

let pending: Candidate[]
let queueError = false
let rejectedError = false
let rejected: Candidate[]
let payees: Payee[]

const idle = { mutate: vi.fn(), isPending: false }

vi.mock("@/features/payees/hooks", () => ({
  usePayees: () => ({ data: payees, isPending: false, isError: false }),
  useCandidates: (status: string) => ({
    data: status === "pending" ? pending : rejected,
    isPending: false,
    isError: status === "pending" ? queueError : rejectedError,
  }),
  useAcceptCandidate: () => ({ mutate: accept, isPending: false }),
  useRejectCandidate: () => ({ mutate: reject, isPending: false }),
  useUnrejectCandidate: () => ({ mutate: unreject, isPending: false }),
  useDeletePayee: () => ({ mutate: removePayee, isPending: false }),
  useMergePayees: () => idle,
  useRenamePayee: () => idle,
  useSetPayeeVaried: () => idle,
}))

import { PayeesPage } from "@/features/payees/PayeesPage"

function cand(id: string, name: string, times: number, amount: string) {
  return {
    id,
    name,
    times_seen: times,
    amount,
    first_seen_at: "2026-11-01T00:00:00Z",
    last_seen_at: "2026-11-20T00:00:00Z",
    status: "pending",
  } as Candidate
}

beforeEach(() => {
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  queueError = false
  rejectedError = false
  accept.mockReset()
  reject.mockReset()
  unreject.mockReset()
  removePayee.mockReset()
  pending = [cand("c1", "Кофейня", 3, "1500.00"), cand("c2", "Злата", 1, "300")]
  rejected = []
  payees = [
    {
      id: "p1",
      name: "Пятёрочка",
      last_category_id: null,
      varied_categories: false,
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    },
  ]
})

afterEach(cleanup)

describe("очередь разбора получателей", () => {
  it("показывает имя, число встреч и сумму", () => {
    render(<PayeesPage />)
    expect(
      screen.getByRole("heading", { name: /очередь.*2/i }),
    ).toBeInTheDocument()
    const row = screen.getByText("Кофейня").closest("li") as HTMLElement
    expect(row).toHaveTextContent(/3/)
    expect(row).toHaveTextContent(/1\s?500/)
  })

  it("«В справочник» заводит нового получателя", () => {
    render(<PayeesPage />)
    const row = screen.getByText("Кофейня").closest("li") as HTMLElement
    fireEvent.click(within(row).getByRole("button", { name: "В справочник" }))
    expect(accept).toHaveBeenCalledWith(
      { id: "c1", payeeId: null },
      expect.anything(),
    )
  })

  it("«это тот же, что…» клеит к существующему после подтверждения", async () => {
    render(<PayeesPage />)
    const row = screen.getByText("Кофейня").closest("li") as HTMLElement
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "p1" },
    })
    await vi.waitFor(() => {
      expect(accept).toHaveBeenCalledWith(
        { id: "c1", payeeId: "p1" },
        expect.anything(),
      )
    })
    expect(confirmMock).toHaveBeenCalledTimes(1)
  })

  it("«это тот же, что…» без подтверждения ничего не клеит", async () => {
    confirmMock.mockResolvedValue(false)
    render(<PayeesPage />)
    const row = screen.getByText("Кофейня").closest("li") as HTMLElement
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "p1" },
    })
    await vi.waitFor(() => {
      expect(confirmMock).toHaveBeenCalledTimes(1)
    })
    expect(accept).not.toHaveBeenCalled()
  })

  it("ошибка загрузки очереди видна, а не выглядит как пустая очередь", () => {
    queueError = true
    pending = undefined as unknown as Candidate[]
    render(<PayeesPage />)
    expect(
      screen.getByText("Не удалось загрузить очередь разбора"),
    ).toBeInTheDocument()
  })

  it("ошибка загрузки отклонённых видна", () => {
    rejectedError = true
    rejected = undefined as unknown as Candidate[]
    render(<PayeesPage />)
    expect(
      screen.getByText(/не удалось загрузить список «не магазины»/i),
    ).toBeInTheDocument()
  })

  it("«Не магазин» отклоняет кандидата", () => {
    render(<PayeesPage />)
    const row = screen.getByText("Злата").closest("li") as HTMLElement
    fireEvent.click(within(row).getByRole("button", { name: "Не магазин" }))
    expect(reject).toHaveBeenCalledWith("c2", expect.anything())
  })

  it("пустая очередь — блока нет", () => {
    pending = []
    render(<PayeesPage />)
    expect(screen.queryByText(/очередь/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/не магазины/i)).not.toBeInTheDocument()
  })

  it("отклонённые: свёрнутый список с возвратом в очередь", () => {
    rejected = [{ ...cand("r1", "СБП", 5, "900"), status: "rejected" }]
    render(<PayeesPage />)
    expect(screen.getByText(/не магазины \(1\)/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /вернуть в очередь/i }))
    expect(unreject).toHaveBeenCalledWith("r1", expect.anything())
  })

  it("«Не магазин» у записи справочника удаляет получателя", async () => {
    pending = []
    render(<PayeesPage />)
    expect(
      screen.queryByRole("button", { name: "Удалить" }),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Не магазин" }))
    await vi.waitFor(() => {
      expect(removePayee).toHaveBeenCalledWith("p1", expect.anything())
    })
  })
})
