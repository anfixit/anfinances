const express = require("express");
const {
  getSheet,
  getRawRows,
  appendRow,
  updateRange,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

// Колонки moneyflow: id, date, type, required, amount, amount RUB, account, account_to, currency, category, subcategory, comment

// Пересчёт amount RUB из суммы и валюты через текущие курсы
async function calcAmountRub(amount, currency, sheets_module) {
  if (!currency || currency === "RUB") return parseFloat(amount) || 0;
  try {
    const { getSheet: gs } = sheets_module;
    const rates = await gs("rates");
    const row = rates.find((r) => r.currency === currency);
    if (row && row.rate)
      return (parseFloat(amount) || 0) * parseFloat(row.rate);
  } catch (e) {}
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
    await appendRow("moneyflow", { ...req.body, id: newId });
    res.json({ success: true, id: newId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add transaction" });
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

    // Пересчитываем amount RUB если поменялась сумма или валюта
    const currency = body.currency ?? rows[rowIndex][8];
    const rawAmount = body.amount ?? rows[rowIndex][4];
    // Вытаскиваем чистое число из строки вида "RUB 48.00" или "48"
    const numericAmount =
      parseFloat(String(rawAmount).replace(/[^0-9.-]/g, "")) || 0;

    let amountRub;
    if (body["amount RUB"] !== undefined) {
      // Если фронт явно передал — используем
      amountRub = parseFloat(body["amount RUB"]) || 0;
    } else if (currency === "RUB") {
      amountRub = numericAmount;
    } else {
      // Пересчитываем через курс
      const sheetsModule = require("../services/sheets");
      amountRub = await calcAmountRub(numericAmount, currency, sheetsModule);
    }

    const values = [
      [
        targetId,
        body.date ?? rows[rowIndex][1],
        body.type ?? rows[rowIndex][2],
        body.required ?? rows[rowIndex][3],
        body.amount ?? rows[rowIndex][4],
        amountRub,
        body.account ?? rows[rowIndex][6],
        body.account_to ?? rows[rowIndex][7],
        currency,
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

// DELETE /api/moneyflow/:id — физически удалить
// ?pair=true — удалить обе строки перевода
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

    const toDelete = [targetRowIndex + 1]; // sheetRow (1-based)

    if (deletePair) {
      const targetRow = rows[targetRowIndex];
      const targetDate = targetRow[1];
      const targetComment = targetRow[11];
      const targetAccount = targetRow[6];
      const targetAccountTo = targetRow[7];

      // Парная строка: та же дата + комментарий + противоположные счета
      // Если комментарий пустой — ищем только по дате и счетам
      const pairRowIndex = rows.findIndex((row, i) => {
        if (i === 0 || parseInt(row[0]) === targetId) return false;
        const sameDate = row[1] === targetDate;
        const sameComment = targetComment
          ? row[11] === targetComment
          : row[11] === "" || row[11] === undefined;
        const oppositeAccounts =
          row[6] === targetAccountTo && row[7] === targetAccount;
        return sameDate && sameComment && oppositeAccounts;
      });

      if (pairRowIndex > 0) toDelete.push(pairRowIndex + 1);
    }

    // Удаляем с конца чтобы индексы не съехали
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
