import { useState, useEffect } from "react";
import {
  updateTransaction,
  deleteTransaction,
  getReference,
  getRates,
} from "../api";

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

// Парсим строку типа "RUB 1,000.00" или "RUB 48.00" → число
function parseAmount(str) {
  if (!str) return "";
  return String(str).replace(/[^0-9.-]/g, "");
}

// Определяем тип UI по данным строки
function detectUIType(tx) {
  if (tx.category === "Transfer") {
    if (tx.subcategory === "Conversion") return "conversion";
    return "transfer";
  }
  return tx.type; // "expense" | "income"
}

// Форма для одной строки (expense или income)
function SingleRowForm({
  tx,
  accounts,
  reference,
  currencies,
  onChange,
  label,
}) {
  const isExpense = tx.type === "expense";
  const cats = isExpense ? EXPENSE_CATS : INCOME_CATS;
  const subcats = (tx.category && reference[tx.category]) || [];

  return (
    <div
      style={{
        background: "var(--bg-input)",
        borderRadius: "var(--radius-md)",
        padding: "var(--sp-4)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-3)",
      }}
    >
      {label && (
        <div
          style={{
            font: "var(--font-label-medium)",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {label}
        </div>
      )}

      <Field label="Сумма">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 96px",
            gap: "var(--sp-2)",
          }}
        >
          <input
            className="input"
            type="number"
            value={parseAmount(tx.amount)}
            onChange={(e) =>
              onChange("amount", `${tx.currency} ${e.target.value}`)
            }
          />
          <select
            className="input"
            value={tx.currency}
            onChange={(e) => onChange("currency", e.target.value)}
          >
            {currencies.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      </Field>

      <Field label="Счёт">
        <select
          className="input"
          value={tx.account}
          onChange={(e) => onChange("account", e.target.value)}
        >
          {accounts.map((a) => (
            <option key={a.account} value={a.account}>
              {a.account}
            </option>
          ))}
        </select>
      </Field>

      {tx.category !== "Transfer" && (
        <>
          <Field label="Категория">
            <select
              className="input"
              value={tx.category}
              onChange={(e) => onChange("category", e.target.value)}
            >
              <option value="">—</option>
              {cats.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          {subcats.length > 0 && (
            <Field label="Подкатегория">
              <select
                className="input"
                value={tx.subcategory}
                onChange={(e) => onChange("subcategory", e.target.value)}
              >
                <option value="">—</option>
                {subcats.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {isExpense && (
            <Field label="Обязательность">
              <select
                className="input"
                value={tx.required}
                onChange={(e) => onChange("required", e.target.value)}
              >
                <option value="required">Обязательный</option>
                <option value="optional">Опциональный</option>
                <option value="">Не указано</option>
              </select>
            </Field>
          )}
        </>
      )}
    </div>
  );
}

export default function EditTransaction({ tx, accounts, onClose, onSaved }) {
  const isTransfer =
    detectUIType(tx) === "transfer" || detectUIType(tx) === "conversion";

  // Для переводов ищем парную строку в данных родителя через prop
  const pairTx = tx._pair || null;

  const [form, setForm] = useState({ ...tx });
  const [pairForm, setPairForm] = useState(pairTx ? { ...pairTx } : null);
  const [reference, setReference] = useState({});
  const [currencies, setCurrencies] = useState(["RUB", "USD", "UZS", "THB"]);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  // Показывать ли пару (только для переводов)
  const [showPair, setShowPair] = useState(true);

  useEffect(() => {
    getReference()
      .then(setReference)
      .catch(() => {});
    getRates()
      .then((r) => {
        const list = r.map((row) => row.currency).filter(Boolean);
        if (list.length) setCurrencies(list);
      })
      .catch(() => {});
  }, []);

  const updateField = (key, val) => setForm((f) => ({ ...f, [key]: val }));
  const updatePairField = (key, val) =>
    setPairForm((f) => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setLoading(true);
    setError("");
    try {
      // Пересчитываем amount RUB из amount
      const amtNum = parseFloat(parseAmount(form.amount)) || 0;
      const payload = { ...form, "amount RUB": amtNum };

      await updateTransaction(form.id, payload);

      if (pairTx && pairForm && showPair) {
        const pairAmtNum = parseFloat(parseAmount(pairForm.amount)) || 0;
        await updateTransaction(pairForm.id, {
          ...pairForm,
          "amount RUB": pairAmtNum,
        });
      }

      onSaved();
    } catch (e) {
      setError("Ошибка сохранения");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (
      !confirm(
        isTransfer && pairTx
          ? "Удалить обе строки перевода?"
          : "Удалить транзакцию?",
      )
    )
      return;
    setDeleting(true);
    try {
      await deleteTransaction(form.id, isTransfer && pairTx);
      onSaved();
    } catch (e) {
      setError("Ошибка удаления");
    } finally {
      setDeleting(false);
    }
  };

  // Парсим дату из формата шита в YYYY-MM-DD для <input type="date">
  const parseDateForInput = (dateStr) => {
    if (!dateStr) return new Date().toISOString().split("T")[0];
    // Формат "5/22/2026 10:54:14" → "2026-05-22"
    const parts = String(dateStr).split(" ")[0].split("/");
    if (parts.length === 3) {
      return `${parts[2]}-${String(parts[0]).padStart(2, "0")}-${String(parts[1]).padStart(2, "0")}`;
    }
    return dateStr;
  };

  const formatDateForSheet = (dateInput) => {
    // "2026-05-22" → "5/22/2026 12:00:00"
    const [y, m, d] = dateInput.split("-");
    return `${parseInt(m)}/${parseInt(d)}/${y} 12:00:00`;
  };

  const uiType = detectUIType(tx);
  const typeLabel =
    {
      expense: "Расход",
      income: "Доход",
      transfer: "Перевод",
      conversion: "Конвертация",
    }[uiType] || uiType;

  const typeColor = {
    expense: "var(--error)",
    income: "var(--success)",
    transfer: "var(--primary)",
    conversion: "var(--warning)",
  }[uiType];

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--overlay)",
        zIndex: 300,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        padding: "var(--sp-4)",
        animation: "fadeIn 0.15s ease",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          borderRadius:
            "var(--radius-xl) var(--radius-xl) var(--radius-lg) var(--radius-lg)",
          width: "100%",
          maxWidth: "560px",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--elev-5)",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "var(--sp-5) var(--sp-6) var(--sp-4)",
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span
            style={{
              font: "var(--font-label-small)",
              color: typeColor,
              background: `color-mix(in srgb, ${typeColor} 15%, transparent)`,
              padding: "2px 10px",
              borderRadius: "var(--radius-full)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {typeLabel}
          </span>
          <span
            style={{
              flex: 1,
              font: "var(--font-title-medium)",
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: "13px",
            }}
          >
            #{form.id}
          </span>
          <button className="btn-icon" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Scrollable body */}
        <div
          style={{
            overflowY: "auto",
            flex: 1,
            padding: "var(--sp-5) var(--sp-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
          }}
        >
          {/* Дата */}
          <Field label="Дата">
            <input
              className="input"
              type="date"
              value={parseDateForInput(form.date)}
              onChange={(e) =>
                updateField("date", formatDateForSheet(e.target.value))
              }
            />
          </Field>

          {/* Комментарий (общий для переводов) */}
          <Field label="Комментарий">
            <input
              className="input"
              value={form.comment}
              onChange={(e) => {
                updateField("comment", e.target.value);
                if (pairForm) updatePairField("comment", e.target.value);
              }}
              placeholder="Необязательно"
            />
          </Field>

          {/* Основная строка */}
          <SingleRowForm
            tx={form}
            accounts={accounts}
            reference={reference}
            currencies={currencies}
            onChange={updateField}
            label={
              isTransfer
                ? tx.type === "expense"
                  ? "Списание"
                  : "Зачисление"
                : null
            }
          />

          {/* Парная строка для переводов */}
          {isTransfer && pairTx && (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-3)",
                  marginBottom: "var(--sp-3)",
                }}
              >
                <span
                  style={{
                    font: "var(--font-label-medium)",
                    color: "var(--text-muted)",
                  }}
                >
                  Парная строка
                </span>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sp-2)",
                    cursor: "pointer",
                    font: "var(--font-body-small)",
                    color: "var(--text-muted)",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={showPair}
                    onChange={(e) => setShowPair(e.target.checked)}
                  />
                  редактировать
                </label>
              </div>
              {showPair ? (
                <SingleRowForm
                  tx={pairForm}
                  accounts={accounts}
                  reference={reference}
                  currencies={currencies}
                  onChange={updatePairField}
                  label={pairTx.type === "income" ? "Зачисление" : "Списание"}
                />
              ) : (
                <div
                  style={{
                    background: "var(--bg-input)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--sp-3) var(--sp-4)",
                    font: "var(--font-body-small)",
                    color: "var(--text-muted)",
                  }}
                >
                  #{pairTx.id} · {pairTx.type === "income" ? "+" : "−"}
                  {parseAmount(pairTx.amount)} {pairTx.currency} ·{" "}
                  {pairTx.account} — без изменений
                </div>
              )}
            </div>
          )}

          {error && (
            <div
              style={{
                color: "var(--error)",
                font: "var(--font-body-small)",
                padding: "var(--sp-2) var(--sp-3)",
                background: "var(--error-container)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "var(--sp-4) var(--sp-6)",
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: "var(--sp-3)",
          }}
        >
          <button
            onClick={handleDelete}
            disabled={deleting || loading}
            style={{
              background: "none",
              border: "1.5px solid var(--error)",
              color: "var(--error)",
              borderRadius: "var(--radius-md)",
              height: "44px",
              padding: "0 var(--sp-4)",
              cursor: "pointer",
              font: "var(--font-label-large)",
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-2)",
              opacity: deleting ? 0.6 : 1,
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "18px" }}
            >
              {deleting ? "progress_activity" : "delete"}
            </span>
            {isTransfer && pairTx ? "Удалить оба" : "Удалить"}
          </button>

          <button
            className="btn-filled"
            onClick={handleSave}
            disabled={loading || deleting}
            style={{ flex: 1, opacity: loading ? 0.7 : 1 }}
          >
            {loading ? "Сохраняем..." : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}
