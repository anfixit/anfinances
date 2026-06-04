const express = require("express");
const { getSheet } = require("../services/sheets");
const router = express.Router();

function parseAmount(str) {
  if (!str) return 0;
  const num = parseFloat(String(str).replace(/[^0-9.-]/g, ""));
  return isNaN(num) ? 0 : num;
}

// Парсит дату из формата "5/22/2026 10:54:14" → Date
function parseSheetDate(str) {
  if (!str) return null;
  const datePart = String(str).split(" ")[0];
  const timePart = String(str).split(" ")[1] || "12:00:00";
  const parts = datePart.split("/");
  if (parts.length !== 3) return null;
  const [m, d, y] = parts.map(Number);
  const [hh = 12, mm = 0, ss = 0] = timePart.split(":").map(Number);
  return new Date(y, m - 1, d, hh, mm, ss);
}

router.get("/", async (req, res) => {
  try {
    const [accounts, moneyflow, recurring, rates] = await Promise.all([
      getSheet("accounts"),
      getSheet("moneyflow"),
      getSheet("plan_min"),
      getSheet("rates"),
    ]);

    const ratesMap = {};
    rates.forEach((r) => {
      if (r.currency && r.rate) ratesMap[r.currency] = parseFloat(r.rate);
    });

    // Начальные балансы в родной валюте
    const balanceNative = {};
    accounts.forEach((acc) => {
      balanceNative[acc.account] = parseAmount(acc.initial_balance);
    });

    // Транзакции изменяют баланс. amount RUB используется для всех расчётов в рублях.
    const unknownAccounts = new Set();
    moneyflow.forEach((t) => {
      const acc = t.account;
      const type = (t.type || "").toLowerCase();
      const amt = parseFloat(t["amount RUB"] || 0);

      if (!acc || isNaN(amt)) return;
      if (!balanceNative.hasOwnProperty(acc)) {
        unknownAccounts.add(acc);
        return;
      }

      if (type === "income") {
        balanceNative[acc] += amt;
      } else if (type === "expense") {
        balanceNative[acc] -= amt;
      }
    });

    if (unknownAccounts.size > 0) {
      console.warn(
        "Unknown accounts in moneyflow (transactions ignored):",
        Array.from(unknownAccounts).join(", "),
      );
    }

    // Пересчёт в рубли с учётом валюты счёта
    const accountBalancesRub = {};
    accounts.forEach((acc) => {
      const rate = ratesMap[acc.currency] || 1;
      const initialNative = parseAmount(acc.initial_balance);
      const initialRub = initialNative * rate;
      const txBalance = balanceNative[acc.account] - initialNative;
      accountBalancesRub[acc.account] = initialRub + txBalance;
    });

    const totalBalance = Object.values(accountBalancesRub).reduce(
      (s, v) => s + v,
      0,
    );

    const monthlyObligatory = recurring
      .filter((r) => r.required === "required")
      .reduce((s, r) => s + parseAmount(r.amount_rub), 0);
    const monthlyTotal = recurring.reduce(
      (s, r) => s + parseAmount(r.amount_rub),
      0,
    );

    const runway =
      monthlyObligatory > 0
        ? Math.floor(totalBalance / monthlyObligatory)
        : null;

    // Доходы/расходы текущего месяца (границы включительно, по конец дня)
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0);
    const monthEnd = new Date(
      now.getFullYear(),
      now.getMonth() + 1,
      0,
      23,
      59,
      59,
    );

    let monthlyIncome = 0;
    let monthlyExpenses = 0;

    moneyflow.forEach((t) => {
      if ((t.category || "") === "Transfer") return;
      const amt = parseFloat(t["amount RUB"] || 0);
      if (isNaN(amt)) return;

      const txDate = parseSheetDate(t.date);
      if (!txDate) return;

      if (txDate >= monthStart && txDate <= monthEnd) {
        if (t.type === "income") monthlyIncome += amt;
        else if (t.type === "expense") monthlyExpenses += amt;
      }
    });

    res.json({
      totalBalance: Math.round(totalBalance),
      monthlyObligatory: Math.round(monthlyObligatory),
      monthlyTotal: Math.round(monthlyTotal),
      monthlyIncome: Math.round(monthlyIncome),
      monthlyExpenses: Math.round(monthlyExpenses),
      runway,
      accountsCount: accounts.length,
      transactionsCount: moneyflow.length,
      ratesMap,
      accountBalancesRub,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch summary" });
  }
});

module.exports = router;
