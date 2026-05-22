const express = require("express");
const { getRawRows } = require("../services/sheets");
const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const rows = await getRawRows("reference");
    const result = {};
    rows.slice(1).forEach((row) => {
      const category = row[0];
      if (!category) return;
      result[category] = row.slice(1).filter((v) => v && v.trim() !== "");
    });
    res.json(result);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch reference" });
  }
});

module.exports = router;
