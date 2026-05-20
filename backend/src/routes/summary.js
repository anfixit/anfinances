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

    // Общий баланс по всем счетам
    const totalBalance = accounts.reduce((sum, acc) => {
      return sum + parseRub(acc["balance in RUB"]);
    }, 0);

    // Курсы валют
    const ratesMap = {};
    rates.forEach((r) => {
      if (r.currency && r.rate) {
        ratesMap[r.currency] = parseFloat(r.rate);
      }
    });

    // Обязательные расходы в месяц
    const monthlyObligatory = recurring
      .filter((r) => r.required === "required")
      .reduce((sum, r) => sum + parseRub(r.amount_rub), 0);

    // Все расходы включая опциональные
    const monthlyTotal = recurring.reduce(
      (sum, r) => sum + parseRub(r.amount_rub),
      0,
    );

    // Runway
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
