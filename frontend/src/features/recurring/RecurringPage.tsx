import { useState } from "react"

import { useCategories } from "@/features/categories/hooks"
import { RecurringForm } from "@/features/recurring/RecurringForm"
import { buildRecurringPlanSummary } from "@/features/recurring/planSummary"
import {
  useArchiveRecurring,
  useGenerateFromCategories,
  usePreviewGeneration,
  useRecurring,
} from "@/features/recurring/hooks"
import type { RecurringGenerationProposal } from "@/features/recurring/recurringApi"
import type { Recurring } from "@/features/recurring/types"
import { Sheet } from "@/components/Sheet"
import { useConfirm } from "@/components/confirm-context"
import { formatMoney } from "@/lib/money"

export function RecurringPage() {
  const { confirm, notify } = useConfirm()
  const recurring = useRecurring()
  const categoriesQ = useCategories()
  const archive = useArchiveRecurring()
  const preview = usePreviewGeneration()
  const generate = useGenerateFromCategories()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editing, setEditing] = useState<Recurring | null>(null)

  const catById = new Map((categoriesQ.data ?? []).map((c) => [c.id, c]))
  const items = recurring.data ?? []
  const planSummary = buildRecurringPlanSummary(
    items,
    categoriesQ.data ?? [],
  )
  const exceededCategories = planSummary.categories.filter(
    (category) => category.isExceeded,
  )

  const openCreate = () => {
    setEditing(null)
    setSheetOpen(true)
  }
  const openEdit = (item: Recurring) => {
    setEditing(item)
    setSheetOpen(true)
  }
  const close = () => {
    setSheetOpen(false)
  }

  const remove = async (item: Recurring) => {
    const ok = await confirm({
      title: `Убрать «${item.name}» из плана-минимума?`,
      body: [
        "Эта сумма перестанет резервироваться — дневной лимит " +
          "вырастет, хотя платить всё равно придётся.",
      ],
      confirmLabel: "Убрать из плана",
      danger: true,
    })
    if (ok) {
      archive.mutate(item.id)
    }
  }

  const onGenerate = () => {
    preview.mutate(undefined, {
      onSuccess: (proposals) => {
        void proposeAndGenerate(proposals)
      },
    })
  }

  const proposeAndGenerate = async (proposals: RecurringGenerationProposal[]) => {
    if (proposals.length === 0) {
      await notify({
        title: "Добавлять нечего",
        body:
          "Все категории с регулярными тратами уже есть в " +
          "плане-минимуме.",
      })
      return
    }

    const lines = proposals.map(
      (proposal) =>
        `${proposal.category_path}: ${formatMoney(
          proposal.monthly_amount,
          proposal.currency_code,
        )}`,
    )
    const ok = await confirm({
      title: `Добавить в план-минимум записей: ${String(lines.length)}?`,
      body: ["Будут добавлены:", ...lines],
      confirmLabel: "Добавить",
    })
    if (!ok) {
      return
    }

    generate.mutate(
      proposals.map((proposal) => proposal.category_id),
      {
        onSuccess: (created) => {
          void notify({
            title: `Добавлено записей: ${String(created.length)}`,
            body: "Проверьте суммы — план считается по прошлым тратам.",
          })
        },
      },
    )
  }

  return (
    <>
      <div className="page-head">
        <h1>План-минимум</h1>
        <button type="button" onClick={openCreate}>
          + Добавить
        </button>
      </div>

      <p className="rec-help">
        Обязательные ежемесячные траты по категориям. Итого в месяц:{" "}
        <strong className="num">
          {formatMoney(String(planSummary.totalRub), "RUB")}
        </strong>
      </p>

      {exceededCategories.length > 0 && (
        <div className="rec-warning" role="status">
          Детализация превышает общий план: {" "}
          {exceededCategories
            .map((category) => category.categoryName)
            .join(", ")}.
        </div>
      )}

      <p>
        <button
          type="button"
          className="btn-outline"
          onClick={onGenerate}
          disabled={preview.isPending || generate.isPending}
        >
          {preview.isPending || generate.isPending
            ? "Считаю…"
            : "Сгенерировать из категорий"}
        </button>
      </p>

      {recurring.isPending && <p>Загрузка…</p>}
      {recurring.isError && <p className="error">Не удалось загрузить план</p>}
      {recurring.isSuccess && items.length === 0 && (
        <p>План пуст. Добавьте обязательные траты или сгенерируйте из истории.</p>
      )}

      <ul className="rec-list">
        {items.map((item) => {
          const cat = catById.get(item.category_id)
          const parent =
            cat?.parent_id === null || cat?.parent_id === undefined
              ? undefined
              : catById.get(cat.parent_id)
          const categoryPath =
            parent === undefined
              ? (cat?.name ?? "—")
              : `${parent.name} → ${cat?.name ?? "—"}`
          const showRub =
            item.currency_code !== "RUB" && item.amount_rub !== null
          return (
            <li key={item.id} className="rec-row">
              <div className="rec-info">
                <span className="rec-name">{item.name}</span>
                <span className="rec-meta">
                  {categoryPath}
                  {item.required === "optional" ? " · необязательный" : ""}
                </span>
              </div>
              <span className="num rec-amount">
                {formatMoney(item.monthly_amount ?? "0", item.currency_code ?? "RUB")}
                {showRub && (
                  <span className="rec-rub">
                    {" "}
                    ({formatMoney(item.amount_rub ?? "0", "RUB")})
                  </span>
                )}
              </span>
              <button
                type="button"
                className="link"
                onClick={() => openEdit(item)}
              >
                Изменить
              </button>
              <button
                type="button"
                className="link danger"
                onClick={() => {
                  void remove(item)
                }}
              >
                Убрать
              </button>
            </li>
          )
        })}
      </ul>

      <Sheet
        open={sheetOpen}
        title={editing ? "Изменить платёж" : "Новый регулярный платёж"}
        onClose={close}
      >
        <RecurringForm
          key={editing?.id ?? "new"}
          item={editing}
          onDone={close}
        />
      </Sheet>
    </>
  )
}
