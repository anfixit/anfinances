import { useState, useMemo } from "react";
import EditTransaction from "./EditTransaction";

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
  Transfer: "sync_alt",
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
    const parts = d.split("/");
    if (parts.length === 3) {
      set.add(`${parts[2]}-${String(parts[0]).padStart(2, "0")}`);
    }
  });
  return Array.from(set).sort().reverse();
}

function monthLabel(m) {
  if (!m) return "Все периоды";
  const [y, mo] = m.split("-");
  return new Date(parseInt(y), parseInt(mo) - 1).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  });
}

export default function Transactions({ moneyflow, accounts, onReload }) {
  const [search, setSearch] = useState("");
  const [showExpenses, setShowExpenses] = useState(false);
  const [showIncome, setShowIncome] = useState(false);
  const [showTransfers, setShowTransfers] = useState(false);
  const [month, setMonth] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [editTx, setEditTx] = useState(null); // транзакция для редактирования

  const allReal = useMemo(() => [...moneyflow].reverse(), [moneyflow]);
  const months = useMemo(() => getMonths(allReal), [allReal]);

  const categories = useMemo(() => {
    const set = new Set(
      allReal
        .filter((t) => t.category !== "Transfer")
        .map((t) => t.category)
        .filter(Boolean),
    );
    return Array.from(set).sort();
  }, [allReal]);

  const filtered = useMemo(() => {
    const noneSelected = !showExpenses && !showIncome && !showTransfers;
    return allReal.filter((t) => {
      const isTransfer = t.category === "Transfer";
      const isExpense = t.type === "expense" && !isTransfer;
      const isIncome = t.type === "income" && !isTransfer;
      if (noneSelected) {
        if (isTransfer) return false;
      } else {
        if (isTransfer && !showTransfers) return false;
        if (isExpense && !showExpenses) return false;
        if (isIncome && !showIncome) return false;
      }
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
  }, [
    allReal,
    showExpenses,
    showIncome,
    showTransfers,
    month,
    category,
    search,
  ]);

  const totalExpenses = filtered
    .filter((t) => t.type === "expense" && t.category !== "Transfer")
    .reduce((s, t) => s + parseFloat(t["amount RUB"] || 0), 0);
  const totalIncome = filtered
    .filter((t) => t.type === "income" && t.category !== "Transfer")
    .reduce((s, t) => s + parseFloat(t["amount RUB"] || 0), 0);

  const visible = filtered.slice(0, page * PAGE_SIZE);
  const hasMore = visible.length < filtered.length;
  const hasFilters =
    showExpenses || showIncome || showTransfers || month || category || search;

  const resetAll = () => {
    setShowExpenses(false);
    setShowIncome(false);
    setShowTransfers(false);
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

  // Найти парную строку перевода (исправлено: пустые комментарии)
  const findPair = (tx) => {
    if (tx.category !== "Transfer") return null;
    const txComment = String(tx.comment || "").trim();
    const txDate = String(tx.date || "");
    return (
      moneyflow.find((other) => {
        if (String(other.id) === String(tx.id)) return false;
        if (other.category !== "Transfer") return false;
        const sameDate = String(other.date || "") === txDate;
        const oppositeAccounts =
          other.account === tx.account_to && other.account_to === tx.account;
        const otherComment = String(other.comment || "").trim();
        const commentMatch = txComment
          ? otherComment === txComment
          : otherComment === "";
        return sameDate && oppositeAccounts && commentMatch;
      }) || null
    );
  };

  const handleRowClick = (tx) => {
    const pair = findPair(tx);
    // Для переводов открываем только expense-сторону чтобы не дублировать
    if (tx.category === "Transfer" && tx.type === "income" && pair) return;
    setEditTx({ ...tx, _pair: pair });
  };

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
    >
      {/* SEARCH */}
      <div style={{ position: "relative" }}>
        <span
          className="material-symbols-outlined"
          style={{
            position: "absolute",
            left: "var(--sp-3)",
            top: "50%",
            transform: "translateY(-50%)",
            fontSize: "20px",
            color: "var(--text-muted)",
            pointerEvents: "none",
          }}
        >
          search
        </span>
        <input
          className="input"
          placeholder="Поиск по описанию, категории, счёту..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          style={{ paddingLeft: "calc(var(--sp-3) + 28px)" }}
        />
      </div>

      {/* FILTERS */}
      <div
        style={{
          display: "flex",
          gap: "var(--sp-2)",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        {[
          {
            label: "Расходы",
            active: showExpenses,
            toggle: () => {
              setShowExpenses((v) => !v);
              setPage(1);
            },
          },
          {
            label: "Доходы",
            active: showIncome,
            toggle: () => {
              setShowIncome((v) => !v);
              setPage(1);
            },
          },
          {
            label: "Переводы",
            active: showTransfers,
            toggle: () => {
              setShowTransfers((v) => !v);
              setPage(1);
            },
          },
        ].map(({ label, active, toggle }) => (
          <button
            key={label}
            onClick={toggle}
            className={active ? "chip chip-active" : "chip"}
          >
            {label}
          </button>
        ))}

        <select
          className="input"
          value={month}
          onChange={(e) => {
            setMonth(e.target.value);
            setPage(1);
          }}
          style={{
            height: "32px",
            minHeight: "unset",
            font: "var(--font-body-small)",
            padding: "0 var(--sp-3)",
          }}
        >
          <option value="">Все периоды</option>
          {months.map((m) => (
            <option key={m} value={m}>
              {monthLabel(m)}
            </option>
          ))}
        </select>

        <select
          className="input"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
          style={{
            height: "32px",
            minHeight: "unset",
            font: "var(--font-body-small)",
            padding: "0 var(--sp-3)",
          }}
        >
          <option value="">Все категории</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        {hasFilters && (
          <button
            className="btn-text"
            onClick={resetAll}
            style={{
              minHeight: "unset",
              height: "32px",
              font: "var(--font-label-small)",
              padding: "0 var(--sp-3)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "16px" }}
            >
              close
            </span>
            Сбросить всё
          </button>
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

      {/* EMPTY */}
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

      {/* LIST */}
      {Object.entries(grouped).map(([date, txs]) => {
        const parts = date.split("/");
        let displayDate = date;
        if (parts.length === 3) {
          displayDate = new Date(
            parseInt(parts[2]),
            parseInt(parts[0]) - 1,
            parseInt(parts[1]),
          ).toLocaleDateString("ru-RU", {
            day: "numeric",
            month: "long",
            weekday: "short",
          });
        }
        return (
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
              {displayDate}
            </div>
            <div className="card-flat" style={{ overflow: "hidden" }}>
              {txs.map((t, i) => {
                const amt = parseFloat(t["amount RUB"] || 0);
                const isIncome = t.type === "income";
                const isTransfer = t.category === "Transfer";
                const isPairIncome = isTransfer && isIncome; // скрытая половина перевода

                return (
                  <div
                    key={t.id || i}
                    onClick={() => handleRowClick(t)}
                    className="list-item"
                    style={{
                      justifyContent: "space-between",
                      padding: "var(--sp-3) var(--sp-4)",
                      borderBottom:
                        i < txs.length - 1 ? "1px solid var(--border)" : "none",
                      minHeight: "64px",
                      opacity: isPairIncome ? 0.5 : isTransfer ? 0.75 : 1,
                      cursor: isPairIncome ? "default" : "pointer",
                      transition: "background 0.12s",
                    }}
                    onMouseEnter={(e) => {
                      if (!isPairIncome)
                        e.currentTarget.style.background = "var(--hover)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    {/* Icon */}
                    <div
                      style={{
                        width: "40px",
                        height: "40px",
                        borderRadius: "var(--radius-md)",
                        flexShrink: 0,
                        background: isTransfer
                          ? "var(--secondary-container)"
                          : isIncome
                            ? "color-mix(in srgb, var(--success) 15%, transparent)"
                            : "color-mix(in srgb, var(--error) 15%, transparent)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{
                          fontSize: "20px",
                          color: isTransfer
                            ? "var(--on-secondary-container)"
                            : isIncome
                              ? "var(--success)"
                              : "var(--error)",
                        }}
                      >
                        {getIcon(t.category)}
                      </span>
                    </div>

                    {/* Info */}
                    <div
                      style={{ flex: 1, minWidth: 0, padding: "0 var(--sp-3)" }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "var(--sp-2)",
                        }}
                      >
                        <span
                          style={{
                            font: "var(--font-title-small)",
                            color: "var(--text)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {t.category === "Transfer"
                            ? `${t.account} → ${t.account_to || "?"}`
                            : t.subcategory || t.category || "—"}
                        </span>
                        {!isPairIncome && t.id && (
                          <span
                            style={{
                              font: "var(--font-label-small)",
                              color: "var(--text-muted)",
                              opacity: 0.5,
                              flexShrink: 0,
                            }}
                          >
                            #{t.id}
                          </span>
                        )}
                      </div>
                      <div
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                          marginTop: "2px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {t.comment || t.account}
                      </div>
                    </div>

                    {/* Amount */}
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end",
                        gap: "2px",
                        flexShrink: 0,
                      }}
                    >
                      <span
                        style={{
                          font: "var(--font-title-small)",
                          fontFamily: "var(--font-mono)",
                          color: isTransfer
                            ? "var(--text-muted)"
                            : isIncome
                              ? "var(--success)"
                              : "var(--error)",
                        }}
                      >
                        {isIncome ? "+" : "−"}
                        {fmt(amt)}
                      </span>
                      <span
                        style={{
                          font: "var(--font-body-small)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {t.account}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* LOAD MORE */}
      {hasMore && (
        <button
          className="btn-outlined"
          onClick={() => setPage((p) => p + 1)}
          style={{ font: "var(--font-label-large)", height: "44px" }}
        >
          Показать ещё ({filtered.length - visible.length})
        </button>
      )}

      {/* EDIT MODAL */}
      {editTx && (
        <EditTransaction
          tx={editTx}
          accounts={accounts}
          onClose={() => setEditTx(null)}
          onSaved={() => {
            setEditTx(null);
            onReload();
          }}
        />
      )}
    </div>
  );
}
