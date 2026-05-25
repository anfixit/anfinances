// Константы — только UI-конфиг, который НЕ хранится в Google Sheets.
// Категории, валюты, счета — берём через getReference(), getRates(), getAccounts().

export const CATEGORY_ICONS = {
  Food: "restaurant",
  Healthcare: "favorite",
  Transport: "directions_car",
  Home: "home",
  Software: "devices",
  Auto: "directions_car",
  Entertainment: "celebration",
  Communication: "phone",
  Hardware: "memory",
  Beauty: "spa",
  Pets: "pets",
  Self_Development: "school",
  Gifts_Charity: "card_giftcard",
  Taxes: "receipt",
  Bank: "account_balance",
  Clothing_Shoes: "checkroom",
  Travel: "flight",
  Public_Services: "account_balance",
  Income: "payments",
  Transfer: "sync_alt",
  default: "attach_money",
};

export function getCategoryIcon(category) {
  return CATEGORY_ICONS[category] || CATEGORY_ICONS.default;
}

export const ACCOUNT_TYPES = ["Card", "Cash", "Card, Credit"];

export const ACCOUNT_TYPE_LABELS = {
  Card: "Карта",
  Cash: "Наличные",
  "Card, Credit": "Кредитная",
};

export const ACCOUNT_TYPE_ICONS = {
  Card: "account_balance_wallet",
  Cash: "payments",
  "Card, Credit": "credit_card",
};

export const PAGE_SIZE = 20;

// ─────────────────────────────────────────────────────────────────────────────
// Утилиты форматирования
// ─────────────────────────────────────────────────────────────────────────────

// Формат даты для шита: M/D/YYYY HH:MM:SS (не зависит от локали сервера/браузера)
export function formatDateForSheet(date) {
  const d = new Date(date);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const y = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${m}/${day}/${y} ${hh}:${mm}:${ss}`;
}

// Из "YYYY-MM-DD" (input type=date) → "M/D/YYYY HH:MM:SS"
export function dateInputToSheet(dateInput, time = "12:00:00") {
  const [y, m, d] = dateInput.split("-").map(Number);
  return `${m}/${d}/${y} ${time}`;
}

// Из "M/D/YYYY HH:MM:SS" → "YYYY-MM-DD" (для input type=date)
export function sheetDateToInput(dateStr) {
  if (!dateStr) return new Date().toISOString().split("T")[0];
  const parts = String(dateStr).split(" ")[0].split("/");
  if (parts.length === 3) {
    return `${parts[2]}-${String(parts[0]).padStart(2, "0")}-${String(parts[1]).padStart(2, "0")}`;
  }
  return dateStr;
}

// Текущая дата в формате "YYYY-MM-DD" (для сравнений и input type=date)
export function todayISO() {
  return new Date().toISOString().split("T")[0];
}

// Форматирование рублей
export function fmtRub(n, fractionDigits = 0) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: fractionDigits,
  }).format(n);
}

// Парсит "RUB 1,000.00" → 1000
export function parseAmount(str) {
  if (!str) return 0;
  const num = parseFloat(String(str).replace(/[^0-9.-]/g, ""));
  return isNaN(num) ? 0 : num;
}

// Парсит "RUB 1,000.00" → "1000" (строкой, для input)
export function parseAmountString(str) {
  if (!str) return "";
  return String(str).replace(/[^0-9.-]/g, "");
}
