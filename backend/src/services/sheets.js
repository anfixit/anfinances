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

// Кэш sheetId по имени (числовой id нужен для batchUpdate)
const sheetIdCache = {};

async function getSheetId(sheetName) {
  if (sheetIdCache[sheetName] != null) return sheetIdCache[sheetName];
  const sheets = getClient();
  const res = await sheets.spreadsheets.get({ spreadsheetId: ID() });
  for (const s of res.data.sheets) {
    sheetIdCache[s.properties.title] = s.properties.sheetId;
  }
  if (sheetIdCache[sheetName] == null) {
    throw new Error(`Sheet "${sheetName}" not found`);
  }
  return sheetIdCache[sheetName];
}

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

// Обновляет конкретный диапазон
async function updateRange(range, values) {
  const sheets = getClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ID(),
    range,
    valueInputOption: "USER_ENTERED",
    requestBody: { values },
  });
}

// Очищает диапазон (оставляет пустую строку)
async function clearRange(range) {
  const sheets = getClient();
  await sheets.spreadsheets.values.clear({
    spreadsheetId: ID(),
    range,
  });
}

// Физически удаляет строку (0-based индекс в шите, включая заголовок)
// Например: строка 2 в шите (вторая строка данных) → sheetRowIndex = 2
async function deleteRow(sheetName, sheetRowIndex) {
  const sheets = getClient();
  const sheetId = await getSheetId(sheetName);
  await sheets.spreadsheets.batchUpdate({
    spreadsheetId: ID(),
    requestBody: {
      requests: [
        {
          deleteDimension: {
            range: {
              sheetId,
              dimension: "ROWS",
              startIndex: sheetRowIndex - 1, // API использует 0-based
              endIndex: sheetRowIndex, // exclusive
            },
          },
        },
      ],
    },
  });
}

module.exports = {
  getSheet,
  getRawRows,
  appendRow,
  updateRange,
  clearRange,
  deleteRow,
  getSheetId,
};
