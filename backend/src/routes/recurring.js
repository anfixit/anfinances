const express = require("express");
const {
  getSheet,
  getRawRows,
  updateRange,
  appendRow,
  deleteRow,
} = require("../services/sheets");
const router = express.Router();

// GET /api/recurring
router.get("/", async (req, res) => {
  try {
    const data = await getSheet("plan_min");
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch plan_min" });
  }
});

// POST /api/recurring — добавить или обновить строку
router.post("/", async (req, res) => {
  try {
    const {
      rowIndex,
      required,
      category,
      subcategory,
      monthly_amount,
      currency,
      amount_rub,
      comments,
    } = req.body;
    if (!category || !subcategory)
      return res
        .status(400)
        .json({ error: "category and subcategory required" });

    const values = [
      [
        required || "optional",
        category,
        subcategory,
        monthly_amount || "0",
        currency || "RUB",
        amount_rub || "0",
        comments || "",
      ],
    ];

    if (rowIndex) {
      const sheetRow = parseInt(rowIndex) + 1; // +1 для заголовка
      await updateRange(`plan_min!A${sheetRow}:G${sheetRow}`, values);
    } else {
      await appendRow("plan_min", {
        required: required || "optional",
        category,
        subcategory,
        monthly_amount: monthly_amount || "0",
        currency: currency || "RUB",
        amount_rub: amount_rub || "0",
        comments: comments || "",
      });
    }
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to save plan_min row" });
  }
});

// DELETE /api/recurring — физически удалить строку по rowIndex (1-based от данных)
router.delete("/", async (req, res) => {
  try {
    const { rowIndex } = req.body;
    if (!rowIndex) return res.status(400).json({ error: "rowIndex required" });
    // rowIndex 1-based от данных → sheetRow = rowIndex + 1 (строка 1 = заголовок)
    const sheetRow = parseInt(rowIndex) + 1;
    await deleteRow("plan_min", sheetRow);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to delete plan_min row" });
  }
});

module.exports = router;
