const { google } = require("googleapis");
const path = require("path");

const SPREADSHEET_ID = process.env.SPREADSHEET_ID;

function getAuth() {
  const credentialsPath = path.resolve(
    process.cwd(),
    process.env.GOOGLE_CREDENTIALS_PATH || "./credentials.json",
  );

  const auth = new google.auth.GoogleAuth({
    keyFile: credentialsPath,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });

  return auth;
}

async function getSheet(sheetName) {
  const auth = getAuth();
  const sheets = google.sheets({ version: "v4", auth });

  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: sheetName,
  });

  const rows = response.data.values || [];
  if (rows.length === 0) return [];

  const headers = rows[0];
  return rows.slice(1).map((row) => {
    const obj = {};
    headers.forEach((header, i) => {
      obj[header] = row[i] ?? "";
    });
    return obj;
  });
}

async function appendRow(sheetName, rowData) {
  const auth = getAuth();
  const sheets = google.sheets({ version: "v4", auth });

  // Сначала получим заголовки чтобы знать порядок колонок
  const headerResponse = await sheets.spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: `${sheetName}!1:1`,
  });

  const headers = headerResponse.data.values?.[0] || [];
  const row = headers.map((header) => rowData[header] ?? "");

  await sheets.spreadsheets.values.append({
    spreadsheetId: SPREADSHEET_ID,
    range: sheetName,
    valueInputOption: "USER_ENTERED",
    requestBody: { values: [row] },
  });
}

module.exports = { getSheet, appendRow };
