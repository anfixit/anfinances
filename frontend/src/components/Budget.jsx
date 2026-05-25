import { useState, useEffect, useMemo } from "react";
import {
  getBudget,
  saveBudgetItem,
  deleteBudgetItem,
  getRecurring,
  savePlanMinItem,
  deletePlanMinItem,
} from "../api";

// ── Утилиты ──────────────────────────────────────────────────────────────────

function fmt(n) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(n);
}

function getCurrentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(m) {
  if (!m) return "";
  const [y, mo] = m.split("-");
  return new Date(parseInt(y), parseInt(mo) - 1).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  });
}

function getPrevMonth(m) {
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(y, mo - 2);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function getNextMonth(m) {
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(y, mo);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const CATEGORY_ICONS = {
  Food: "restaurant",
  Healthcare: "favorite",
  Transport: "directions_car",
  Home: "home",
  Software: "devices",
  Auto: "directions_car",
  Entertainment: "celebration",
  Communication: "phone",
  Hardware: "memory",
  Beauty: "spa",
  Pets: "pets",
  Self_Development: "school",
  Gifts_Charity: "card_giftcard",
  Taxes: "receipt",
  Bank: "account_balance",
  Clothing_Shoes: "checkroom",
  Travel: "flight",
  Public_Services: "account_balance",
  default: "attach_money",
};

const ALL_CATEGORIES = [
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

const CURRENCIES = ["RUB", "USD", "EUR", "UZS", "THB"];

// ── Прогресс-бар бюджета ─────────────────────────────────────────────────────

function ProgressBar({ spent, planned, rollover = 0 }) {
  const total = planned + rollover;
  const pct = total > 0 ? Math.min((spent / total) * 100, 100) : 0;
  const over = total > 0 && spent > total;
  return (
    <div
      style={{
        height: "6px",
        background: "var(--border)",
        borderRadius: "var(--radius-full)",
        overflow: "hidden",
        marginTop: "var(--sp-2)",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          borderRadius: "var(--radius-full)",
          background: over
            ? "var(--error)"
            : pct > 80
              ? "var(--warning)"
              : "var(--primary)",
          transition: "width 0.4s ease",
        }}
      />
    </div>
  );
}

// ── Модалка редактирования бюджетной категории ────────────────────────────────

function BudgetEditModal({ item, onSave, onClose }) {
  const [planned, setPlanned] = useState(String(item.planned || ""));
  const [notes, setNotes] = useState(item.notes || "");
  const [rollover, setRollover] = useState(item.rollover === "true");
  const [loading, setLoading] = useState(false);

  const handleSave = async () => {
    setLoading(true);
    try {
      await onSave({ ...item, planned, notes, rollover: String(rollover) });
      onClose();
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
        zIndex: 300,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--sp-4)",
        animation: "fadeIn 0.15s ease",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          borderRadius: "var(--radius-xl)",
          padding: "var(--sp-6)",
          width: "100%",
          maxWidth: "400px",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-4)",
          boxShadow: "var(--elev-5)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{ font: "var(--font-title-medium)", color: "var(--text)" }}
          >
            {item.category}
          </span>
          <button className="btn-icon" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
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
            Лимит, ₽
          </label>
          <input
            className="input"
            type="number"
            value={planned}
            onChange={(e) => setPlanned(e.target.value)}
            placeholder="0"
          />
        </div>
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
            Заметки
          </label>
          <input
            className="input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Необязательно"
          />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            padding: "var(--sp-3)",
            background: "var(--bg-input)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <input
            type="checkbox"
            id="rollover"
            checked={rollover}
            onChange={(e) => setRollover(e.target.checked)}
            style={{ width: "18px", height: "18px", cursor: "pointer" }}
          />
          <label
            htmlFor="rollover"
            style={{
              font: "var(--font-body-medium)",
              color: "var(--text)",
              cursor: "pointer",
            }}
          >
            Переносить остаток
          </label>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-3)" }}>
          <button
            className="btn-outlined"
            onClick={async () => {
              await deleteBudgetItem({
                month: item.month,
                category: item.category,
              });
              onClose();
            }}
            style={{
              flex: 1,
              color: "var(--error)",
              borderColor: "var(--error)",
            }}
          >
            Удалить
          </button>
          <button
            className="btn-filled"
            onClick={handleSave}
            disabled={loading}
            style={{ flex: 2, opacity: loading ? 0.7 : 1 }}
          >
            {loading ? "Сохраняем..." : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Модалка редактирования строки план минимума ───────────────────────────────

const EMPTY_PLAN_ITEM = {
  required: "optional",
  category: "",
  subcategory: "",
  monthly_amount: "",
  currency: "RUB",
  amount_rub: "",
  comments: "",
};

function PlanMinModal({ item, rowIndex, onSave, onClose }) {
  const isNew = rowIndex == null;
  const [form, setForm] = useState({
    required: item?.required || "optional",
    category: item?.category || "",
    subcategory: item?.subcategory || "",
    monthly_amount: item?.monthly_amount || "",
    currency: item?.currency || "RUB",
    amount_rub: String(item?.amount_rub || "").replace(/[^0-9.-]/g, "") || "",
    comments: item?.comments || "",
  });
  const [loading, setLoading] = useState(false);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  // Авторасчёт amount_rub при RUB
  const handleAmountChange = (v) => {
    set("monthly_amount", v);
    if (form.currency === "RUB") set("amount_rub", v);
  };

  const handleSave = async () => {
    if (!form.category || !form.subcategory) return;
    setLoading(true);
    try {
      await onSave({ ...form, rowIndex });
      onClose();
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
        zIndex: 300,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--sp-4)",
        animation: "fadeIn 0.15s ease",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          borderRadius: "var(--radius-xl)",
          padding: "var(--sp-6)",
          width: "100%",
          maxWidth: "480px",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-4)",
          boxShadow: "var(--elev-5)",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{ font: "var(--font-title-medium)", color: "var(--text)" }}
          >
            {isNew ? "Новая статья" : "Редактировать статью"}
          </span>
          <button className="btn-icon" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Required toggle */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "var(--sp-2)",
          }}
        >
          {[
            { val: "required", label: "Обязательный", icon: "priority_high" },
            { val: "optional", label: "Опциональный", icon: "tune" },
          ].map(({ val, label, icon }) => {
            const active = form.required === val;
            return (
              <button
                key={val}
                onClick={() => set("required", val)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "var(--sp-2)",
                  height: "44px",
                  border: "1.5px solid",
                  borderColor: active
                    ? val === "required"
                      ? "var(--error)"
                      : "var(--primary)"
                    : "var(--border)",
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  background: active
                    ? val === "required"
                      ? "var(--error-container)"
                      : "var(--primary-container)"
                    : "transparent",
                  color: active
                    ? val === "required"
                      ? "var(--error)"
                      : "var(--primary)"
                    : "var(--text-muted)",
                  font: "var(--font-label-large)",
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
            );
          })}
        </div>

        {/* Category */}
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
            Категория
          </label>
          <select
            className="input"
            value={form.category}
            onChange={(e) => set("category", e.target.value)}
          >
            <option value="">Выбери категорию</option>
            {ALL_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* Subcategory */}
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
            Подкатегория / название
          </label>
          <input
            className="input"
            value={form.subcategory}
            onChange={(e) => set("subcategory", e.target.value)}
            placeholder="Например: Аренда, Яндекс Плюс..."
          />
        </div>

        {/* Amount + Currency */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: "var(--sp-2)",
          }}
        >
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
              Сумма в месяц
            </label>
            <input
              className="input"
              type="number"
              value={form.monthly_amount}
              onChange={(e) => handleAmountChange(e.target.value)}
              placeholder="0"
            />
          </div>
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
              Валюта
            </label>
            <select
              className="input"
              value={form.currency}
              onChange={(e) => set("currency", e.target.value)}
              style={{ minWidth: "90px" }}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Amount RUB (если не RUB) */}
        {form.currency !== "RUB" && (
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
              Эквивалент в ₽
            </label>
            <input
              className="input"
              type="number"
              value={form.amount_rub}
              onChange={(e) => set("amount_rub", e.target.value)}
              placeholder="Введи вручную по текущему курсу"
            />
          </div>
        )}

        {/* Comments */}
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
            className="input"
            value={form.comments}
            onChange={(e) => set("comments", e.target.value)}
            placeholder="Необязательно"
          />
        </div>

        {/* Actions */}
        <button
          className="btn-filled"
          onClick={handleSave}
          disabled={loading || !form.category || !form.subcategory}
          style={{
            opacity: loading || !form.category || !form.subcategory ? 0.6 : 1,
          }}
        >
          {loading ? "Сохраняем..." : isNew ? "Добавить" : "Сохранить"}
        </button>
      </div>
    </div>
  );
}

