import { useState, useEffect } from "react";
import { getSummary, getAccounts, getMoneyflow } from "./api";
import Dashboard from "./components/Dashboard";
import Transactions from "./components/Transactions";
import Budget from "./components/Budget";
import AddTransaction from "./components/AddTransaction";
import "./index.css";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "dark",
  );
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [moneyflow, setMoneyflow] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const loadData = () => {
    setLoading(true);
    Promise.all([getSummary(), getAccounts(), getMoneyflow()])
      .then(([s, a, m]) => {
        setSummary(s);
        setAccounts(a);
        setMoneyflow(m);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const NAV = [
    { id: "dashboard", icon: "dashboard", label: "Дашборд" },
    { id: "transactions", icon: "receipt_long", label: "Транзакции" },
    { id: "budget", icon: "account_balance_wallet", label: "Бюджет" },
  ];

  return (
    <div
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
      {/* NAVBAR */}
      <nav
        style={{
          background: "var(--bg-card)",
          borderBottom: "1px solid var(--border)",
          padding: "0 var(--sp-6)",
          display: "flex",
          alignItems: "center",
          height: "64px",
          gap: "var(--sp-2)",
          position: "sticky",
          top: 0,
          zIndex: 100,
          boxShadow: "var(--elev-2)",
        }}
      >
        {/* Logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            marginRight: "var(--sp-6)",
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              background: "var(--primary)",
              borderRadius: "var(--radius-sm)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "18px", color: "var(--on-primary)" }}
            >
              savings
            </span>
          </div>
          <span
            style={{
              font: "var(--font-title-medium)",
              color: "var(--text)",
              letterSpacing: "-0.02em",
            }}
          >
            anfinances
          </span>
        </div>

        {/* Nav */}
        <div style={{ display: "flex", flex: 1, height: "100%" }}>
          {NAV.map(({ id, icon, label }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              style={{
                background: "none",
                border: "none",
                borderBottom:
                  page === id
                    ? "2px solid var(--primary)"
                    : "2px solid transparent",
                borderRadius: 0,
                color: page === id ? "var(--text)" : "var(--text-muted)",
                padding: "0 var(--sp-4)",
                font: "var(--font-label-large)",
                height: "100%",
                minHeight: "unset",
                gap: "var(--sp-2)",
                transition: "color 0.15s, border-color 0.15s",
              }}
            >
              <span
                className="material-symbols-outlined hide-mobile"
                style={{ fontSize: "18px" }}
              >
                {icon}
              </span>
              {label}
            </button>
          ))}
        </div>

        {/* Actions */}
        <div
          style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}
        >
          <button
            className="btn-filled hide-mobile"
            onClick={() => setShowAdd(true)}
            style={{
              height: "40px",
              minHeight: "40px",
              borderRadius: "var(--radius-full)",
              padding: "0 var(--sp-5)",
              font: "var(--font-label-large)",
              fontWeight: 700,
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "18px" }}
            >
              add
            </span>
            Добавить
          </button>
          <button
            className="btn-outlined"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            style={{
              width: "40px",
              height: "40px",
              minHeight: "40px",
              padding: 0,
              borderRadius: "var(--radius-full)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "20px" }}
            >
              {theme === "dark" ? "light_mode" : "dark_mode"}
            </span>
          </button>
        </div>
      </nav>

      {/* CONTENT */}
      <main
        style={{
          flex: 1,
          padding: "var(--sp-6)",
          maxWidth: "1100px",
          width: "100%",
          margin: "0 auto",
          paddingBottom: "80px",
        }}
      >
        {loading ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "240px",
              color: "var(--text-muted)",
              font: "var(--font-body-medium)",
              gap: "var(--sp-3)",
              flexDirection: "column",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{
                fontSize: "32px",
                animation: "spin 1s linear infinite",
                color: "var(--primary)",
              }}
            >
              progress_activity
            </span>
            Загружаем данные...
          </div>
        ) : (
          <>
            {page === "dashboard" && (
              <Dashboard
                summary={summary}
                accounts={accounts}
                moneyflow={moneyflow}
                onReload={loadData}
              />
            )}
            {page === "transactions" && (
              <Transactions
                moneyflow={moneyflow}
                accounts={accounts}
                onReload={loadData}
              />
            )}
            {page === "budget" && <Budget moneyflow={moneyflow} />}
          </>
        )}
      </main>

      {/* FAB mobile */}
      <button
        className="fab show-mobile"
        onClick={() => setShowAdd(true)}
        style={{ display: "flex" }}
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: "22px" }}
        >
          add
        </span>
        Добавить
      </button>

      {showAdd && (
        <AddTransaction
          accounts={accounts}
          onClose={() => setShowAdd(false)}
          onSaved={() => {
            setShowAdd(false);
            loadData();
          }}
        />
      )}
    </div>
  );
}
