import { useState, useEffect, useMemo } from "react";
import {
  getBudget,
  saveBudgetItem,
  deleteBudgetItem,
  getRecurring,
} from "../api";

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

function EditModal({ item, onSave, onClose }) {
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
          <span style={{ font: "var(--font-title-large)" }}>
            {item.category}
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              minWidth: "unset",
              width: "40px",
              height: "40px",
              borderRadius: "var(--radius-full)",
              padding: 0,
            }}
          >
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
            type="number"
            value={planned}
            onChange={(e) => setPlanned(e.target.value)}
            placeholder="0"
            autoFocus
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
            Заметка
          </label>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="необязательно"
          />
        </div>

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            cursor: "pointer",
            font: "var(--font-body-medium)",
            background: "var(--bg-card-2)",
            borderRadius: "var(--radius-md)",
            padding: "var(--sp-3) var(--sp-4)",
          }}
        >
          <input
            type="checkbox"
            checked={rollover}
            onChange={(e) => setRollover(e.target.checked)}
          />
          <div>
            <div style={{ fontWeight: 600 }}>Переносить остаток</div>
            <div
              style={{
                font: "var(--font-body-small)",
                color: "var(--text-muted)",
              }}
            >
              Неиспользованный лимит добавится к следующему месяцу
            </div>
          </div>
        </label>

        <button
          onClick={handleSave}
          disabled={loading}
          style={{
            background: "var(--primary)",
            color: "var(--on-primary)",
            border: "none",
            borderRadius: "var(--radius-xl)",
            height: "52px",
            font: "var(--font-title-small)",
            cursor: "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "Сохраняем..." : "Сохранить"}
        </button>
      </div>
    </div>
  );
}

