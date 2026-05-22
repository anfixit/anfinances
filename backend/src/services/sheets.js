const { google } = require("googleapis");
const path = require("path");

function getClient() {
  const auth = new google.auth.GoogleAuth({
    keyFile: path.resolve(
      process.cwd(),
      process.env.GOOGLE_CREDENTIALS_PATH || "./credentials.json",
    ),
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
  return google.sheets({ version: "v4", auth });
}

const ID = () => process.env.SPREADSHEET_ID;

// Читает лист → массив объектов
async function getSheet(sheetName) {
  const sheets = getClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ID(),
    range: sheetName,
  });
  const rows = res.data.values || [];
  if (rows.length === 0) return [];
  const headers = rows[0];
  return rows.slice(1).map((row) => {
    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = row[i] ?? "";
    });
    return obj;
  });
}

// Читает лист → сырые строки (без маппинга заголовков)
async function getRawRows(sheetName) {
  const sheets = getClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ID(),
    range: sheetName,
  });
  return res.data.values || [];
}

// Добавляет строку в конец листа
async function appendRow(sheetName, rowData) {
  const sheets = getClient();
  const headerRes = await sheets.spreadsheets.values.get({
    spreadsheetId: ID(),
    range: `${sheetName}!1:1`,
  });
  const headers = headerRes.data.values?.[0] || [];
  const row = headers.map((h) => rowData[h] ?? "");
  await sheets.spreadsheets.values.append({
    spreadsheetId: ID(),
    range: sheetName,
    valueInputOption: "USER_ENTERED",
    requestBody: { values: [row] },
  });
}

// Обновляет конкретную ячейку/диапазон
async function updateRange(range, values) {
  const sheets = getClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ID(),
    range,
    valueInputOption: "USER_ENTERED",
    requestBody: { values },
  });
}

// Очищает диапазон
async function clearRange(range) {
  const sheets = getClient();
  await sheets.spreadsheets.values.clear({
    spreadsheetId: ID(),
    range,
  });
}

module.exports = { getSheet, getRawRows, appendRow, updateRange, clearRange };
