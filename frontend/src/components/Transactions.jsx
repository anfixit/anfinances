import { useState, useMemo } from "react";

function fmt(n) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(n);
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
  Income: "payments",
  Salary: "payments",
  Freelance: "work",
  default: "attach_money",
};

function getIcon(category) {
  return CATEGORY_ICONS[category] || CATEGORY_ICONS.default;
}

const PAGE_SIZE = 20;

function getMonths(txs) {
  const set = new Set();
  txs.forEach((t) => {
    const d = String(t.date || "").split(" ")[0];
    if (!d) return;
    const parts = d.split("/");
    if (parts.length === 3) {
      const month = `${parts[2]}-${String(parts[0]).padStart(2, "0")}`;
      set.add(month);
    }
  });
  return Array.from(set).sort().reverse();
}

function monthLabel(m) {
  if (!m) return "Все периоды";
  const [y, mo] = m.split("-");
  const date = new Date(parseInt(y), parseInt(mo) - 1);
  return date.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
}

export default function Transactions({ moneyflow }) {
  const [search, setSearch] = useState("");
  const [types, setTypes] = useState([]);
  const [month, setMonth] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);

  const allReal = useMemo(
    () => [...moneyflow].filter((t) => t.category !== "Transfer").reverse(),
    [moneyflow],
  );

  const months = useMemo(() => getMonths(allReal), [allReal]);

  const categories = useMemo(() => {
    const set = new Set(allReal.map((t) => t.category).filter(Boolean));
    return Array.from(set).sort();
  }, [allReal]);

  const toggleType = (t) => {
    setTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
    setPage(1);
  };

  const filtered = useMemo(() => {
    return allReal.filter((t) => {
      if (types.length > 0 && !types.includes(t.type)) return false;
      if (month) {
        const d = String(t.date || "").split(" ")[0];
        const parts = d.split("/");
        if (parts.length === 3) {
          const txMonth = `${parts[2]}-${String(parts[0]).padStart(2, "0")}`;
          if (txMonth !== month) return false;
        }
      }
      if (category && t.category !== category) return false;
      if (search) {
        const q = search.toLowerCase();
        const hay = [t.comment, t.category, t.subcategory, t.account]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allReal, types, month, category, search]);

  const totalExpenses = filtered
    .filter((t) => t.type === "expense")
    .reduce((s, t) => s + parseFloat(t["amount RUB"] || 0), 0);

  const totalIncome = filtered
    .filter((t) => t.type === "income")
    .reduce((s, t) => s + parseFloat(t["amount RUB"] || 0), 0);

  const visible = filtered.slice(0, page * PAGE_SIZE);
  const hasMore = visible.length < filtered.length;
  const hasFilters = types.length > 0 || month || category || search;

  const resetAll = () => {
    setTypes([]);
    setMonth("");
    setCategory("");
    setSearch("");
    setPage(1);
  };

  const grouped = useMemo(() => {
    return visible.reduce((acc, t) => {
      const d = String(t.date || "").split(" ")[0] || "Без даты";
      if (!acc[d]) acc[d] = [];
      acc[d].push(t);
      return acc;
    }, {});
  }, [visible]);

  if (allReal.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--sp-4)",
          padding: "var(--sp-12) var(--sp-6)",
          color: "var(--text-muted)",
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
            receipt_long
          </span>
        </div>
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              font: "var(--font-title-medium)",
              color: "var(--text)",
              marginBottom: "var(--sp-2)",
            }}
          >
            Нет транзакций
          </div>
          <div
            style={{
              font: "var(--font-body-medium)",
              color: "var(--text-muted)",
            }}
          >
            Добавь первую операцию через кнопку «Добавить»
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* FILTER BAR */}
      <div
        className="card"
        style={{
          padding: "var(--sp-4)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-3)",
        }}
      >
        {/* Search + type chips */}
        <div
          style={{
            display: "flex",
            gap: "var(--sp-3)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <div
            style={{
              position: "relative",
              flex: "1 1 200px",
              minWidth: "180px",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{
                position: "absolute",
                left: "12px",
                top: "50%",
                transform: "translateY(-50%)",
                fontSize: "18px",
                color: "var(--text-muted)",
                pointerEvents: "none",
              }}
            >
              search
            </span>
            <input
              type="text"
              placeholder="Поиск по комментарию, категории..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              style={{ paddingLeft: "40px" }}
            />
          </div>

          <div style={{ display: "flex", gap: "var(--sp-2)" }}>
            {[
              { id: "expense", label: "Расходы", icon: "trending_down" },
              { id: "income", label: "Доходы", icon: "trending_up" },
            ].map(({ id, label, icon }) => (
              <button
                key={id}
                className={`chip ${types.includes(id) ? "active" : ""}`}
                onClick={() => toggleType(id)}
                style={{ minHeight: "unset", minWidth: "unset" }}
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "14px" }}
                >
                  {icon}
                </span>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Month + category selects */}
        <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" }}>
          <select
            value={month}
            onChange={(e) => {
              setMonth(e.target.value);
              setPage(1);
            }}
            style={{ flex: "1 1 160px", minWidth: "140px", minHeight: "40px" }}
          >
            <option value="">Все периоды</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
              </option>
            ))}
          </select>

          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
            style={{ flex: "1 1 160px", minWidth: "140px", minHeight: "40px" }}
          >
            <option value="">Все категории</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* Active filter tags */}
        {hasFilters && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-2)",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                font: "var(--font-label-small)",
                color: "var(--text-muted)",
              }}
            >
              Активно:
            </span>
            {types.map((t) => (
              <span
                key={t}
                className="badge badge-primary"
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
                onClick={() => toggleType(t)}
              >
                {t === "expense" ? "Расходы" : "Доходы"}
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "12px" }}
                >
                  close
                </span>
              </span>
            ))}
            {month && (
              <span
                className="badge badge-primary"
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
                onClick={() => setMonth("")}
              >
                {monthLabel(month)}{" "}
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "12px" }}
                >
                  close
                </span>
              </span>
            )}
            {category && (
              <span
                className="badge badge-primary"
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
                onClick={() => setCategory("")}
              >
                {category}{" "}
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "12px" }}
                >
                  close
                </span>
              </span>
            )}
            {search && (
              <span
                className="badge badge-primary"
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
                onClick={() => setSearch("")}
              >
                «{search}»{" "}
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "12px" }}
                >
                  close
                </span>
              </span>
            )}
            <button
              className="btn-text"
              onClick={resetAll}
              style={{
                font: "var(--font-label-small)",
                color: "var(--text-muted)",
                minHeight: "unset",
                padding: "2px var(--sp-2)",
              }}
            >
              Сбросить всё
            </button>
          </div>
        )}
      </div>

      {/* STATS */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "var(--sp-3)",
        }}
      >
        {[
          {
            label: "Найдено",
            value: `${filtered.length} операций`,
            icon: "filter_list",
            color: null,
          },
          {
            label: "Расходы",
            value: fmt(totalExpenses),
            icon: "trending_down",
            color: "var(--error)",
          },
          {
            label: "Доходы",
            value: fmt(totalIncome),
            icon: "trending_up",
            color: "var(--success)",
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

      {/* EMPTY FILTERED STATE */}
      {filtered.length === 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "var(--sp-12)",
            gap: "var(--sp-3)",
            color: "var(--text-muted)",
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: "40px" }}
          >
            search_off
          </span>
          <div style={{ font: "var(--font-title-small)" }}>
            Ничего не найдено
          </div>
          <button
            className="btn-outlined"
            onClick={resetAll}
            style={{ minHeight: "40px", font: "var(--font-label-medium)" }}
          >
            Сбросить фильтры
          </button>
        </div>
      )}

      {/* TRANSACTION LIST */}
      {Object.entries(grouped).map(([date, txs]) => (
        <div key={date}>
          <div
            style={{
              font: "var(--font-label-small)",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginBottom: "var(--sp-2)",
              padding: "0 var(--sp-1)",
            }}
          >
            {date}
          </div>

          <div className="card-flat" style={{ overflow: "hidden" }}>
            {txs.map((t, i) => {
              const amt = parseFloat(t["amount RUB"] || 0);
              const isIncome = t.type === "income";
              return (
                <div
                  key={i}
                  className="list-item"
                  style={{
                    justifyContent: "space-between",
                    padding: "var(--sp-3) var(--sp-4)",
                    borderBottom:
                      i < txs.length - 1 ? "1px solid var(--border)" : "none",
                    minHeight: "64px",
                  }}
                >
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "var(--radius-md)",
                      flexShrink: 0,
                      background: isIncome
                        ? "var(--success-container)"
                        : "var(--primary-container)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: "20px",
                        color: isIncome
                          ? "var(--on-success-container)"
                          : "var(--on-primary-container)",
                      }}
                    >
                      {getIcon(t.category)}
                    </span>
                  </div>

                  <div
                    style={{ flex: 1, minWidth: 0, margin: "0 var(--sp-3)" }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--sp-2)",
                        marginBottom: "2px",
                      }}
                    >
                      <span
                        style={{
                          font: "var(--font-title-small)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {t.subcategory ||
                          t.category ||
                          (isIncome ? "Доход" : "Расход")}
                      </span>
                      {t.required === "required" && (
                        <span
                          className="badge badge-error"
                          style={{ flexShrink: 0 }}
                        >
                          обяз.
                        </span>
                      )}
                    </div>
                    {t.comment && (
                      <div
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {t.comment}
                      </div>
                    )}
                    <div
                      style={{
                        font: "var(--font-body-small)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {t.account}
                    </div>
                  </div>

                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div
                      style={{
                        font: "var(--font-title-small)",
                        fontFamily: "var(--font-mono)",
                        color: isIncome ? "var(--success)" : "var(--error)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {isIncome ? "+" : "−"}
                      {fmt(amt)}
                    </div>
                    <div
                      style={{
                        font: "var(--font-body-small)",
                        color: "var(--text-muted)",
                        marginTop: "2px",
                      }}
                    >
                      {t.currency}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* LOAD MORE */}
      {hasMore && (
        <div style={{ textAlign: "center", padding: "var(--sp-2)" }}>
          <button
            className="btn-outlined"
            onClick={() => setPage((p) => p + 1)}
            style={{
              minHeight: "44px",
              font: "var(--font-label-large)",
              gap: "var(--sp-2)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "18px" }}
            >
              expand_more
            </span>
            Показать ещё ({filtered.length - visible.length})
          </button>
        </div>
      )}
    </div>
  );
}
