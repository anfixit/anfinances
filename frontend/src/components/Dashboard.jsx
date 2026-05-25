import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useState } from "react";
import { updateRates } from "../api";
import AddAccount from "./AddAccount";

function fmt(n) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
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

export default function Dashboard({ summary, accounts, moneyflow, onReload }) {
  const [ratesUpdating, setRatesUpdating] = useState(false);
  const [ratesUpdated, setRatesUpdated] = useState(false);
  const [showAddAccount, setShowAddAccount] = useState(false);

  if (!summary) return null;

  const handleUpdateRates = async () => {
    setRatesUpdating(true);
    setRatesUpdated(false);
    try {
      await updateRates();
      setRatesUpdated(true);
      setTimeout(() => setRatesUpdated(false), 3000);
    } catch (e) {
    } finally {
      setRatesUpdating(false);
    }
  };

  const balances = summary.accountBalancesRub || {};

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

  // Балансы теперь из summary.accountBalancesRub
  const assets = accounts
    .filter((a) => !a["acc.type"]?.includes("Credit"))
    .reduce(
      (s, a) => s + (balances[a.account] ?? parseRub(a["balance in RUB"])),
      0,
    );

  const debts = accounts
    .filter((a) => a["acc.type"]?.includes("Credit"))
    .reduce(
      (s, a) => s + (balances[a.account] ?? parseRub(a["balance in RUB"])),
      0,
    );

  const nonZero = accounts.filter(
    (a) =>
      Math.abs(balances[a.account] ?? parseRub(a["balance in RUB"])) > 0.01,
  );

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
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-3)",
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
            <span className="badge badge-primary">
              {nonZero.length} активных
            </span>
          </div>
          <button
            className="btn-text"
            onClick={() => setShowAddAccount(true)}
            style={{
              minHeight: "unset",
              height: "32px",
              padding: "0 var(--sp-3)",
              font: "var(--font-label-medium)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "16px" }}
            >
              add
            </span>
            Добавить
          </button>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "1px",
            background: "var(--border)",
          }}
        >
          // ── ПАТЧ для Dashboard.jsx ── // Заменить фрагмент рендера карточки
          счёта (внутри nonZero.map) на этот код:
          {nonZero.map((acc) => {
            const bal =
              balances[acc.account] ?? parseRub(acc["balance in RUB"]);
            const isCredit = acc["acc.type"]?.includes("Credit");

            // credit_limit — новая колонка в accounts (число, например 110000)
            const creditLimit = parseFloat(
              String(acc.credit_limit || "0").replace(/[^0-9.-]/g, ""),
            );
            // Доступно = лимит + текущий баланс (баланс отрицательный при долге)
            const available = creditLimit > 0 ? creditLimit + bal : null;

            return (
              <div
                key={acc.account}
                className="list-item"
                style={{
                  background: "var(--bg-card)",
                  justifyContent: "space-between",
                  padding: "var(--sp-3) var(--sp-5)",
                  minHeight: isCredit && creditLimit > 0 ? "72px" : "56px",
                  borderBottom: "none",
                  flexDirection: "row",
                  alignItems: "center",
                }}
              >
                {/* LEFT: name + type */}
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

                {/* RIGHT: balance + credit info */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-end",
                    gap: "2px",
                  }}
                >
                  {isCredit && creditLimit > 0 ? (
                    <>
                      {/* Долг (отрицательный баланс — красный) */}
                      <span
                        style={{
                          font: "var(--font-title-small)",
                          fontFamily: "var(--font-mono)",
                          color: "var(--error)",
                        }}
                      >
                        {fmt(bal)}
                      </span>
                      {/* Доступно */}
                      <span
                        style={{
                          font: "var(--font-body-small)",
                          fontFamily: "var(--font-mono)",
                          color:
                            available >= 0
                              ? "var(--success)"
                              : "var(--warning)",
                        }}
                      >
                        доступно {fmt(available)}
                      </span>
                      {/* Лимит */}
                      <span
                        style={{
                          font: "var(--font-label-small)",
                          color: "var(--text-muted)",
                        }}
                      >
                        лимит {fmt(creditLimit)}
                      </span>
                    </>
                  ) : (
                    <span
                      style={{
                        font: "var(--font-title-small)",
                        fontFamily: "var(--font-mono)",
                        color: bal >= 0 ? "var(--text)" : "var(--error)",
                      }}
                    >
                      {fmt(bal)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── RATES ── */}
      <div
        className="card"
        style={{
          padding: "var(--sp-4) var(--sp-5)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--sp-4)",
          flexWrap: "wrap",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-4)",
            flexWrap: "wrap",
          }}
        >
          <div>
            <div
              style={{
                font: "var(--font-label-small)",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: "var(--sp-1)",
              }}
            >
              Курсы валют
            </div>
            <div
              style={{ display: "flex", gap: "var(--sp-4)", flexWrap: "wrap" }}
            >
              {summary.ratesMap &&
                Object.entries(summary.ratesMap)
                  .filter(([cur]) => cur !== "RUB")
                  .map(([cur, rate]) => (
                    <span
                      key={cur}
                      style={{
                        font: "var(--font-title-small)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      1 {cur} ={" "}
                      {Number(rate).toLocaleString("ru-RU", {
                        maximumFractionDigits: 2,
                      })}{" "}
                      ₽
                    </span>
                  ))}
            </div>
          </div>
        </div>
        <button
          className={ratesUpdated ? "btn-success" : "btn-outlined"}
          onClick={handleUpdateRates}
          disabled={ratesUpdating}
          style={{
            height: "40px",
            minHeight: "40px",
            font: "var(--font-label-large)",
            flexShrink: 0,
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{
              fontSize: "18px",
              animation: ratesUpdating ? "spin 1s linear infinite" : "none",
            }}
          >
            {ratesUpdated ? "check" : "currency_exchange"}
          </span>
          {ratesUpdating
            ? "Обновляем..."
            : ratesUpdated
              ? "Обновлено"
              : "Обновить курсы"}
        </button>
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

      {/* ── ADD ACCOUNT MODAL ── */}
      {showAddAccount && (
        <AddAccount
          onClose={() => setShowAddAccount(false)}
          onSaved={() => {
            setShowAddAccount(false);
            if (onReload) onReload();
          }}
        />
      )}
    </div>
  );
}
