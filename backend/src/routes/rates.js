const express = require("express");
const { getSheet, updateRange } = require("../services/sheets");
const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const data = await getSheet("rates");
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch rates" });
  }
});

router.post("/update", async (req, res) => {
  try {
    const currencies = await getSheet("rates");
    if (!currencies.length)
      return res.status(400).json({ error: "No currencies in rates sheet" });

    const now = new Date().toLocaleDateString("en-US");
    const updated = [];

    for (let i = 0; i < currencies.length; i++) {
      const { currency } = currencies[i];
      if (!currency) continue;

      if (currency === "RUB") {
        await updateRange(`rates!B${i + 2}:C${i + 2}`, [[1, now]]);
        updated.push({ currency: "RUB", rate: 1 });
        continue;
      }

      const apiRes = await fetch(
        `https://open.er-api.com/v6/latest/${currency}`,
      );
      if (!apiRes.ok) throw new Error(`API error for ${currency}`);
      const data = await apiRes.json();
      const rate = data.rates?.RUB;
      if (!rate) throw new Error(`No RUB rate for ${currency}`);

      await updateRange(`rates!B${i + 2}:C${i + 2}`, [[rate, now]]);
      updated.push({ currency, rate });
    }

    res.json({ success: true, updated });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to update rates: " + err.message });
  }
});

module.exports = router;