// ── Вкладка «Прожиточный минимум» ────────────────────────────────────────────

function PlanMinTab({ recurring, onReload }) {
  const [editItem, setEditItem] = useState(null); // { item, rowIndex } | "new"
  const [deleting, setDeleting] = useState(null);
  const [expanded, setExpanded] = useState({});
  const toggle = (cat) => setExpanded((p) => ({ ...p, [cat]: !p[cat] }));

  // Группируем по категории, сохраняем rowIndex (1-based от данных)
  const byCategory = useMemo(() => {
    const map = {};
    recurring.forEach((r, i) => {
      const cat = r.category || "Другое";
      if (!map[cat]) map[cat] = { required: 0, optional: 0, items: [] };
      const amt =
        parseFloat(String(r.amount_rub || "").replace(/[^0-9.-]/g, "")) || 0;
      if (r.required === "required") map[cat].required += amt;
      else map[cat].optional += amt;
      map[cat].items.push({ ...r, _amt: amt, _rowIndex: i + 2 }); // +2: строка 1 = заголовок
    });
    return map;
  }, [recurring]);

  const totalRequired = Object.values(byCategory).reduce(
    (s, c) => s + c.required,
    0,
  );
  const totalOptional = Object.values(byCategory).reduce(
    (s, c) => s + c.optional,
    0,
  );

  const handleSave = async (data) => {
    await savePlanMinItem(data);
    onReload();
  };

  const handleDelete = async (rowIndex) => {
    setDeleting(rowIndex);
    try {
      await deletePlanMinItem({ rowIndex });
      onReload();
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* ── Справка ── */}
      <div
        style={{
          background: "var(--primary-container)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--sp-4) var(--sp-5)",
          display: "flex",
          gap: "var(--sp-3)",
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{
            fontSize: "20px",
            color: "var(--on-primary-container)",
            flexShrink: 0,
            marginTop: "2px",
          }}
        >
          info
        </span>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-2)",
          }}
        >
          <span
            style={{
              font: "var(--font-title-small)",
              color: "var(--on-primary-container)",
            }}
          >
            Что такое прожиточный минимум?
          </span>
          <span
            style={{
              font: "var(--font-body-small)",
              color: "var(--on-primary-container)",
              lineHeight: 1.6,
            }}
          >
            Это минимальный набор постоянных расходов — то, что нужно заплатить
            каждый месяц независимо ни от чего.
            <br />
            <br />
            <strong>Обязательные</strong> — без них не обойтись: аренда, еда,
            связь, обязательные подписки. Именно они определяют <em>runway</em>{" "}
            — сколько месяцев можно прожить на текущих сбережениях.
            <br />
            <br />
            <strong>Опциональные</strong> — желательные, но от которых можно
            отказаться в кризис: необязательные сервисы, развлечения.
            <br />
            <br />
            Сумма всех статей используется в кнопке «Импорт из плана минимума»
            при составлении ежемесячного бюджета.
          </span>
        </div>
      </div>

      {/* ── Итоги ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "var(--sp-3)",
        }}
      >
        {[
          {
            label: "Обязательно",
            value: fmt(totalRequired),
            color: "var(--error)",
          },
          {
            label: "Опционально",
            value: fmt(totalOptional),
            color: "var(--warning)",
          },
          {
            label: "Итого",
            value: fmt(totalRequired + totalOptional),
            color: "var(--text)",
          },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            className="card"
            style={{ padding: "var(--sp-3) var(--sp-4)" }}
          >
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
            <div
              style={{
                font: "var(--font-title-medium)",
                color,
                fontFamily: "var(--font-mono)",
              }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Кнопка добавить ── */}
      <button
        className="btn-outlined"
        onClick={() => setEditItem({ item: null, rowIndex: null })}
        style={{
          font: "var(--font-label-large)",
          height: "40px",
          alignSelf: "flex-start",
        }}
      >
        <span
          className="material-symbols-outlined"
          style={{ fontSize: "18px" }}
        >
          add
        </span>
        Добавить статью
      </button>

      {/* ── Список по категориям ── */}
      <div className="card-flat" style={{ overflow: "hidden" }}>
        {Object.entries(byCategory)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([cat, data], i, arr) => {
            const icon = CATEGORY_ICONS[cat] || CATEGORY_ICONS.default;
            const isOpen = expanded[cat];
            return (
              <div
                key={cat}
                style={{
                  borderBottom:
                    i < arr.length - 1 ? "1px solid var(--border)" : "none",
                }}
              >
                {/* Category header */}
                <div
                  onClick={() => toggle(cat)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sp-3)",
                    padding: "var(--sp-3) var(--sp-5)",
                    cursor: "pointer",
                    background: isOpen
                      ? "var(--primary-container)"
                      : "transparent",
                    transition: "background 0.15s",
                  }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ fontSize: "18px", color: "var(--text-muted)" }}
                  >
                    {icon}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      font: "var(--font-title-small)",
                      color: "var(--text)",
                    }}
                  >
                    {cat}
                  </span>
                  {data.required > 0 && (
                    <span
                      style={{
                        font: "var(--font-label-small)",
                        color: "var(--error)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {fmt(data.required)}
                    </span>
                  )}
                  {data.optional > 0 && (
                    <span
                      style={{
                        font: "var(--font-label-small)",
                        color: "var(--text-muted)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      +{fmt(data.optional)}
                    </span>
                  )}
                  <span
                    className="material-symbols-outlined"
                    style={{
                      fontSize: "18px",
                      color: "var(--text-muted)",
                      transform: isOpen ? "rotate(180deg)" : "none",
                      transition: "transform 0.2s",
                    }}
                  >
                    expand_more
                  </span>
                </div>

                {/* Items */}
                {isOpen &&
                  data.items.map((item, j) => (
                    <div
                      key={j}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--sp-3)",
                        padding:
                          "var(--sp-2) var(--sp-4) var(--sp-2) calc(var(--sp-5) + 26px)",
                        borderTop: "1px solid var(--border)",
                        background: "var(--bg-input)",
                      }}
                    >
                      <span
                        className="badge"
                        style={{
                          background:
                            item.required === "required"
                              ? "var(--error-container)"
                              : "var(--border)",
                          color:
                            item.required === "required"
                              ? "var(--error)"
                              : "var(--text-muted)",
                          fontSize: "11px",
                          flexShrink: 0,
                        }}
                      >
                        {item.required === "required" ? "обяз" : "опц"}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            font: "var(--font-body-small)",
                            color: "var(--text)",
                          }}
                        >
                          {item.subcategory}
                        </div>
                        {item.comments && (
                          <div
                            style={{
                              font: "var(--font-body-small)",
                              color: "var(--text-muted)",
                              marginTop: "1px",
                            }}
                          >
                            {item.comments}
                          </div>
                        )}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "flex-end",
                          gap: "1px",
                        }}
                      >
                        <span
                          style={{
                            font: "var(--font-label-small)",
                            fontFamily: "var(--font-mono)",
                            color: "var(--text)",
                          }}
                        >
                          {fmt(item._amt)}
                        </span>
                        {item.currency !== "RUB" && (
                          <span
                            style={{
                              font: "var(--font-label-small)",
                              color: "var(--text-muted)",
                            }}
                          >
                            {item.monthly_amount} {item.currency}
                          </span>
                        )}
                      </div>
                      {/* Edit button */}
                      <button
                        onClick={() =>
                          setEditItem({ item, rowIndex: item._rowIndex })
                        }
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-muted)",
                          width: "32px",
                          height: "32px",
                          borderRadius: "var(--radius-full)",
                          padding: 0,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        <span
                          className="material-symbols-outlined"
                          style={{ fontSize: "16px" }}
                        >
                          edit
                        </span>
                      </button>
                      {/* Delete button */}
                      <button
                        onClick={() => handleDelete(item._rowIndex)}
                        disabled={deleting === item._rowIndex}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--error)",
                          width: "32px",
                          height: "32px",
                          borderRadius: "var(--radius-full)",
                          padding: 0,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                          opacity: deleting === item._rowIndex ? 0.4 : 1,
                        }}
                      >
                        <span
                          className="material-symbols-outlined"
                          style={{ fontSize: "16px" }}
                        >
                          {deleting === item._rowIndex
                            ? "progress_activity"
                            : "delete"}
                        </span>
                      </button>
                    </div>
                  ))}
              </div>
            );
          })}

        {Object.keys(byCategory).length === 0 && (
          <div
            style={{
              padding: "var(--sp-12)",
              textAlign: "center",
              color: "var(--text-muted)",
              font: "var(--font-body-medium)",
            }}
          >
            Список пуст — добавь первую статью
          </div>
        )}
      </div>

      {/* Модалка */}
      {editItem && (
        <PlanMinModal
          item={editItem.item}
          rowIndex={editItem.rowIndex}
          onSave={handleSave}
          onClose={() => setEditItem(null)}
        />
      )}
    </div>
  );
}

