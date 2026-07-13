import { useMemo, useState } from "react"

import { Sheet } from "@/components/Sheet"
import { useAccounts } from "@/features/accounts/hooks"
import { CreditForm } from "@/features/credits/CreditForm"
import { CreditPaymentForm } from "@/features/credits/CreditPaymentForm"
import {
  useArchiveCredit,
  useCreditPayments,
  useCredits,
} from "@/features/credits/hooks"
import type { Credit } from "@/features/credits/types"
import { formatDate } from "@/lib/datetime"
import { formatMoney } from "@/lib/money"

function percentPaid(credit: Credit): number {
  const initial = Number(credit.principal_initial)
  if (initial <= 0) {
    return 0
  }
  const paid = initial - Number(credit.principal_balance)
  return Math.min(100, Math.max(0, (paid / initial) * 100))
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 1,
  }).format(value)
}

function creditMeta(credit: Credit): string {
  const parts = [credit.currency_code]
  if (credit.lender) {
    parts.push(credit.lender)
  }
  if (credit.annual_rate !== null) {
    parts.push(`${formatPercent(Number(credit.annual_rate))}% годовых`)
  }
  if (credit.term_months !== null) {
    parts.push(`${credit.term_months} мес.`)
  }
  if (credit.payment_day !== null) {
    parts.push(`платёж ${credit.payment_day} числа`)
  }
  return parts.join(" · ")
}

export function CreditsPage() {
  const credits = useCredits()
  const accounts = useAccounts()
  const archive = useArchiveCredit()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creditSheetOpen, setCreditSheetOpen] = useState(false)
  const [paymentSheetOpen, setPaymentSheetOpen] = useState(false)
  const [editingCredit, setEditingCredit] = useState<Credit | null>(null)

  const list = useMemo(() => credits.data ?? [], [credits.data])
  const firstCredit = list[0] ?? null
  const selectedCredit =
    list.find((credit) => credit.id === selectedId) ?? firstCredit
  const payments = useCreditPayments(selectedCredit?.id ?? null)
  const accountById = useMemo(
    () =>
      new Map(
        (accounts.data ?? []).map((account) => [account.id, account]),
      ),
    [accounts.data],
  )

  const openCreate = () => {
    setEditingCredit(null)
    setCreditSheetOpen(true)
  }

  const openEdit = (credit: Credit) => {
    setEditingCredit(credit)
    setCreditSheetOpen(true)
  }

  const closeCreditSheet = () => {
    setCreditSheetOpen(false)
    setEditingCredit(null)
  }

  const closePaymentSheet = () => {
    setPaymentSheetOpen(false)
  }

  const remove = (credit: Credit) => {
    if (window.confirm(`Архивировать кредит «${credit.name}»?`)) {
      archive.mutate(credit.id)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Кредиты</h1>
        <button type="button" onClick={openCreate}>
          + Добавить кредит
        </button>
      </div>

      {credits.isPending && <p>Загрузка…</p>}
      {credits.isError && <p className="error">Не удалось загрузить кредиты</p>}
      {credits.isSuccess && list.length === 0 && (
        <p>Кредитов пока нет. Добавьте первый кредитный договор.</p>
      )}

      {list.length > 0 && (
        <div className="credits-layout">
          <ul className="credit-list">
            {list.map((credit) => {
              const active = selectedCredit?.id === credit.id
              const paid = percentPaid(credit)
              return (
                <li key={credit.id}>
                  <button
                    type="button"
                    className="credit-card"
                    aria-pressed={active}
                    onClick={() => setSelectedId(credit.id)}
                  >
                    <span className="credit-card__head">
                      <span className="credit-card__title">
                        {credit.name}
                      </span>
                      <span className="credit-card__balance">
                        {formatMoney(
                          credit.principal_balance,
                          credit.currency_code,
                        )}
                      </span>
                    </span>
                    <span className="credit-card__meta">
                      {creditMeta(credit)}
                    </span>
                    <span className="credit-progress">
                      <span
                        className="credit-progress__bar"
                        style={{ width: `${paid}%` }}
                      />
                    </span>
                    <span className="credit-card__meta">
                      Погашено {formatPercent(paid)}%
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>

          {selectedCredit && (
            <section className="credit-detail card">
              <div className="credit-detail__head">
                <div>
                  <h2>{selectedCredit.name}</h2>
                  <p>{creditMeta(selectedCredit)}</p>
                </div>
                <div className="credit-detail__actions">
                  <button
                    type="button"
                    className="btn-tonal"
                    onClick={() => setPaymentSheetOpen(true)}
                  >
                    + Платёж
                  </button>
                  <button
                    type="button"
                    className="link"
                    onClick={() => openEdit(selectedCredit)}
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="link danger"
                    onClick={() => remove(selectedCredit)}
                  >
                    В архив
                  </button>
                </div>
              </div>

              <dl className="credit-stats">
                <div>
                  <dt>Начальная сумма</dt>
                  <dd>
                    {formatMoney(
                      selectedCredit.principal_initial,
                      selectedCredit.currency_code,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Остаток долга</dt>
                  <dd>
                    {formatMoney(
                      selectedCredit.principal_balance,
                      selectedCredit.currency_code,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Погашено</dt>
                  <dd>{formatPercent(percentPaid(selectedCredit))}%</dd>
                </div>
              </dl>

              {selectedCredit.comments && (
                <p className="credit-comment">{selectedCredit.comments}</p>
              )}

              <h3>Платежи</h3>
              {payments.isPending && <p>Загрузка платежей…</p>}
              {payments.isError && (
                <p className="error">Не удалось загрузить платежи</p>
              )}
              {payments.isSuccess && payments.data.length === 0 && (
                <p>Платежей пока нет.</p>
              )}

              <ul className="credit-payments">
                {(payments.data ?? []).map((payment) => {
                  const account = accountById.get(payment.payment_account_id)
                  return (
                    <li key={payment.id} className="credit-payment-row">
                      <div>
                        <span className="credit-payment-row__title">
                          {formatMoney(
                            payment.total_amount,
                            payment.currency_code,
                          )}
                        </span>
                        <span className="credit-payment-row__meta">
                          {formatDate(payment.date)} · {account?.name ?? "Счёт"}
                        </span>
                        {payment.comment && (
                          <span className="credit-payment-row__meta">
                            {payment.comment}
                          </span>
                        )}
                      </div>
                      <div className="credit-payment-parts">
                        <span>
                          тело {formatMoney(
                            payment.principal_amount,
                            payment.currency_code,
                          )}
                        </span>
                        <span>
                          проценты {formatMoney(
                            payment.interest_amount,
                            payment.currency_code,
                          )}
                        </span>
                        <span>
                          комиссия {formatMoney(
                            payment.fee_amount,
                            payment.currency_code,
                          )}
                        </span>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}
        </div>
      )}

      <Sheet
        open={creditSheetOpen}
        title={editingCredit ? "Редактировать кредит" : "Новый кредит"}
        onClose={closeCreditSheet}
      >
        <CreditForm
          key={editingCredit?.id ?? "new"}
          credit={editingCredit}
          onDone={closeCreditSheet}
        />
      </Sheet>

      {selectedCredit && (
        <Sheet
          open={paymentSheetOpen}
          title={`Платёж по кредиту «${selectedCredit.name}»`}
          onClose={closePaymentSheet}
        >
          <CreditPaymentForm
            key={selectedCredit.id}
            credit={selectedCredit}
            onDone={closePaymentSheet}
          />
        </Sheet>
      )}
    </>
  )
}
