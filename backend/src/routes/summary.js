const express = require("express");
const { getSheet } = require("../services/sheets");
const router = express.Router();

function parseRub(str) {
  if (!str) return 0;
  const num = parseFloat(String(str).replace(/[^0-9.-]/g, ""));
  return isNaN(num) ? 0 : num;
}

router.get("/", async (req, res) => {
  try {
    const [accounts, moneyflow, recurring, rates] = await Promise.all([
      getSheet("accounts"),
      getSheet("moneyflow"),
      getSheet("plan_min"),
      getSheet("rates"),
    ]);

    const totalBalance = accounts.reduce(
      (s, a) => s + parseRub(a["balance in RUB"]),
      0,
    );

    const ratesMap = {};
    rates.forEach((r) => {
      if (r.currency && r.rate) ratesMap[r.currency] = parseFloat(r.rate);
    });

    const monthlyObligatory = recurring
      .filter((r) => r.required === "required")
      .reduce((s, r) => s + parseRub(r.amount_rub), 0);

    const monthlyTotal = recurring.reduce(
      (s, r) => s + parseRub(r.amount_rub),
      0,
    );

    const runway =
      monthlyObligatory > 0
        ? Math.floor(totalBalance / monthlyObligatory)
        : null;

    res.json({
      totalBalance: Math.round(totalBalance),
      monthlyObligatory: Math.round(monthlyObligatory),
      monthlyTotal: Math.round(monthlyTotal),
      runway,
      accountsCount: accounts.length,
      transactionsCount: moneyflow.length,
      ratesMap,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch summary" });
  }
});

module.exports = router;
