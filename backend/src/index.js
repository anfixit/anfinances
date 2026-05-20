require("dotenv").config();
const express = require("express");
const cors = require("cors");

const accountsRouter = require("./routes/accounts");
const moneyflowRouter = require("./routes/moneyflow");
const recurringRouter = require("./routes/recurring");
const ratesRouter = require("./routes/rates");
const summaryRouter = require("./routes/summary");
const referenceRouter = require("./routes/reference");

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

app.use("/api/accounts", accountsRouter);
app.use("/api/moneyflow", moneyflowRouter);
app.use("/api/recurring", recurringRouter);
app.use("/api/rates", ratesRouter);
app.use("/api/summary", summaryRouter);
app.use("/api/reference", referenceRouter);

app.get("/api/health", (req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