export default function Budget({ moneyflow }) {
  const [month, setMonth] = useState(getCurrentMonth);
  const [budget, setBudget] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editItem, setEditItem] = useState(null);
  const [showAddCategory, setShowAddCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");

  const loadBudget = async () => {
    setLoading(true);
    try {
      const [b, r] = await Promise.all([getBudget(month), getRecurring()]);
      setBudget(b);
      setRecurring(r);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBudget();
  }, [month]);

  // Расходы текущего месяца по категориям
  const spentByCategory = useMemo(() => {
    const map = {};
    moneyflow.forEach((t) => {
      if (t.type !== "expense" || t.category === "Transfer") return;
      // Проверяем месяц транзакции
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

  // plan_min по категориям
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
    await loadBudget();
  };

  const handleDelete = async (item) => {
    await deleteBudgetItem({ month: item.month, category: item.category });
    await loadBudget();
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
    await loadBudget();
  };

  const handleImportFromPlanMin = async () => {
    const entries = Object.entries(planMinByCategory);
    for (const [cat, amt] of entries) {
      const exists = budget.find((b) => b.category === cat);
      if (!exists) {
        await saveBudgetItem({
          month,
          category: cat,
          planned: String(Math.round(amt)),
          notes: "из plan_min",
          rollover: "false",
        });
      }
    }
    await loadBudget();
  };

  // Суммарные данные
  const totalPlanned = budget.reduce(
    (s, b) => s + parseFloat(b.planned || 0),
    0,
  );
  const totalSpent = budget.reduce(
    (s, b) => s + (spentByCategory[b.category] || 0),
    0,
  );
  const totalLeft = totalPlanned - totalSpent;

  // Категории которых ещё нет в бюджете
  const availableCategories = ALL_CATEGORIES.filter(
    (c) => !budget.find((b) => b.category === c),
  );

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* MONTH NAVIGATION */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--sp-3)",
        }}
      >
        <button
          className="btn-outlined"
          onClick={() => setMonth(getPrevMonth(month))}
          style={{ width: "48px", minWidth: "48px", padding: 0 }}
        >
          <span className="material-symbols-outlined">chevron_left</span>
        </button>

        <div
          style={{
            font: "var(--font-headline-small)",
            letterSpacing: "-0.02em",
            textAlign: "center",
            textTransform: "capitalize",
          }}
        >
          {monthLabel(month)}
        </div>

        <button
          className="btn-outlined"
          onClick={() => setMonth(getNextMonth(month))}
          style={{ width: "48px", minWidth: "48px", padding: 0 }}
        >
          <span className="material-symbols-outlined">chevron_right</span>
        </button>
      </div>

      {/* SUMMARY CARDS */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "var(--sp-3)",
        }}
      >
        {[
          {
            label: "Запланировано",
            value: fmt(totalPlanned),
            icon: "event_note",
            color: null,
          },
          {
            label: "Потрачено",
            value: fmt(totalSpent),
            icon: "trending_down",
            color: "var(--error)",
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

      {/* ACTIONS */}
      <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" }}>
        {budget.length === 0 && Object.keys(planMinByCategory).length > 0 && (
          <button
            className="btn-tonal"
            onClick={handleImportFromPlanMin}
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
              download
            </span>
            Импорт из plan_min
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

      {/* LOADING */}
      {loading && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            padding: "var(--sp-12)",
            color: "var(--text-muted)",
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

      {/* EMPTY STATE */}
      {!loading && budget.length === 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "var(--sp-12)",
            gap: "var(--sp-4)",
            color: "var(--text-muted)",
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
              style={{ fontSize: "32px", color: "var(--on-primary-container)" }}
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
            <div style={{ font: "var(--font-body-medium)" }}>
              {Object.keys(planMinByCategory).length > 0
                ? "Импортируй категории из plan_min или добавь вручную"
                : "Добавь категории с лимитами"}
            </div>
          </div>
        </div>
      )}

      {/* BUDGET LIST */}
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
                style={{
                  padding: "var(--sp-4) var(--sp-5)",
                  borderBottom:
                    i < budget.length - 1 ? "1px solid var(--border)" : "none",
                  cursor: "pointer",
                  transition: "background 0.15s",
                }}
                onClick={() => setEditItem(item)}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background =
                    "color-mix(in srgb, var(--primary) 4%, transparent)")
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
                  }}
                >
                  {/* Icon */}
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "var(--radius-md)",
                      background: over
                        ? "var(--error-container)"
                        : "var(--primary-container)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: "20px",
                        color: over
                          ? "var(--error)"
                          : "var(--on-primary-container)",
                      }}
                    >
                      {icon}
                    </span>
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        marginBottom: "var(--sp-1)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "var(--sp-2)",
                        }}
                      >
                        <span style={{ font: "var(--font-title-small)" }}>
                          {item.category}
                        </span>
                        {item.rollover === "true" && (
                          <span
                            className="badge badge-primary"
                            style={{ fontSize: "10px" }}
                          >
                            rollover
                          </span>
                        )}
                        {over && (
                          <span className="badge badge-error">перерасход</span>
                        )}
                      </div>
                      <div
                        style={{
                          textAlign: "right",
                          flexShrink: 0,
                          marginLeft: "var(--sp-3)",
                        }}
                      >
                        <span
                          style={{
                            font: "var(--font-title-small)",
                            fontFamily: "var(--font-mono)",
                            color: over ? "var(--error)" : "var(--text)",
                          }}
                        >
                          {fmt(spent)}
                        </span>
                        <span
                          style={{
                            font: "var(--font-body-small)",
                            color: "var(--text-muted)",
                          }}
                        >
                          {" "}
                          / {fmt(planned)}
                        </span>
                      </div>
                    </div>

                    <ProgressBar
                      spent={spent}
                      planned={planned}
                      rollover={rollover}
                    />

                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginTop: "var(--sp-1)",
                      }}
                    >
                      {item.notes && (
                        <span
                          style={{
                            font: "var(--font-body-small)",
                            color: "var(--text-muted)",
                          }}
                        >
                          {item.notes}
                        </span>
                      )}
                      <span
                        style={{
                          font: "var(--font-body-small)",
                          color: over ? "var(--error)" : "var(--text-muted)",
                          marginLeft: "auto",
                        }}
                      >
                        {over
                          ? `перерасход ${fmt(Math.abs(left))}`
                          : `осталось ${fmt(left)}`}
                      </span>
                    </div>
                  </div>

                  {/* Delete */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(item);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted)",
                      minWidth: "unset",
                      width: "36px",
                      height: "36px",
                      borderRadius: "var(--radius-full)",
                      padding: 0,
                      flexShrink: 0,
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "18px" }}
                    >
                      delete
                    </span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* NOT BUDGETED — категории с расходами но без лимита */}
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
                      cursor: "pointer",
                      transition: "background 0.15s",
                    }}
                    onClick={() =>
                      setEditItem({
                        month,
                        category: cat,
                        planned: "",
                        notes: "",
                        rollover: "false",
                      })
                    }
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background =
                        "color-mix(in srgb, var(--primary) 4%, transparent)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    <div
                      style={{
                        width: "40px",
                        height: "40px",
                        borderRadius: "var(--radius-md)",
                        background: "var(--warning-container)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: "20px", color: "var(--warning)" }}
                      >
                        {icon}
                      </span>
                    </div>
                    <div style={{ flex: 1 }}>
                      <span style={{ font: "var(--font-title-small)" }}>
                        {cat}
                      </span>
                      <div
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                        }}
                      >
                        Нет лимита — нажми чтобы добавить
                      </div>
                    </div>
                    <span
                      style={{
                        font: "var(--font-title-small)",
                        fontFamily: "var(--font-mono)",
                        color: "var(--warning)",
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

      {/* ADD CATEGORY MODAL */}
      {showAddCategory && (
        <div
          onClick={(e) =>
            e.target === e.currentTarget && setShowAddCategory(false)
          }
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
              <span style={{ font: "var(--font-title-large)" }}>
                Добавить категорию
              </span>
              <button
                onClick={() => setShowAddCategory(false)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  minWidth: "unset",
                  width: "40px",
                  height: "40px",
                  borderRadius: "var(--radius-full)",
                  padding: 0,
                }}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            >
              <option value="">— выбрать —</option>
              {availableCategories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button
              onClick={handleAddCategory}
              disabled={!newCategory}
              style={{
                background: "var(--primary)",
                color: "var(--on-primary)",
                border: "none",
                borderRadius: "var(--radius-xl)",
                height: "52px",
                font: "var(--font-title-small)",
                cursor: "pointer",
                opacity: newCategory ? 1 : 0.5,
              }}
            >
              Добавить
            </button>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editItem && (
        <EditModal
          item={editItem}
          onSave={handleSave}
          onClose={() => setEditItem(null)}
        />
      )}
    </div>
  );
}
