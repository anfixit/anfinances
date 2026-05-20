import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

function fmt(n) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(n);
}

function parseRub(str) {
  return parseFloat(String(str || "").replace(/[^0-9.-]/g, "")) || 0;
}

function StatCard({ label, value, sub, color, icon }) {
  return (
    <div
      className="card"
      style={{
        padding: "var(--sp-4)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-1)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          marginBottom: "var(--sp-1)",
        }}
      >
        {icon && (
          <span
            className="material-symbols-outlined"
            style={{ fontSize: "16px", color: "var(--text-muted)" }}
          >
            {icon}
          </span>
        )}
        <span
          style={{
            font: "var(--font-label-small)",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {label}
        </span>
      </div>
      <span
        style={{
          font: "var(--font-headline-small)",
          color: color || "var(--text)",
          letterSpacing: "-0.02em",
        }}
      >
        {value}
      </span>
      {sub && (
        <span
          style={{ font: "var(--font-body-small)", color: "var(--text-muted)" }}
        >
          {sub}
        </span>
      )}
    </div>
  );
}

export default function Dashboard({ summary, accounts, moneyflow }) {
  if (!summary) return null;

  const expenses = moneyflow.filter(
    (t) => t.type === "expense" && t.category !== "Transfer",
  );
  const income = moneyflow.filter(
    (t) => t.type === "income" && t.category !== "Transfer",
  );

  const totalExpenses = expenses.reduce(
    (s, t) => s + parseFloat(t["amount RUB"] || 0),
    0,
  );
  const totalIncome = income.reduce(
    (s, t) => s + parseFloat(t["amount RUB"] || 0),
    0,
  );
  const saldo = totalIncome - totalExpenses;

  const byCategory = expenses.reduce((acc, t) => {
    const cat = t.category || "Другое";
    acc[cat] = (acc[cat] || 0) + parseFloat(t["amount RUB"] || 0);
    return acc;
  }, {});

  const chartData = Object.entries(byCategory)
    .map(([name, value]) => ({ name, value: Math.round(value) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const assets = accounts
    .filter((a) => !a["acc.type"]?.includes("Credit"))
    .reduce((s, a) => s + parseRub(a["balance in RUB"]), 0);

  const debts = accounts
    .filter((a) => a["acc.type"]?.includes("Credit"))
    .reduce((s, a) => s + parseRub(a["balance in RUB"]), 0);

  const nonZero = accounts.filter((a) => parseRub(a["balance in RUB"]) !== 0);

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* ── HERO CARD ── */}
      <div className="card" style={{ padding: "var(--sp-6)" }}>
        <div
          style={{
            font: "var(--font-label-small)",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: "var(--sp-2)",
          }}
        >
          Net Worth
        </div>
        <div
          style={{
            font: "var(--font-display-small)",
            color:
              summary.totalBalance >= 0 ? "var(--success)" : "var(--error)",
            letterSpacing: "-0.03em",
            lineHeight: 1,
            marginBottom: "var(--sp-5)",
          }}
        >
          {fmt(summary.totalBalance)}
        </div>

        <div
          style={{
            height: "1px",
            background: "var(--border)",
            marginBottom: "var(--sp-5)",
          }}
        />

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "var(--sp-4)",
          }}
        >
          {[
            { label: "Активы", value: fmt(assets), color: "var(--success)" },
            { label: "Долги", value: fmt(debts), color: "var(--error)" },
            {
              label: "Runway",
              value: `${summary.runway ?? "—"} мес.`,
              color: summary.runway > 3 ? "var(--success)" : "var(--error)",
            },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div
                style={{
                  font: "var(--font-label-small)",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: "var(--sp-1)",
                }}
              >
                {label}
              </div>
              <div style={{ font: "var(--font-title-large)", color }}>
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── MONTH STATS ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "var(--sp-3)",
        }}
      >
        <StatCard
          icon="trending_up"
          label="Доходы"
          value={fmt(totalIncome)}
          sub="этот месяц"
          color="var(--success)"
        />
        <StatCard
          icon="trending_down"
          label="Расходы"
          value={fmt(totalExpenses)}
          sub="этот месяц"
          color="var(--error)"
        />
        <StatCard
          icon="balance"
          label="Сальдо"
          value={fmt(saldo)}
          color={saldo >= 0 ? "var(--success)" : "var(--error)"}
        />
        <StatCard
          icon="event_note"
          label="План минимум"
          value={fmt(summary.monthlyObligatory)}
          sub="в месяц"
        />
      </div>

      {/* ── ACCOUNTS ── */}
      <div className="card-flat" style={{ overflow: "hidden" }}>
        <div
          style={{
            padding: "var(--sp-3) var(--sp-5)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span
            style={{
              font: "var(--font-label-medium)",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            Счета
          </span>
          <span className="badge badge-primary">{nonZero.length} активных</span>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "1px",
            background: "var(--border)",
          }}
        >
          {nonZero.map((acc) => {
            const bal = parseRub(acc["balance in RUB"]);
            const isCredit = acc["acc.type"]?.includes("Credit");
            return (
              <div
                key={acc.account}
                className="list-item"
                style={{
                  background: "var(--bg-card)",
                  justifyContent: "space-between",
                  padding: "var(--sp-3) var(--sp-5)",
                  minHeight: "56px",
                  borderBottom: "none",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--sp-2)",
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "16px", color: "var(--text-muted)" }}
                    >
                      {isCredit ? "credit_card" : "account_balance_wallet"}
                    </span>
                    <span
                      style={{
                        font: "var(--font-title-small)",
                        color: "var(--text)",
                      }}
                    >
                      {acc.account}
                    </span>
                  </div>
                  <span
                    style={{
                      font: "var(--font-body-small)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {acc["acc.type"]} · {acc.currency}
                  </span>
                </div>
                <span
                  style={{
                    font: "var(--font-title-small)",
                    fontFamily: "var(--font-mono)",
                    color: bal >= 0 ? "var(--text)" : "var(--error)",
                  }}
                >
                  {fmt(bal)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── CHART ── */}
      {chartData.length > 0 && (
        <div className="card" style={{ padding: "var(--sp-5)" }}>
          <div
            style={{
              font: "var(--font-label-medium)",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginBottom: "var(--sp-4)",
            }}
          >
            Расходы по категориям
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={chartData}
              margin={{ top: 0, right: 0, left: -20, bottom: 0 }}
            >
              <XAxis
                dataKey="name"
                tick={{
                  fill: "var(--text-muted)",
                  fontSize: 11,
                  fontFamily: "var(--font-sans)",
                }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{
                  fill: "var(--text-muted)",
                  fontSize: 11,
                  fontFamily: "var(--font-sans)",
                }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text)",
                  font: "var(--font-body-small)",
                  boxShadow: "var(--elev-3)",
                }}
                formatter={(v) => [fmt(v), ""]}
                cursor={{ fill: "var(--surface-tint)", radius: 4 }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill="var(--primary)" fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── RECENT TRANSACTIONS ── */}
      {moneyflow.length > 0 && (
        <div className="card-flat" style={{ overflow: "hidden" }}>
          <div
            style={{
              padding: "var(--sp-3) var(--sp-5)",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span
              style={{
                font: "var(--font-label-medium)",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              Последние операции
            </span>
          </div>
          {[...moneyflow]
            .reverse()
            .filter((t) => t.category !== "Transfer")
            .slice(0, 5)
            .map((t, i, arr) => {
              const amt = parseFloat(t["amount RUB"] || 0);
              const isIncome = t.type === "income";
              return (
                <div
                  key={i}
                  className="list-item"
                  style={{
                    justifyContent: "space-between",
                    padding: "var(--sp-3) var(--sp-5)",
                    borderBottom:
                      i < arr.length - 1 ? "1px solid var(--border)" : "none",
                    minHeight: "56px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--sp-3)",
                      minWidth: 0,
                    }}
                  >
                    <div
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "var(--radius-md)",
                        background: isIncome
                          ? "var(--success-container)"
                          : "var(--error-container)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{
                          fontSize: "18px",
                          color: isIncome ? "var(--success)" : "var(--error)",
                        }}
                      >
                        {isIncome ? "arrow_downward" : "arrow_upward"}
                      </span>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          font: "var(--font-title-small)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {t.subcategory || t.category}
                      </div>
                      <div
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {t.account} · {String(t.date || "").split(" ")[0]}
                      </div>
                    </div>
                  </div>
                  <span
                    style={{
                      font: "var(--font-title-small)",
                      fontFamily: "var(--font-mono)",
                      color: isIncome ? "var(--success)" : "var(--error)",
                      whiteSpace: "nowrap",
                      marginLeft: "var(--sp-3)",
                    }}
                  >
                    {isIncome ? "+" : "−"}
                    {fmt(amt)}
                  </span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
