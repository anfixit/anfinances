const express = require("express");
const {
  getSheet,
  getRawRows,
  appendRow,
  updateRange,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

// Колонки moneyflow: id, pair_id, date, type, required, amount, amount RUB, account, account_to, currency, category, subcategory, comment
// Индексы:           0   1        2     3     4         5       6           7        8           9         10        11           12

// Пересчёт amount RUB из суммы и валюты через текущие курсы
async function calcAmountRub(amount, currency) {
  if (!currency || currency === "RUB") return parseFloat(amount) || 0;
  try {
    const rates = await getSheet("rates");
    const row = rates.find((r) => r.currency === currency);
    if (row && row.rate)
      return (parseFloat(amount) || 0) * parseFloat(row.rate);
  } catch (e) {
    console.warn("calcAmountRub failed:", e.message);
  }
  return parseFloat(amount) || 0;
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

// POST /api/moneyflow — добавить транзакцию (генерируем max(id)+1)
router.post("/", async (req, res) => {
  try {
    const rows = await getRawRows("moneyflow");
    let maxId = 0;
    rows.slice(1).forEach((row) => {
      const id = parseInt(row[0]);
      if (!isNaN(id) && id > maxId) maxId = id;
    });
    const newId = maxId + 1;

    const payload = { ...req.body, id: newId };
    if (payload.pair_id === undefined) payload.pair_id = "";

    await appendRow("moneyflow", payload);
    res.json({ success: true, id: newId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transaction" });
  }
});

// POST /api/moneyflow/transfer — атомарно создать пару строк перевода/конвертации
// body: { expense: {...}, income: {...}, fee?: {...} }
// Обе строки получают одинаковый pair_id = id первой строки
router.post("/transfer", async (req, res) => {
  try {
    const { expense, income, fee } = req.body;
    if (!expense || !income) {
      return res.status(400).json({ error: "expense and income required" });
    }

    const rows = await getRawRows("moneyflow");
    let maxId = 0;
    rows.slice(1).forEach((row) => {
      const id = parseInt(row[0]);
      if (!isNaN(id) && id > maxId) maxId = id;
    });

    const firstId = maxId + 1;
    const secondId = maxId + 2;

    await appendRow("moneyflow", {
      ...expense,
      id: firstId,
      pair_id: firstId,
    });
    await appendRow("moneyflow", {
      ...income,
      id: secondId,
      pair_id: firstId,
    });

    // Опциональная комиссия — отдельная одиночная транзакция (без pair_id)
    if (fee) {
      await appendRow("moneyflow", {
        ...fee,
        id: maxId + 3,
        pair_id: "",
      });
    }

    res.json({ success: true, ids: [firstId, secondId], pair_id: firstId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transfer" });
  }
});

// PUT /api/moneyflow/:id — обновить транзакцию
router.put("/:id", async (req, res) => {
  try {
    const targetId = parseInt(req.params.id);
    const rows = await getRawRows("moneyflow");
    const rowIndex = rows.findIndex(
      (row, i) => i > 0 && parseInt(row[0]) === targetId,
    );
    if (rowIndex < 1)
      return res.status(404).json({ error: "Transaction not found" });

    const sheetRow = rowIndex + 1;
    const body = req.body;
    const existing = rows[rowIndex];

    // Пересчитываем amount RUB всегда (не доверяем фронту)
    const currency = body.currency ?? existing[9];
    const rawAmount = body.amount ?? existing[5];
    const numericAmount =
      parseFloat(String(rawAmount).replace(/[^0-9.-]/g, "")) || 0;
    const amountRub = await calcAmountRub(numericAmount, currency);

    const values = [
      [
        targetId, // id никогда не меняется
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
// ?pair=true — удалить обе строки пары (по pair_id, fallback на эвристику)
router.delete("/:id", async (req, res) => {
  try {
    const targetId = parseInt(req.params.id);
    const deletePair = req.query.pair === "true";
    const rows = await getRawRows("moneyflow");

    const targetRowIndex = rows.findIndex(
      (row, i) => i > 0 && parseInt(row[0]) === targetId,
    );
    if (targetRowIndex < 1)
      return res.status(404).json({ error: "Transaction not found" });

    const toDelete = [targetRowIndex + 1];

    if (deletePair) {
      const targetRow = rows[targetRowIndex];
      const targetPairId = targetRow[1];

      let pairRowIndex = -1;

      // 1. По pair_id (новые переводы)
      if (targetPairId && String(targetPairId).trim() !== "") {
        pairRowIndex = rows.findIndex((row, i) => {
          if (i === 0 || parseInt(row[0]) === targetId) return false;
          return String(row[1]) === String(targetPairId);
        });
      }

      // 2. Fallback: эвристика по date + accounts + comment
      if (pairRowIndex < 1) {
        const targetDate = targetRow[2];
        const targetAccount = targetRow[7];
        const targetAccountTo = targetRow[8];
        const targetComment = String(targetRow[12] || "").trim();

        pairRowIndex = rows.findIndex((row, i) => {
          if (i === 0 || parseInt(row[0]) === targetId) return false;
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