// ── Основной компонент бюджета ────────────────────────────────────────────────

export default function Budget({ moneyflow }) {
  const [month, setMonth] = useState(getCurrentMonth);
  const [tab, setTab] = useState("budget"); // "budget" | "planmin"
  const [budget, setBudget] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [showAddCategory, setShowAddCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");

  const loadData = async () => {
    setLoading(true);
    try {
      const [b, r] = await Promise.all([getBudget(month), getRecurring()]);
      setBudget(b);
      setRecurring(r);
    } finally {
      setLoading(false);
    }
  };

  const reloadRecurring = async () => {
    const r = await getRecurring();
    setRecurring(r);
  };

  useEffect(() => {
    loadData();
  }, [month]);

  const spentByCategory = useMemo(() => {
    const map = {};
    moneyflow.forEach((t) => {
      if (t.type !== "expense" || t.category === "Transfer") return;
      const d = String(t.date || "").split(" ")[0];
      const parts = d.split("/");
      if (parts.length === 3) {
        const txMonth = `${parts[2]}-${String(parts[0]).padStart(2, "0")}`;
        if (txMonth !== month) return;
      }
      const cat = t.category || "Другое";
      map[cat] = (map[cat] || 0) + parseFloat(t["amount RUB"] || 0);
    });
    return map;
  }, [moneyflow, month]);

  const planMinByCategory = useMemo(() => {
    const map = {};
    recurring.forEach((r) => {
      if (!r.category) return;
      const amt =
        parseFloat(String(r.amount_rub || "").replace(/[^0-9.-]/g, "")) || 0;
      map[r.category] = (map[r.category] || 0) + amt;
    });
    return map;
  }, [recurring]);

  const handleSave = async (item) => {
    await saveBudgetItem(item);
    await loadData();
  };

  const handleImportFromPlanMin = async () => {
    setImporting(true);
    try {
      for (const [cat, amt] of Object.entries(planMinByCategory)) {
        if (!budget.find((b) => b.category === cat)) {
          await saveBudgetItem({
            month,
            category: cat,
            planned: String(Math.round(amt)),
            notes: "из плана минимума",
            rollover: "false",
          });
        }
      }
      await loadData();
    } finally {
      setImporting(false);
    }
  };

  const handleImportFromPrevMonth = async () => {
    setImporting(true);
    try {
      const prevBudget = await getBudget(getPrevMonth(month));
      for (const item of prevBudget) {
        if (!budget.find((b) => b.category === item.category)) {
          await saveBudgetItem({
            month,
            category: item.category,
            planned: item.planned,
            notes: item.notes || "",
            rollover: item.rollover || "false",
          });
        }
      }
      await loadData();
    } finally {
      setImporting(false);
    }
  };

  const handleAddCategory = async () => {
    if (!newCategory) return;
    await saveBudgetItem({
      month,
      category: newCategory,
      planned: "0",
      notes: "",
      rollover: "false",
    });
    setNewCategory("");
    setShowAddCategory(false);
    await loadData();
  };

  const totalPlanned = budget.reduce(
    (s, b) => s + parseFloat(b.planned || 0),
    0,
  );
  const totalSpent = budget.reduce(
    (s, b) => s + (spentByCategory[b.category] || 0),
    0,
  );
  const totalLeft = totalPlanned - totalSpent;
  const availableCategories = ALL_CATEGORIES.filter(
    (c) => !budget.find((b) => b.category === c),
  );

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* ── Вкладки ── */}
      <div
        style={{
          display: "flex",
          gap: "2px",
          background: "var(--bg-input)",
          borderRadius: "var(--radius-md)",
          padding: "4px",
        }}
      >
        {[
          { id: "budget", label: "Бюджет", icon: "account_balance_wallet" },
          { id: "planmin", label: "Прожиточный минимум", icon: "list_alt" },
        ].map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--sp-2)",
              height: "36px",
              border: "none",
              cursor: "pointer",
              borderRadius: "var(--radius-sm)",
              font: "var(--font-label-large)",
              background: tab === id ? "var(--bg-card)" : "transparent",
              color: tab === id ? "var(--primary)" : "var(--text-muted)",
              boxShadow: tab === id ? "var(--elev-1)" : "none",
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

      {/* ── Вкладка прожиточный минимум ── */}
      {tab === "planmin" && (
        <PlanMinTab recurring={recurring} onReload={reloadRecurring} />
      )}

      {/* ── Вкладка бюджет ── */}
      {tab === "budget" && (
        <>
          {/* Month nav */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <button
              className="btn-icon"
              onClick={() => setMonth(getPrevMonth(month))}
            >
              <span className="material-symbols-outlined">chevron_left</span>
            </button>
            <span
              style={{
                font: "var(--font-title-large)",
                color: "var(--text)",
                textTransform: "capitalize",
              }}
            >
              {monthLabel(month)}
            </span>
            <button
              className="btn-icon"
              onClick={() => setMonth(getNextMonth(month))}
            >
              <span className="material-symbols-outlined">chevron_right</span>
            </button>
          </div>

          {/* Summary cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "var(--sp-3)",
            }}
          >
            {[
              {
                label: "Запланировано",
                value: fmt(totalPlanned),
                icon: "event_note",
              },
              {
                label: "Потрачено",
                value: fmt(totalSpent),
                icon: "trending_down",
                color: totalSpent > 0 ? "var(--error)" : undefined,
              },
              {
                label: "Остаток",
                value: fmt(totalLeft),
                icon: "savings",
                color: totalLeft >= 0 ? "var(--success)" : "var(--error)",
              },
            ].map(({ label, value, icon, color }) => (
              <div
                key={label}
                className="card"
                style={{
                  padding: "var(--sp-3) var(--sp-4)",
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
                  }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ fontSize: "15px", color: "var(--text-muted)" }}
                  >
                    {icon}
                  </span>
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
                    font: "var(--font-title-medium)",
                    color: color || "var(--text)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div
            style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" }}
          >
            <button
              className="btn-tonal"
              onClick={handleImportFromPrevMonth}
              disabled={importing}
              style={{
                font: "var(--font-label-large)",
                height: "40px",
                minHeight: "40px",
                opacity: importing ? 0.7 : 1,
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "18px" }}
              >
                history
              </span>
              Из прошлого месяца
            </button>
            {Object.keys(planMinByCategory).length > 0 && (
              <button
                className="btn-tonal"
                onClick={handleImportFromPlanMin}
                disabled={importing}
                style={{
                  font: "var(--font-label-large)",
                  height: "40px",
                  minHeight: "40px",
                  opacity: importing ? 0.7 : 1,
                }}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "18px" }}
                >
                  download
                </span>
                Из плана минимума
              </button>
            )}
            <button
              className="btn-outlined"
              onClick={() => setShowAddCategory(true)}
              style={{
                font: "var(--font-label-large)",
                height: "40px",
                minHeight: "40px",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "18px" }}
              >
                add
              </span>
              Добавить категорию
            </button>
          </div>

          {/* Add category inline */}
          {showAddCategory && (
            <div
              style={{
                display: "flex",
                gap: "var(--sp-3)",
                alignItems: "center",
                padding: "var(--sp-4)",
                background: "var(--bg-input)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <select
                className="input"
                style={{ flex: 1 }}
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
              >
                <option value="">Выбери категорию</option>
                {availableCategories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button
                className="btn-filled"
                onClick={handleAddCategory}
                disabled={!newCategory}
                style={{ height: "40px" }}
              >
                Добавить
              </button>
              <button
                className="btn-icon"
                onClick={() => setShowAddCategory(false)}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                padding: "var(--sp-12)",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{
                  animation: "spin 1s linear infinite",
                  fontSize: "32px",
                  color: "var(--primary)",
                }}
              >
                progress_activity
              </span>
            </div>
          )}

          {/* Empty state */}
          {!loading && budget.length === 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                padding: "var(--sp-12)",
                gap: "var(--sp-4)",
                textAlign: "center",
              }}
            >
              <div
                style={{
                  width: "72px",
                  height: "72px",
                  borderRadius: "var(--radius-full)",
                  background: "var(--primary-container)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <span
                  className="material-symbols-outlined"
                  style={{
                    fontSize: "32px",
                    color: "var(--on-primary-container)",
                  }}
                >
                  account_balance_wallet
                </span>
              </div>
              <div>
                <div
                  style={{
                    font: "var(--font-title-medium)",
                    color: "var(--text)",
                    marginBottom: "var(--sp-2)",
                  }}
                >
                  Бюджет не настроен
                </div>
                <div
                  style={{
                    font: "var(--font-body-medium)",
                    color: "var(--text-muted)",
                  }}
                >
                  Импортируй из плана минимума или из прошлого месяца
                </div>
              </div>
            </div>
          )}

          {/* Budget list */}
          {!loading && budget.length > 0 && (
            <div className="card-flat" style={{ overflow: "hidden" }}>
              {budget.map((item, i) => {
                const spent = spentByCategory[item.category] || 0;
                const planned = parseFloat(item.planned || 0);
                const rollover = parseFloat(item.rollover_amount || 0);
                const left = planned + rollover - spent;
                const over = left < 0;
                const icon =
                  CATEGORY_ICONS[item.category] || CATEGORY_ICONS.default;
                return (
                  <div
                    key={item.category}
                    onClick={() => setEditItem(item)}
                    style={{
                      padding: "var(--sp-4) var(--sp-5)",
                      borderBottom:
                        i < budget.length - 1
                          ? "1px solid var(--border)"
                          : "none",
                      cursor: "pointer",
                      transition: "background 0.15s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background = "var(--hover)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--sp-3)",
                        marginBottom: "var(--sp-2)",
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: "18px", color: "var(--text-muted)" }}
                      >
                        {icon}
                      </span>
                      <span
                        style={{
                          flex: 1,
                          font: "var(--font-title-small)",
                          color: "var(--text)",
                        }}
                      >
                        {item.category}
                      </span>
                      {item.rollover === "true" && rollover !== 0 && (
                        <span
                          style={{
                            font: "var(--font-label-small)",
                            color:
                              rollover > 0 ? "var(--success)" : "var(--error)",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          {rollover > 0 ? "+" : ""}
                          {fmt(rollover)}
                        </span>
                      )}
                      <span
                        style={{
                          font: "var(--font-title-small)",
                          fontFamily: "var(--font-mono)",
                          color: over ? "var(--error)" : "var(--text)",
                        }}
                      >
                        {fmt(left)}
                      </span>
                      <span
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        / {fmt(planned)}
                      </span>
                    </div>
                    <ProgressBar
                      spent={spent}
                      planned={planned}
                      rollover={rollover}
                    />
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        marginTop: "var(--sp-1)",
                      }}
                    >
                      <span
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {fmt(spent)} потрачено
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Unbudgeted */}
          {(() => {
            const unbudgeted = Object.entries(spentByCategory).filter(
              ([cat]) => !budget.find((b) => b.category === cat),
            );
            if (unbudgeted.length === 0) return null;
            return (
              <div>
                <div
                  style={{
                    font: "var(--font-label-medium)",
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    marginBottom: "var(--sp-2)",
                    padding: "0 var(--sp-1)",
                  }}
                >
                  Без лимита
                </div>
                <div className="card-flat" style={{ overflow: "hidden" }}>
                  {unbudgeted.map(([cat, spent], i) => {
                    const icon = CATEGORY_ICONS[cat] || CATEGORY_ICONS.default;
                    return (
                      <div
                        key={cat}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "var(--sp-3)",
                          padding: "var(--sp-3) var(--sp-5)",
                          borderBottom:
                            i < unbudgeted.length - 1
                              ? "1px solid var(--border)"
                              : "none",
                        }}
                      >
                        <span
                          className="material-symbols-outlined"
                          style={{
                            fontSize: "18px",
                            color: "var(--text-muted)",
                          }}
                        >
                          {icon}
                        </span>
                        <span
                          style={{
                            flex: 1,
                            font: "var(--font-body-medium)",
                            color: "var(--text-muted)",
                          }}
                        >
                          {cat}
                        </span>
                        <span
                          style={{
                            font: "var(--font-title-small)",
                            fontFamily: "var(--font-mono)",
                            color: "var(--text)",
                          }}
                        >
                          {fmt(spent)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </>
      )}

      {/* Edit modal */}
      {editItem && (
        <BudgetEditModal
          item={editItem}
          onSave={handleSave}
          onClose={() => {
            setEditItem(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}
