import { useState, useEffect } from "react";
import { getRates, addAccount } from "../api";
import {
  ACCOUNT_TYPES,
  ACCOUNT_TYPE_LABELS,
  ACCOUNT_TYPE_ICONS,
} from "../constants";

export default function AddAccount({
  onClose,
  onSaved,
  existingAccounts = [],
}) {
  const [form, setForm] = useState({
    account: "",
    "acc.type": "Card",
    currency: "RUB",
    initial_balance: "0",
    credit_limit: "",
    comments: "",
  });
  const [currencies, setCurrencies] = useState(["RUB"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getRates()
      .then((r) => {
        const list = r.map((row) => row.currency).filter(Boolean);
        if (list.length) setCurrencies(list);
      })
      .catch(() => {});
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const formatBalance = (amount, currency) => {
    const num = parseFloat(amount) || 0;
    if (currency === "RUB") return `${num.toFixed(2)} RUB `;
    if (currency === "USD") return `${num.toFixed(2)}$`;
    if (currency === "UZS") return `${num.toFixed(0)}soʼm`;
    return `${num.toFixed(2)} ${currency}`;
  };

  const isCredit = form["acc.type"]?.includes("Credit");

  const handleSubmit = async () => {
    const nameTrimmed = form.account.trim();
    if (!nameTrimmed) {
      setError("Введи название счёта");
      return;
    }
    // Проверка уникальности
    const duplicate = existingAccounts.some(
      (a) =>
        String(a.account || "")
          .trim()
          .toLowerCase() === nameTrimmed.toLowerCase(),
    );
    if (duplicate) {
      setError(`Счёт с именем "${nameTrimmed}" уже существует`);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const formatted = formatBalance(form.initial_balance, form.currency);
      await addAccount({
        account: nameTrimmed,
        "acc.type": form["acc.type"],
        currency: form.currency,
        initial_balance: formatted,
        "balance in acc.currency": formatted,
        "balance in RUB": formatted,
        comments: form.comments,
        credit_limit: isCredit ? form.credit_limit : "",
      });
      onSaved();
    } catch (e) {
      setError("Ошибка при сохранении. Попробуй ещё раз.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--overlay)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--sp-4)",
        animation: "fadeIn 0.2s ease",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          borderRadius: "var(--radius-xl)",
          width: "100%",
          maxWidth: "440px",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--elev-5)",
          animation: "slideUp 0.3s cubic-bezier(0.32, 0.72, 0, 1)",
          maxHeight: "92vh",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "var(--sp-5) var(--sp-6) var(--sp-4)",
          }}
        >
          <span style={{ font: "var(--font-headline-small)" }}>Новый счёт</span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              width: "40px",
              height: "40px",
              borderRadius: "var(--radius-full)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-muted)",
            }}
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div
          style={{
            padding: "0 var(--sp-6) var(--sp-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
          }}
        >
          {/* Название */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
            }}
          >
            <label
              style={{
                font: "var(--font-label-medium)",
                color: "var(--text-muted)",
              }}
            >
              Название
            </label>
            <input
              placeholder="Например: Tinkoff Black"
              value={form.account}
              onChange={(e) => set("account", e.target.value)}
              autoFocus
            />
          </div>

          {/* Тип */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
            }}
          >
            <label
              style={{
                font: "var(--font-label-medium)",
                color: "var(--text-muted)",
              }}
            >
              Тип
            </label>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                overflow: "hidden",
                background: "var(--bg-input)",
              }}
            >
              {ACCOUNT_TYPES.map((type, i) => {
                const active = form["acc.type"] === type;
                return (
                  <button
                    key={type}
                    onClick={() => set("acc.type", type)}
                    style={{
                      background: active
                        ? "var(--primary-container)"
                        : "transparent",
                      color: active
                        ? "var(--on-primary-container)"
                        : "var(--text-muted)",
                      border: "none",
                      borderRight:
                        i < 2 ? "1px solid var(--border-strong)" : "none",
                      borderRadius: 0,
                      height: "56px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "4px",
                      cursor: "pointer",
                      fontWeight: active ? 700 : 400,
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "18px" }}
                    >
                      {ACCOUNT_TYPE_ICONS[type]}
                    </span>
                    <span style={{ fontSize: "11px" }}>
                      {ACCOUNT_TYPE_LABELS[type]}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Начальный баланс + валюта */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
            }}
          >
            <label
              style={{
                font: "var(--font-label-medium)",
                color: "var(--text-muted)",
              }}
            >
              Начальный баланс
            </label>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 96px",
                gap: "var(--sp-2)",
              }}
            >
              <input
                type="number"
                inputMode="decimal"
                placeholder="0.00"
                value={form.initial_balance}
                onChange={(e) => set("initial_balance", e.target.value)}
              />
              <select
                value={form.currency}
                onChange={(e) => set("currency", e.target.value)}
              >
                {currencies.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Кредитный лимит — только для Card, Credit */}
          {isCredit && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-2)",
              }}
            >
              <label
                style={{
                  font: "var(--font-label-medium)",
                  color: "var(--text-muted)",
                }}
              >
                Кредитный лимит, {form.currency}
              </label>
              <input
                type="number"
                inputMode="decimal"
                placeholder="например, 120000"
                value={form.credit_limit}
                onChange={(e) => set("credit_limit", e.target.value)}
              />
            </div>
          )}

          {/* Комментарий */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
            }}
          >
            <label
              style={{
                font: "var(--font-label-medium)",
                color: "var(--text-muted)",
              }}
            >
              Комментарий
            </label>
            <input
              placeholder="необязательно"
              value={form.comments}
              onChange={(e) => set("comments", e.target.value)}
            />
          </div>

          {error && (
            <div
              style={{
                background: "var(--error-container)",
                borderRadius: "var(--radius-md)",
                padding: "var(--sp-3) var(--sp-4)",
                font: "var(--font-body-medium)",
                color: "var(--error)",
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-2)",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "18px" }}
              >
                error
              </span>
              {error}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              background: "var(--primary)",
              color: "var(--on-primary)",
              border: "none",
              borderRadius: "var(--radius-xl)",
              height: "56px",
              font: "var(--font-title-small)",
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--sp-2)",
              transition: "all 0.15s",
            }}
          >
            {loading ? "Сохраняем..." : "Создать счёт"}
          </button>
        </div>
      </div>
    </div>
  );
}
