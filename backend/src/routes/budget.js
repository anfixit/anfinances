const express = require("express");
const {
  getSheet,
  getRawRows,
  updateRange,
  appendRow,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

function parseAmount(str) {
  if (!str) return 0;
  const num = parseFloat(String(str).replace(/[^0-9.-]/g, ""));
  return isNaN(num) ? 0 : num;
}

// Парсит "M/D/YYYY HH:MM:SS" → "YYYY-MM"
function txDateToMonth(dateStr) {
  if (!dateStr) return null;
  const datePart = String(dateStr).split(" ")[0];
  const parts = datePart.split("/");
  if (parts.length !== 3) return null;
  return `${parts[2]}-${String(parts[0]).padStart(2, "0")}`;
}

// Предыдущий месяц от "YYYY-MM"
function prevMonth(m) {
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(y, mo - 2);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// Рассчитывает rollover_amount для каждой строки бюджета.
// rollover_amount = (planned + rollover_amount_prev - spent_prev), если у предыдущего месяца rollover=true.
async function enrichWithRollover(budgetRows) {
  if (!budgetRows.length) return budgetRows;

  const moneyflow = await getSheet("moneyflow");

  // Группируем расходы по {month, category}
  const spentByMonthCat = {};
  moneyflow.forEach((t) => {
    if (t.type !== "expense" || t.category === "Transfer") return;
    const m = txDateToMonth(t.date);
    if (!m) return;
    const key = `${m}|${t.category}`;
    spentByMonthCat[key] =
      (spentByMonthCat[key] || 0) + parseAmount(t["amount RUB"]);
  });

  // Полная история бюджета по {month, category}
  const allBudget = await getSheet("budget");
  const budgetByKey = {};
  allBudget.forEach((b) => {
    if (b.month && b.category) {
      budgetByKey[`${b.month}|${b.category}`] = b;
    }
  });

  // Рекурсивно считаем rollover для категории
  // (с мемоизацией чтобы не пересчитывать одно и то же)
  const cache = {};
  function calcRolloverFor(month, category) {
    const key = `${month}|${category}`;
    if (cache[key] !== undefined) return cache[key];

    const pm = prevMonth(month);
    const prev = budgetByKey[`${pm}|${category}`];
    if (!prev || String(prev.rollover).toLowerCase() !== "true") {
      cache[key] = 0;
      return 0;
    }

    const prevPlanned = parseAmount(prev.planned);
    const prevRollover = calcRolloverFor(pm, category);
    const prevSpent = spentByMonthCat[`${pm}|${category}`] || 0;
    const leftover = prevPlanned + prevRollover - prevSpent;

    cache[key] = leftover;
    return leftover;
  }

  return budgetRows.map((b) => ({
    ...b,
    rollover_amount: calcRolloverFor(b.month, b.category),
  }));
}

router.get("/", async (req, res) => {
  try {
    const data = await getSheet("budget");
    const { month } = req.query;
    const filtered = (
      month ? data.filter((r) => r.month === month) : data
    ).filter((r) => r.month);
    const enriched = await enrichWithRollover(filtered);
    res.json(enriched);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch budget" });
  }
});

router.post("/", async (req, res) => {
  try {
    const { month, category, planned, notes, rollover } = req.body;
    if (!month || !category)
      return res.status(400).json({ error: "month and category required" });

    const rows = await getRawRows("budget");
    const rowIndex = rows.findIndex(
      (r, i) => i > 0 && r[0] === month && r[1] === category,
    );
    const values = [
      [month, category, planned, notes || "", rollover || "false"],
    ];

    if (rowIndex > 0) {
      await updateRange(`budget!A${rowIndex + 1}:E${rowIndex + 1}`, values);
    } else {
      await appendRow("budget", {
        month,
        category,
        planned,
        notes: notes || "",
        rollover: rollover || "false",
      });
    }
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to save budget" });
  }
});

router.delete("/", async (req, res) => {
  try {
    const { month, category } = req.body;
    const rows = await getRawRows("budget");
    const rowIndex = rows.findIndex(
      (r, i) => i > 0 && r[0] === month && r[1] === category,
    );
    if (rowIndex < 1) return res.status(404).json({ error: "Not found" });
    await deleteRow("budget", rowIndex + 1);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to delete budget row" });
  }
});

module.exports = router;
