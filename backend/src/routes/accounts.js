const express = require("express");
const { getSheet, appendRow } = require("../services/sheets");
const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const data = await getSheet("accounts");
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch accounts" });
  }
});

router.post("/", async (req, res) => {
  try {
    await appendRow("accounts", req.body);
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to add account" });
  }
});

module.exports = router;
