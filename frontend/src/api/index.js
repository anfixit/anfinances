import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export const getAccounts = () => api.get("/accounts").then((r) => r.data);
export const getMoneyflow = () => api.get("/moneyflow").then((r) => r.data);
export const getRecurring = () => api.get("/recurring").then((r) => r.data);
export const getRates = () => api.get("/rates").then((r) => r.data);
export const getSummary = () => api.get("/summary").then((r) => r.data);
export const getReference = () => api.get("/reference").then((r) => r.data);
export const updateRates = () => api.post("/rates/update").then((r) => r.data);
export const addAccount = (data) =>
  api.post("/accounts", data).then((r) => r.data);

// Транзакции
export const addTransaction = (data) =>
  api.post("/moneyflow", data).then((r) => r.data);
export const addTransfer = (data) =>
  api.post("/moneyflow/transfer", data).then((r) => r.data);
export const updateTransaction = (id, data) =>
  api.put(`/moneyflow/${id}`, data).then((r) => r.data);
export const deleteTransaction = (id, pair = false) =>
  api.delete(`/moneyflow/${id}`, { params: { pair } }).then((r) => r.data);

// Бюджет
export const getBudget = (month) =>
  api.get("/budget", { params: { month } }).then((r) => r.data);
export const saveBudgetItem = (data) =>
  api.post("/budget", data).then((r) => r.data);
export const deleteBudgetItem = (data) =>
  api.delete("/budget", { data }).then((r) => r.data);

// План минимума
export const savePlanMinItem = (data) =>
  api.post("/recurring", data).then((r) => r.data);
export const deletePlanMinItem = (data) =>
  api.delete("/recurring", { data }).then((r) => r.data);
