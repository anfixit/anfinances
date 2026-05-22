const express = require("express");
const {
  getSheet,
  getRawRows,
  updateRange,
  clearRange,
} = require("../services/sheets");
const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const data = await getSheet("budget");
    const { month } = req.query;
    const result = month ? data.filter((r) => r.month === month) : data;
    res.json(result.filter((r) => r.month));
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
      const { appendRow } = require("../services/sheets");
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
    await clearRange(`budget!A${rowIndex + 1}:E${rowIndex + 1}`);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to delete budget row" });
  }
});

module.exports = router;
