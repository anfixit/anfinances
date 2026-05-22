require("dotenv").config();
const express = require("express");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

app.use("/api/accounts", require("./routes/accounts"));
app.use("/api/moneyflow", require("./routes/moneyflow"));
app.use("/api/recurring", require("./routes/recurring"));
app.use("/api/rates", require("./routes/rates"));
app.use("/api/summary", require("./routes/summary"));
app.use("/api/reference", require("./routes/reference"));
app.use("/api/budget", require("./routes/budget"));

app.get("/api/health", (req, res) => res.json({ status: "ok" }));

app.listen(PORT, () =>
  console.log(`Backend running on http://localhost:${PORT}`),
);
