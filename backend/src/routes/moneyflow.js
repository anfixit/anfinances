const express = require("express");
const {
  getSheet,
  getRawRows,
  appendRow,
  updateRange,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

// Колонки moneyflow в порядке шита:
// id, date, type, required, amount, amount RUB, account, account_to, currency, category, subcategory, comment
const COLUMNS = [
  "id",
  "date",
  "type",
  "required",
  "amount",
  "amount RUB",
  "account",
  "account_to",
  "currency",
  "category",
  "subcategory",
  "comment",
];

// GET /api/moneyflow — все транзакции (id теперь включён автоматически через getSheet)
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

    // Находим max id из существующих строк (строка 0 — заголовки)
    let maxId = 0;
    rows.slice(1).forEach((row) => {
      const id = parseInt(row[0]);
      if (!isNaN(id) && id > maxId) maxId = id;
    });
    const newId = maxId + 1;

    await appendRow("moneyflow", { ...req.body, id: newId });
    res.json({ success: true, id: newId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transaction" });
  }
});

// PUT /api/moneyflow/:id — обновить транзакцию по id
router.put("/:id", async (req, res) => {
  try {
    const targetId = parseInt(req.params.id);
    const rows = await getRawRows("moneyflow");

    // Ищем строку с нужным id (строка 0 — заголовки, поэтому шитовая строка = i+1)
    const rowIndex = rows.findIndex(
      (row, i) => i > 0 && parseInt(row[0]) === targetId,
    );
    if (rowIndex < 1)
      return res.status(404).json({ error: "Transaction not found" });

    const sheetRow = rowIndex + 1; // 1-based для Sheets API
    const body = req.body;

    // Формируем строку в порядке колонок, id не меняем
    const values = [
      [
        targetId,
        body.date ?? rows[rowIndex][1],
        body.type ?? rows[rowIndex][2],
        body.required ?? rows[rowIndex][3],
        body.amount ?? rows[rowIndex][4],
        body["amount RUB"] ?? rows[rowIndex][5],
        body.account ?? rows[rowIndex][6],
        body.account_to ?? rows[rowIndex][7],
        body.currency ?? rows[rowIndex][8],
        body.category ?? rows[rowIndex][9],
        body.subcategory ?? rows[rowIndex][10],
        body.comment ?? rows[rowIndex][11],
      ],
    ];

    await updateRange(`moneyflow!A${sheetRow}:L${sheetRow}`, values);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to update transaction" });
  }
});

// DELETE /api/moneyflow/:id — физически удалить строку по id
// Если передан ?pair=true — удалить обе строки пары (по pair_id или совпадению account_to)
router.delete("/:id", async (req, res) => {
  try {
    const targetId = parseInt(req.params.id);
    const deletePair = req.query.pair === "true";
    const rows = await getRawRows("moneyflow");

    if (deletePair) {
      // Находим строку и её pair (ищем по совпадению даты + комментария + Transfer)
      const targetRowIndex = rows.findIndex(
        (row, i) => i > 0 && parseInt(row[0]) === targetId,
      );
      if (targetRowIndex < 1)
        return res.status(404).json({ error: "Transaction not found" });

      const targetRow = rows[targetRowIndex];
      const targetDate = targetRow[1];
      const targetComment = targetRow[11];
      const targetAccount = targetRow[6];
      const targetAccountTo = targetRow[7];

      // Ищем парную строку: та же дата, тот же комментарий, противоположное направление
      const pairRowIndex = rows.findIndex((row, i) => {
        if (i === 0 || parseInt(row[0]) === targetId) return false;
        return (
          row[1] === targetDate &&
          row[11] === targetComment &&
          row[6] === targetAccountTo &&
          row[7] === targetAccount
        );
      });

      // Удаляем с конца чтобы индексы не съехали
      const toDelete = [targetRowIndex + 1]; // sheetRow (1-based)
      if (pairRowIndex > 0) toDelete.push(pairRowIndex + 1);
      toDelete.sort((a, b) => b - a); // сортируем по убыванию

      for (const sheetRow of toDelete) {
        await deleteRow("moneyflow", sheetRow);
      }

      res.json({ success: true, deleted: toDelete.length });
    } else {
      // Удаляем только одну строку
      const rowIndex = rows.findIndex(
        (row, i) => i > 0 && parseInt(row[0]) === targetId,
      );
      if (rowIndex < 1)
        return res.status(404).json({ error: "Transaction not found" });

      await deleteRow("moneyflow", rowIndex + 1);
      res.json({ success: true, deleted: 1 });
    }
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to delete transaction" });
  }
});

module.exports = router;
