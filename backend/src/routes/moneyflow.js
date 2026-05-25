const express = require("express");
const crypto = require("crypto"); // Добавили встроенный модуль для UUID
const {
  getSheet,
  getRawRows,
  appendRow,
  appendRows, // <-- Импортируем новую функцию
  updateRange,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

// Безопасный парсинг чисел (понимает запятую как разделитель дробей)
function parseAmount(amountStr) {
  if (typeof amountStr === "number") return amountStr;
  if (!amountStr) return 0;
  // Заменяем запятую на точку и вычищаем всё, кроме цифр, минуса и точки
  const sanitized = String(amountStr)
    .replace(",", ".")
    .replace(/[^0-9.-]/g, "");
  return parseFloat(sanitized) || 0;
}

// Пересчёт amount RUB
async function calcAmountRub(amount, currency) {
  if (!currency || currency === "RUB") return parseAmount(amount);
  try {
    const rates = await getSheet("rates");
    const row = rates.find((r) => r.currency === currency);
    if (row && row.rate) return parseAmount(amount) * parseAmount(row.rate);
  } catch (e) {
    console.warn("calcAmountRub failed:", e.message);
  }
  return parseAmount(amount);
}

// GET /api/moneyflow
router.get("/", async (req, res) => {
  try {
    const data = await getSheet("moneyflow");
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch moneyflow" });
  }
});

// POST /api/moneyflow — добавить транзакцию
router.post("/", async (req, res) => {
  try {
    const newId = crypto.randomUUID(); // Генерируем надежный уникальный ID

    const payload = { ...req.body, id: newId };
    if (payload.pair_id === undefined) payload.pair_id = "";

    await appendRow("moneyflow", payload);
    res.json({ success: true, id: newId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transaction" });
  }
});

// POST /api/moneyflow/transfer — атомарно создать пару строк
router.post("/transfer", async (req, res) => {
  try {
    const { expense, income, fee } = req.body;
    if (!expense || !income) {
      return res.status(400).json({ error: "expense and income required" });
    }

    const firstId = crypto.randomUUID();
    const secondId = crypto.randomUUID();

    // Собираем все строки в один массив
    const rowsToInsert = [
      { ...expense, id: firstId, pair_id: firstId },
      { ...income, id: secondId, pair_id: firstId },
    ];

    if (fee) {
      rowsToInsert.push({ ...fee, id: crypto.randomUUID(), pair_id: "" });
    }

    // Вызываем новую функцию атомарной вставки!
    await appendRows("moneyflow", rowsToInsert);

    res.json({ success: true, ids: [firstId, secondId], pair_id: firstId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transfer" });
  }
});

// PUT /api/moneyflow/:id — обновить транзакцию
router.put("/:id", async (req, res) => {
  try {
    // ВАЖНО: теперь id это строка, не делаем parseInt
    const targetId = String(req.params.id);
    const rows = await getRawRows("moneyflow");
    const rowIndex = rows.findIndex(
      (row, i) => i > 0 && String(row[0]) === targetId,
    );
    if (rowIndex < 1)
      return res.status(404).json({ error: "Transaction not found" });

    const sheetRow = rowIndex + 1;
    const body = req.body;
    const existing = rows[rowIndex];

    const currency = body.currency ?? existing[9];
    const rawAmount = body.amount ?? existing[5];
    const numericAmount = parseAmount(rawAmount); // Используем безопасный парсер
    const amountRub = await calcAmountRub(numericAmount, currency);

    const values = [
      [
        targetId,
        body.pair_id ?? existing[1] ?? "",
        body.date ?? existing[2],
        body.type ?? existing[3],
        body.required ?? existing[4],
        body.amount ?? existing[5],
        amountRub,
        body.account ?? existing[7],
        body.account_to ?? existing[8],
        currency,
        body.category ?? existing[10],
        body.subcategory ?? existing[11],
        body.comment ?? existing[12],
      ],
    ];

    await updateRange(`moneyflow!A${sheetRow}:M${sheetRow}`, values);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to update transaction" });
  }
});

// DELETE /api/moneyflow/:id — физически удалить
router.delete("/:id", async (req, res) => {
  try {
    const targetId = String(req.params.id); // Также сравниваем как строку
    const deletePair = req.query.pair === "true";
    const rows = await getRawRows("moneyflow");

    const targetRowIndex = rows.findIndex(
      (row, i) => i > 0 && String(row[0]) === targetId,
    );
    if (targetRowIndex < 1)
      return res.status(404).json({ error: "Transaction not found" });

    const toDelete = [targetRowIndex + 1];

    if (deletePair) {
      const targetRow = rows[targetRowIndex];
      const targetPairId = targetRow[1];

      let pairRowIndex = -1;

      if (targetPairId && String(targetPairId).trim() !== "") {
        pairRowIndex = rows.findIndex((row, i) => {
          if (i === 0 || String(row[0]) === targetId) return false;
          return String(row[1]) === String(targetPairId);
        });
      }

      if (pairRowIndex < 1) {
        const targetDate = targetRow[2];
        const targetAccount = targetRow[7];
        const targetAccountTo = targetRow[8];
        const targetComment = String(targetRow[12] || "").trim();

        pairRowIndex = rows.findIndex((row, i) => {
          if (i === 0 || String(row[0]) === targetId) return false;
          if (row[10] !== "Transfer") return false;
          const sameDate = row[2] === targetDate;
          const oppositeAccounts =
            row[7] === targetAccountTo && row[8] === targetAccount;
          const otherComment = String(row[12] || "").trim();
          const commentMatch = targetComment
            ? otherComment === targetComment
            : otherComment === "";
          return sameDate && oppositeAccounts && commentMatch;
        });
      }

      if (pairRowIndex > 0) toDelete.push(pairRowIndex + 1);
    }

    toDelete.sort((a, b) => b - a);
    for (const sheetRow of toDelete) {
      await deleteRow("moneyflow", sheetRow);
    }

    res.json({ success: true, deleted: toDelete.length });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to delete transaction" });
  }
});

module.exports = router;
