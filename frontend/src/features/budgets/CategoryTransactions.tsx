import { useTransactions } from "@/features/transactions/hooks"
import { formatMoney } from "@/lib/money"

/** Границы месяца «YYYY-MM» в виде ISO-дат. */
function bounds(month: string): { from: string; to: string } {
  const [ys, ms] = month.split("-")
  const year = Number(ys)
  const mon = Number(ms)
  const last = new Date(year, mon, 0).getDate()
  return {
    from: `${month}-01`,
    to: `${month}-${String(last).padStart(2, "0")}`,
  }
}

/** Операции, из которых сложилась цифра «потрачено» в строке бюджета.
 *
 * Раньше за числом ничего не стояло: чтобы понять, из чего оно
 * набралось, надо было уходить на страницу операций и настраивать
 * там фильтры заново. */
export function CategoryTransactions({
  categoryId,
  month,
}: {
  categoryId: string
  month: string
}) {
  const { from, to } = bounds(month)
  const list = useTransactions({
    category_id: categoryId,
    date_from: from,
    date_to: to,
  })

  const rows = list.data?.pages.flatMap((p) => p.items) ?? []

  if (list.isPending) {
    return <p className="allowance-note">Загрузка…</p>
  }
  if (rows.length === 0) {
    return <p className="allowance-note">В этом месяце операций нет.</p>
  }

  return (
    <table className="data-table">
      <tbody>
        {rows.map((t) => (
          <tr key={t.id}>
            <td>
              {new Date(t.date).toLocaleDateString("ru-RU")}
              {t.payee_name_snapshot !== null &&
                ` · ${t.payee_name_snapshot}`}
              {t.payee_name_snapshot === null &&
                t.comment !== null &&
                ` · ${t.comment}`}
            </td>
            <td className="num">
              {formatMoney(t.amount, t.currency_code)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
