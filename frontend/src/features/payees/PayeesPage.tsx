import { useState } from "react"

import { useConfirm } from "@/components/confirm-context"
import { useCategories } from "@/features/categories/hooks"
import {
  useAcceptCandidate,
  useCandidates,
  useDeletePayee,
  useMergePayees,
  usePayees,
  useRejectCandidate,
  useRenamePayee,
  useSetPayeeVaried,
  useUnrejectCandidate,
} from "@/features/payees/hooks"
import type { Candidate, Payee } from "@/features/payees/types"
import { categoryPath } from "@/features/categories/path"
import { reportError } from "@/lib/errors/reportError"
import { formatMoney } from "@/lib/money"

export function PayeesPage() {
  const payees = usePayees()
  const queue = useCandidates("pending")
  const rejected = useCandidates("rejected")
  const categories = useCategories()

  const catById = new Map((categories.data ?? []).map((c) => [c.id, c]))

  if (payees.isPending) {
    return <p>Загрузка…</p>
  }
  if (payees.isError || !payees.data) {
    return <p className="error">Не удалось загрузить получателей</p>
  }

  return (
    <>
      <h1>Получатели</h1>

      <p className="rec-help">
        Кому уходят деньги. За каждым получателем сайт запоминает
        категорию последней операции и подставляет её в следующий раз —
        поэтому выписки разносятся сами. Там, где покупают всё подряд,
        отметьте «разные категории»: память им только мешает. Ozon,
        Wildberries и Яндекс Маркет отмечаются сами.
      </p>

      {queue.data && queue.data.length > 0 && (
        <CandidateQueue items={queue.data} payees={payees.data} />
      )}

      {rejected.data && rejected.data.length > 0 && (
        <RejectedList items={rejected.data} />
      )}

      {payees.data.length === 0 && (
        <p>
          Получателей пока нет. Они появятся сами, как только вы
          укажете магазин при вводе траты.
        </p>
      )}

      <ul className="tree">
        {payees.data.map((payee) => (
          <li key={payee.id}>
            <PayeeRow
              payee={payee}
              hint={categoryPath(catById, payee.last_category_id)}
              all={payees.data ?? []}
            />
          </li>
        ))}
      </ul>
    </>
  )
}

