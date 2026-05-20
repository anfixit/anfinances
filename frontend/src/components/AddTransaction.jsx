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
const CURRENCIES = ["RUB", "USD", "UZS"];

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

function AmountRow({ value, onChange, currency, onCurrencyChange }) {
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
        {CURRENCIES.map((c) => (
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getReference()
      .then(setReference)
      .catch(() => {});
    getRates()
      .then((r) => {
        const map = {};
        r.forEach((row) => {
          if (row.currency) map[row.currency] = parseFloat(row.rate);
        });
        setRates(map);
      })
      .catch(() => {});
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleTypeChange = (t) => {
    setForm((f) => ({ ...f, type: t, category: "", subcategory: "" }));
  };

  const handleCategoryChange = (cat) => {
    setForm((f) => ({ ...f, category: cat, subcategory: "" }));
  };

  const cats = form.type === "income" ? INCOME_CATS : EXPENSE_CATS;
  const subcats = (form.category && reference[form.category]) || [];
  const isTransferLike = form.type === "transfer" || form.type === "conversion";

  const toRub = (amount, currency) => {
    if (!amount) return 0;
    const amt = parseFloat(amount);
    if (currency === "RUB") return amt;
    return amt * (rates[currency] || 0);
  };

  const rubPreview = toRub(form.amount, form.currency);

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
      className="sheet-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="sheet-content">
        {/* Handle */}
        <div className="sheet-handle" />

        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ font: "var(--font-headline-small)" }}>
            Новая операция
          </span>
          <button
            className="btn-text"
            onClick={onClose}
            style={{
              minWidth: "var(--touch)",
              width: "var(--touch)",
              height: "var(--touch)",
              borderRadius: "var(--radius-full)",
              padding: 0,
            }}
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Type selector */}
        <div className="segment-group">
          {TYPES.map(({ id, label, icon }) => (
            <button
              key={id}
              className={`segment-btn ${form.type === id ? "active" : ""}`}
              onClick={() => handleTypeChange(id)}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "16px" }}
              >
                {icon}
              </span>
              <span className="hide-mobile">{label}</span>
              <span
                className="show-mobile"
                style={{ fontSize: "11px", display: "block" }}
              >
                {label}
              </span>
            </button>
          ))}
        </div>

        {/* Date */}
        <Field label="Дата">
          <input
            type="date"
            value={form.date}
            onChange={(e) => set("date", e.target.value)}
          />
        </Field>

        {/* Amount from */}
        <Field label={form.type === "conversion" ? "Сумма списания" : "Сумма"}>
          <AmountRow
            value={form.amount}
            onChange={(v) => set("amount", v)}
            currency={form.currency}
            onCurrencyChange={(v) => set("currency", v)}
          />
        </Field>

        {/* Amount to (conversion only) */}
        {form.type === "conversion" && (
          <Field label="Сумма получения">
            <AmountRow
              value={form.amountTo}
              onChange={(v) => set("amountTo", v)}
              currency={form.currencyTo}
              onCurrencyChange={(v) => set("currencyTo", v)}
            />
          </Field>
        )}

        {/* Account from */}
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

        {/* Account to */}
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

        {/* Fee (conversion only) */}
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
                font: "var(--font-label-large)",
                minHeight: "var(--touch)",
              }}
            >
              <input
                type="checkbox"
                checked={form.hasFee}
                onChange={(e) => set("hasFee", e.target.checked)}
              />
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "18px", color: "var(--text-muted)" }}
              >
                info
              </span>
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

        {/* Category */}
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

        {/* Subcategory — dynamic, only shown when category selected */}
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

        {/* Required toggle (expense only) */}
        {form.type === "expense" && (
          <div className="segment-group">
            {[
              { id: "required", label: "Обязательный", icon: "priority_high" },
              { id: "optional", label: "Необязательный", icon: "remove" },
            ].map(({ id, label, icon }) => (
              <button
                key={id}
                className={`segment-btn ${form.required === id ? "active" : ""}`}
                onClick={() => set("required", id)}
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
        )}

        {/* Comment */}
        <Field label="Комментарий">
          <input
            placeholder="за что?"
            value={form.comment}
            onChange={(e) => set("comment", e.target.value)}
          />
        </Field>

        {/* RUB preview */}
        {form.amount && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              background: "var(--primary-container)",
              borderRadius: "var(--radius-md)",
              padding: "var(--sp-3) var(--sp-4)",
            }}
          >
            <span
              style={{
                font: "var(--font-label-medium)",
                color: "var(--on-primary-container)",
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-2)",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "16px" }}
              >
                calculate
              </span>
              Примерно в рублях
            </span>
            <span
              style={{
                font: "var(--font-title-small)",
                fontFamily: "var(--font-mono)",
                color: "var(--on-primary-container)",
              }}
            >
              ≈ {rubPreview.toLocaleString("ru-RU")} ₽
            </span>
          </div>
        )}

        {/* Error */}
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

        {/* Submit */}
        <button
          className="btn-success"
          onClick={handleSubmit}
          disabled={loading}
          style={{
            minHeight: "56px",
            borderRadius: "var(--radius-xl)",
            font: "var(--font-title-small)",
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
  );
}
