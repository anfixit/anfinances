const express = require("express");
const { getSheet } = require("../services/sheets");
const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const data = await getSheet("plan_min");
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch recurring" });
  }
});

module.exports = router;