function PayeeRow({
  payee,
  hint,
  all,
}: {
  payee: Payee
  hint: string | null
  all: Payee[]
}) {
  const rename = useRenamePayee()
  const merge = useMergePayees()
  const remove = useDeletePayee()
  const varied = useSetPayeeVaried()
  const { confirm } = useConfirm()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(payee.name)
  const [mergeInto, setMergeInto] = useState("")

  const onMerge = async () => {
    const target = all.find((p) => p.id === mergeInto)
    if (target === undefined) {
      return
    }
    const ok = await confirm({
      title: `Слить «${payee.name}» в «${target.name}»?`,
      body: [
        "Все операции первого получателя перевесятся на второго, а " +
          "он сам удалится.",
        "Отменить одним действием не получится.",
      ],
      confirmLabel: "Слить",
      danger: true,
    })
    if (ok) {
      merge.mutate(
        { sourceId: payee.id, targetId: target.id },
        { onError: reportError },
      )
    }
  }

  const onNotShop = async () => {
    const ok = await confirm({
      title: `«${payee.name}» — не магазин?`,
      body: [
        "Получатель исчезнет из справочника, имя на операциях " +
          "останется, и в очередь оно больше не попадёт. Если " +
          "понадобится, вернёте его кнопкой «вернуть в очередь» " +
          "в списке «Не магазины».",
      ],
      confirmLabel: "Не магазин",
      danger: true,
    })
    if (ok) {
      remove.mutate(payee.id, { onError: reportError })
    }
  }

  if (editing) {
    return (
      <span className="row payee-row">
        <input
          className="payee-edit__input"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          type="button"
          disabled={rename.isPending}
          onClick={() =>
            rename.mutate(
              { id: payee.id, name },
              { onSuccess: () => setEditing(false), onError: reportError },
            )
          }
        >
          Сохранить
        </button>
        <button
          type="button"
          className="link"
          onClick={() => setEditing(false)}
        >
          Отмена
        </button>
      </span>
    )
  }

  return (
    <span className="row payee-row">
      <span className="payee-info">
        <span className="payee-name">
          <span className="payee-name__text">{payee.name}</span>
        </span>
        <span className="acc-meta">
          {payee.varied_categories
            ? "категория зависит от покупки"
            : (hint ?? "категория не запомнена")}
        </span>
        <label className="payee-varied">
          <input
            type="checkbox"
            checked={payee.varied_categories}
            disabled={varied.isPending}
            onChange={(e) => {
              varied.mutate(
                { id: payee.id, varied: e.target.checked },
                { onError: reportError },
              )
            }}
          />
          разные категории
        </label>
      </span>
      <select
        className="payee-merge"
        value={mergeInto}
        onChange={(e) => {
          setMergeInto(e.target.value)
        }}
      >
        <option value="">Слить в…</option>
        {all
          .filter((p) => p.id !== payee.id)
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
      </select>
      <span className="payee-actions">
        <button
          type="button"
          className="link"
          disabled={mergeInto === "" || merge.isPending}
          onClick={() => {
            void onMerge()
          }}
        >
          Слить
        </button>
        <button type="button" className="link" onClick={() => setEditing(true)}>
          Переименовать
        </button>
        <button
          type="button"
          className="link"
          disabled={remove.isPending}
          onClick={() => {
            void onNotShop()
          }}
        >
          Не магазин
        </button>
      </span>
    </span>
  )
}

function CandidateQueue({
  items,
  payees,
}: {
  items: Candidate[]
  payees: Payee[]
}) {
  return (
    <div className="card">
      <h2>Очередь разбора ({items.length})</h2>
      <p className="allowance-note">
        Эти имена встретились в выписках, но в справочнике их нет. Если это
        магазин — добавьте; если человек или слово из назначения платежа — «Не
        магазин».
      </p>
      <ul className="tree">
        {items.map((c) => (
          <li key={c.id}>
            <CandidateRow candidate={c} payees={payees} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function CandidateRow({
  candidate,
  payees,
}: {
  candidate: Candidate
  payees: Payee[]
}) {
  const accept = useAcceptCandidate()
  const reject = useRejectCandidate()
  const busy = accept.isPending || reject.isPending

  return (
    <span className="row payee-row">
      <span className="payee-info">
        <span className="payee-name">
          <span className="payee-name__text">{candidate.name}</span>
        </span>
        <span className="acc-meta">
          встретилось {candidate.times_seen} ·{" "}
          {formatMoney(candidate.amount, "RUB")}
        </span>
      </span>
      <select
        className="payee-merge"
        aria-label="Это тот же, что…"
        value=""
        disabled={busy}
        onChange={(e) => {
          if (e.target.value !== "") {
            accept.mutate(
              { id: candidate.id, payeeId: e.target.value },
              { onError: reportError },
            )
          }
        }}
      >
        <option value="">Это тот же, что…</option>
        {payees.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <span className="payee-actions">
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            accept.mutate(
              { id: candidate.id, payeeId: null },
              { onError: reportError },
            )
          }}
        >
          В справочник
        </button>
        <button
          type="button"
          className="link"
          disabled={busy}
          onClick={() => {
            reject.mutate(candidate.id, { onError: reportError })
          }}
        >
          Не магазин
        </button>
      </span>
    </span>
  )
}

function RejectedList({ items }: { items: Candidate[] }) {
  const unreject = useUnrejectCandidate()

  return (
    <details className="card payee-rejected">
      <summary>Не магазины ({items.length})</summary>
      <ul className="tree">
        {items.map((c) => (
          <li key={c.id}>
            <span className="row payee-row">
              <span className="payee-info">
                <span className="payee-name">
                  <span className="payee-name__text">{c.name}</span>
                </span>
              </span>
              <button
                type="button"
                className="link"
                disabled={unreject.isPending}
                onClick={() => {
                  unreject.mutate(c.id, { onError: reportError })
                }}
              >
                вернуть в очередь
              </button>
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}
