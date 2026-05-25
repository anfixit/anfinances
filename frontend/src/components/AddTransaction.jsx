import { useState, useEffect } from "react";
import { addTransaction, getReference, getRates } from "../api";

const EXPENSE_CATS = [
  "Auto",
  "Bank",
  "Beauty",
  "Clothing_Shoes",
  "Communication",
  "Entertainment",
  "Food",
  "Gifts_Charity",
  "Hardware",
  "Healthcare",
  "Home",
  "Self_Development",
  "Software",
  "Pets",
  "Public_Services",
  "Taxes",
  "Transport",
  "Travel",
];
const INCOME_CATS = ["Income"];

const TYPES = [
  { id: "expense", label: "Расход", icon: "trending_down" },
  { id: "income", label: "Доход", icon: "trending_up" },
  { id: "transfer", label: "Перевод", icon: "sync_alt" },
  { id: "conversion", label: "Конвертация", icon: "currency_exchange" },
];

function Field({ label, children }) {
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}
    >
      <label
        style={{ font: "var(--font-label-medium)", color: "var(--text-muted)" }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

function AmountRow({
  value,
  onChange,
  currency,
  onCurrencyChange,
  currencies,
}) {
  return (
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
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <select
        value={currency}
        onChange={(e) => onCurrencyChange(e.target.value)}
      >
        {currencies.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
    </div>
  );
}

export default function AddTransaction({ accounts, onClose, onSaved }) {
  const [form, setForm] = useState({
    type: "expense",
    amount: "",
    amountTo: "",
    account: accounts[0]?.account || "",
    account_to: accounts[1]?.account || "",
    currency: "RUB",
    currencyTo: "USD",
    category: "",
    subcategory: "",
    comment: "",
    required: "optional",
    date: new Date().toISOString().split("T")[0],
    hasFee: false,
    fee: "",
    feeAccount: accounts[0]?.account || "",
  });
  const [reference, setReference] = useState({});
  const [rates, setRates] = useState({});
  const [currencies, setCurrencies] = useState(["RUB"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getReference()
      .then(setReference)
      .catch(() => {});
    getRates()
      .then((r) => {
        const map = {};
        const list = [];
        r.forEach((row) => {
          if (row.currency) {
            map[row.currency] = parseFloat(row.rate);
            list.push(row.currency);
          }
        });
        setRates(map);
        setCurrencies(list);
      })
      .catch(() => {});
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const handleTypeChange = (t) =>
    setForm((f) => ({ ...f, type: t, category: "", subcategory: "" }));
  const handleCategoryChange = (cat) =>
    setForm((f) => ({ ...f, category: cat, subcategory: "" }));

  const cats = form.type === "income" ? INCOME_CATS : EXPENSE_CATS;
  const subcats = (form.category && reference[form.category]) || [];
  const isTransferLike = form.type === "transfer" || form.type === "conversion";

  const toRub = (amount, currency) => {
    if (!amount) return 0;
    const amt = parseFloat(amount);
    if (currency === "RUB") return amt;
    return amt * (rates[currency] || 0);
  };

  const handleSubmit = async () => {
    if (!form.amount || !form.account) {
      setError("Заполни сумму и счёт");
      return;
    }
    if (isTransferLike && form.account === form.account_to) {
      setError("Счета должны быть разными");
      return;
    }
    if (form.type === "conversion" && !form.amountTo) {
      setError("Укажи сумму получения");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const now = new Date();
      const isToday = form.date === now.toISOString().split("T")[0];
      const dateStr = isToday
        ? now.toLocaleDateString("en-US") +
          " " +
          now.toLocaleTimeString("en-US", { hour12: false })
        : new Date(form.date + "T12:00:00").toLocaleDateString("en-US") +
          " 12:00:00";

      if (form.type === "transfer") {
        const amtRub = toRub(form.amount, form.currency);
        const base = {
          date: dateStr,
          currency: form.currency,
          account_to: form.account_to,
          category: "Transfer",
          subcategory: "Transfer",
          comment: form.comment,
          required: "",
          amount: `${form.currency} ${form.amount}`,
          "amount RUB": amtRub,
        };
        await addTransaction({
          ...base,
          type: "expense",
          account: form.account,
        });
        await addTransaction({
          ...base,
          type: "income",
          account: form.account_to,
          account_to: form.account,
        });
      } else if (form.type === "conversion") {
        const comment =
          form.comment ||
          `${form.amount} ${form.currency} → ${form.amountTo} ${form.currencyTo}`;
        await addTransaction({
          date: dateStr,
          type: "expense",
          required: "",
          amount: `${form.currency} ${form.amount}`,
          "amount RUB": toRub(form.amount, form.currency),
          account: form.account,
          account_to: form.account_to,
          currency: form.currency,
          category: "Transfer",
          subcategory: "Conversion",
          comment,
        });
        await addTransaction({
          date: dateStr,
          type: "income",
          required: "",
          amount: `${form.currencyTo} ${form.amountTo}`,
          "amount RUB": toRub(form.amountTo, form.currencyTo),
          account: form.account_to,
          account_to: form.account,
          currency: form.currencyTo,
          category: "Transfer",
          subcategory: "Conversion",
          comment,
        });
        if (form.hasFee && form.fee) {
          await addTransaction({
            date: dateStr,
            type: "expense",
            required: "optional",
            amount: `${form.currency} ${form.fee}`,
            "amount RUB": toRub(form.fee, form.currency),
            account: form.feeAccount,
            account_to: "",
            currency: form.currency,
            category: "Bank",
            subcategory: "Service",
            comment: `Комиссия: ${comment}`,
          });
        }
      } else {
        await addTransaction({
          date: dateStr,
          type: form.type,
          required: form.type === "expense" ? form.required : "",
          amount: `${form.currency} ${form.amount}`,
          "amount RUB": toRub(form.amount, form.currency),
          account: form.account,
          account_to: "",
          currency: form.currency,
          category: form.category,
          subcategory: form.subcategory || form.category,
          comment: form.comment,
        });
      }
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
        alignItems: "flex-end",
        justifyContent: "center",
        animation: "fadeIn 0.2s ease",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          borderRadius: "var(--radius-xl) var(--radius-xl) 0 0",
          width: "100%",
          maxWidth: "600px",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--elev-5)",
          animation: "slideUp 0.3s cubic-bezier(0.32, 0.72, 0, 1)",
        }}
      >
        {/* Handle */}
        <div
          style={{
            padding: "var(--sp-3) 0 0",
            display: "flex",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <div
            style={{
              width: "32px",
              height: "4px",
              background: "var(--border-strong)",
              borderRadius: "var(--radius-full)",
            }}
          />
        </div>

        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "var(--sp-4) var(--sp-6)",
            flexShrink: 0,
          }}
        >
          <span style={{ font: "var(--font-headline-small)" }}>
            Новая операция
          </span>
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
              cursor: "pointer",
            }}
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Type selector */}
        <div style={{ padding: "0 var(--sp-6) var(--sp-4)", flexShrink: 0 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-sm)",
              overflow: "hidden",
              background: "var(--bg-input)",
            }}
          >
            {TYPES.map(({ id, label, icon }, i) => (
              <button
                key={id}
                onClick={() => handleTypeChange(id)}
                style={{
                  background:
                    form.type === id
                      ? "var(--primary-container)"
                      : "transparent",
                  color:
                    form.type === id
                      ? "var(--on-primary-container)"
                      : "var(--text-muted)",
                  border: "none",
                  borderRight:
                    i < TYPES.length - 1
                      ? "1px solid var(--border-strong)"
                      : "none",
                  borderRadius: 0,
                  padding: "var(--sp-3) var(--sp-2)",
                  height: "52px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "4px",
                  cursor: "pointer",
                  fontWeight: form.type === id ? 700 : 400,
                  transition: "all 0.15s",
                  minWidth: 0,
                }}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "18px" }}
                >
                  {icon}
                </span>
                <span
                  style={{
                    fontSize: "11px",
                    whiteSpace: "nowrap",
                    lineHeight: 1,
                  }}
                >
                  {label}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Scrollable content */}
        <div
          style={{
            overflowY: "auto",
            flex: 1,
            padding: "0 var(--sp-6) var(--sp-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
          }}
        >
          <Field label="Дата">
            <input
              type="date"
              value={form.date}
              onChange={(e) => set("date", e.target.value)}
            />
          </Field>

          <Field
            label={form.type === "conversion" ? "Сумма списания" : "Сумма"}
          >
            <AmountRow
              value={form.amount}
              onChange={(v) => set("amount", v)}
              currency={form.currency}
              onCurrencyChange={(v) => set("currency", v)}
              currencies={currencies}
            />
          </Field>

          {form.type === "conversion" && (
            <Field label="Сумма получения">
              <AmountRow
                value={form.amountTo}
                onChange={(v) => set("amountTo", v)}
                currency={form.currencyTo}
                onCurrencyChange={(v) => set("currencyTo", v)}
                currencies={currencies}
              />
            </Field>
          )}

          <Field label={isTransferLike ? "Откуда" : "Счёт"}>
            <select
              value={form.account}
              onChange={(e) => set("account", e.target.value)}
            >
              {accounts.map((a) => (
                <option key={a.account} value={a.account}>
                  {a.account}
                </option>
              ))}
            </select>
          </Field>

          {isTransferLike && (
            <Field label="Куда">
              <select
                value={form.account_to}
                onChange={(e) => set("account_to", e.target.value)}
              >
                {accounts.map((a) => (
                  <option key={a.account} value={a.account}>
                    {a.account}
                  </option>
                ))}
              </select>
            </Field>
          )}

          {form.type === "conversion" && (
            <div
              style={{
                background: "var(--bg-card-2)",
                borderRadius: "var(--radius-md)",
                padding: "var(--sp-4)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-4)",
              }}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-3)",
                  cursor: "pointer",
                  font: "var(--font-body-medium)",
                }}
              >
                <input
                  type="checkbox"
                  checked={form.hasFee}
                  onChange={(e) => set("hasFee", e.target.checked)}
                />
                Есть комиссия банка
              </label>
              {form.hasFee && (
                <>
                  <Field label="Сумма комиссии">
                    <input
                      type="number"
                      placeholder="0.00"
                      value={form.fee}
                      onChange={(e) => set("fee", e.target.value)}
                    />
                  </Field>
                  <Field label="Счёт списания комиссии">
                    <select
                      value={form.feeAccount}
                      onChange={(e) => set("feeAccount", e.target.value)}
                    >
                      {accounts.map((a) => (
                        <option key={a.account} value={a.account}>
                          {a.account}
                        </option>
                      ))}
                    </select>
                  </Field>
                </>
              )}
            </div>
          )}

          {!isTransferLike && (
            <Field label="Категория">
              <select
                value={form.category}
                onChange={(e) => handleCategoryChange(e.target.value)}
              >
                <option value="">— выбрать —</option>
                {cats.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
          )}

          {!isTransferLike && subcats.length > 0 && (
            <Field label="Подкатегория">
              <select
                value={form.subcategory}
                onChange={(e) => set("subcategory", e.target.value)}
              >
                <option value="">— выбрать —</option>
                {subcats.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
          )}

          {form.type === "expense" && (
            <Field label="Тип расхода">
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--radius-sm)",
                  overflow: "hidden",
                  background: "var(--bg-input)",
                }}
              >
                {[
                  {
                    id: "required",
                    label: "Обязательный",
                    icon: "priority_high",
                  },
                  { id: "optional", label: "Необязательный", icon: "remove" },
                ].map(({ id, label, icon }, i) => (
                  <button
                    key={id}
                    onClick={() => set("required", id)}
                    style={{
                      background:
                        form.required === id
                          ? "var(--primary-container)"
                          : "transparent",
                      color:
                        form.required === id
                          ? "var(--on-primary-container)"
                          : "var(--text-muted)",
                      border: "none",
                      borderRight:
                        i === 0 ? "1px solid var(--border-strong)" : "none",
                      borderRadius: 0,
                      height: "48px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "var(--sp-2)",
                      cursor: "pointer",
                      font: "var(--font-label-medium)",
                      fontWeight: form.required === id ? 700 : 400,
                      transition: "all 0.15s",
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "16px" }}
                    >
                      {icon}
                    </span>
                    {label}
                  </button>
                ))}
              </div>
            </Field>
          )}

          <Field label="Комментарий">
            <input
              placeholder="за что?"
              value={form.comment}
              onChange={(e) => set("comment", e.target.value)}
            />
          </Field>

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
            {loading ? (
              <>
                <span
                  className="material-symbols-outlined"
                  style={{
                    animation: "spin 1s linear infinite",
                    fontSize: "20px",
                  }}
                >
                  progress_activity
                </span>
                Сохраняем...
              </>
            ) : (
              <>
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "20px" }}
                >
                  check
                </span>
                Сохранить
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
