const express = require("express");
const { getSheet } = require("../services/sheets");
const router = express.Router();

function parseAmount(str) {
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

    const ratesMap = {};
    rates.forEach((r) => {
      if (r.currency && r.rate) ratesMap[r.currency] = parseFloat(r.rate);
    });

    // Начальные балансы в родной валюте
    const balanceNative = {};
    accounts.forEach((acc) => {
      balanceNative[acc.account] = parseAmount(acc.initial_balance);
    });

    // Каждая строка moneyflow — либо income либо expense
    // Переводы записаны как ПАРА строк:
    //   expense на счёте-источнике
    //   income  на счёте-получателе
    // Поэтому просто считаем: income += amt, expense -= amt для каждого account
    moneyflow.forEach((t) => {
      const acc = t.account;
      const type = (t.type || "").toLowerCase();
      // Используем amount RUB для всех расчётов в рублях
      const amt = parseFloat(t["amount RUB"] || 0);

      if (!acc || isNaN(amt) || !balanceNative.hasOwnProperty(acc)) return;

      if (type === "income") {
        balanceNative[acc] += amt;
      } else if (type === "expense") {
        balanceNative[acc] -= amt;
      }
    });

    // Переводим в рубли (для не-рублёвых счетов начальный баланс в родной валюте)
    // Но поскольку мы уже считаем в amount RUB, нужно скорректировать initial_balance
    // initial_balance хранится в родной валюте — переводим его отдельно
    const accountBalancesRub = {};
    accounts.forEach((acc) => {
      const rate = ratesMap[acc.currency] || 1;
      const initialNative = parseAmount(acc.initial_balance);
      const initialRub = initialNative * rate;
      // balanceNative уже включает initial + все транзакции в рублях
      // но initial был добавлен как native, надо пересчитать
      const txBalance = balanceNative[acc.account] - initialNative; // только транзакции
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

    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    let monthlyIncome = 0;
    let monthlyExpenses = 0;

    moneyflow.forEach((t) => {
      if ((t.category || "") === "Transfer") return;
      const amt = parseFloat(t["amount RUB"] || 0);
      if (isNaN(amt)) return;
      const datePart = String(t.date || "").split(" ")[0];
      const parts = datePart.split("/");
      if (parts.length !== 3) return;
      const txDate = new Date(
        parseInt(parts[2]),
        parseInt(parts[0]) - 1,
        parseInt(parts[1]),
      );
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
