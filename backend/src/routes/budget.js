const express = require('express');
const { google } = require('googleapis');
const path = require('path');
const router = express.Router();

function getSheets() {
  const auth = new google.auth.GoogleAuth({
    keyFile: path.resolve(process.cwd(), process.env.GOOGLE_CREDENTIALS_PATH || './credentials.json'),
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
  });
  return google.sheets({ version: 'v4', auth });
}

const SPREADSHEET_ID = process.env.SPREADSHEET_ID;

// GET /api/budget?month=2026-05
router.get('/', async (req, res) => {
  try {
    const sheets = getSheets();
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: SPREADSHEET_ID,
      range: 'budget',
    });
    const rows = response.data.values || [];
    if (rows.length < 2) return res.json([]);
    const headers = rows[0];
    const data = rows.slice(1).map(row => {
      const obj = {};
      headers.forEach((h, i) => { obj[h] = row[i] ?? ''; });
      return obj;
    }).filter(r => r.month);
    // Фильтр по месяцу если передан
    const { month } = req.query;
    const result = month ? data.filter(r => r.month === month) : data;
    res.json(result);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch budget' });
  }
});

// POST /api/budget — добавить или обновить строку
router.post('/', async (req, res) => {
  try {
    const { month, category, planned, notes, rollover } = req.body;
    if (!month || !category) return res.status(400).json({ error: 'month and category required' });

    const sheets = getSheets();

    // Найдём существующую строку
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: SPREADSHEET_ID,
      range: 'budget',
    });
    const rows = response.data.values || [];
    const rowIndex = rows.findIndex((r, i) => i > 0 && r[0] === month && r[1] === category);

    if (rowIndex > 0) {
      // Обновить существующую
      await sheets.spreadsheets.values.update({
        spreadsheetId: SPREADSHEET_ID,
        range: `budget!A${rowIndex + 1}:E${rowIndex + 1}`,
        valueInputOption: 'USER_ENTERED',
        requestBody: { values: [[month, category, planned, notes || '', rollover || 'false']] },
      });
    } else {
      // Добавить новую
      await sheets.spreadsheets.values.append({
        spreadsheetId: SPREADSHEET_ID,
        range: 'budget',
        valueInputOption: 'USER_ENTERED',
        requestBody: { values: [[month, category, planned, notes || '', rollover || 'false']] },
      });
    }
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to save budget' });
  }
});

// DELETE /api/budget — удалить строку
router.delete('/', async (req, res) => {
  try {
    const { month, category } = req.body;
    const sheets = getSheets();
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: SPREADSHEET_ID,
      range: 'budget',
    });
    const rows = response.data.values || [];
    const rowIndex = rows.findIndex((r, i) => i > 0 && r[0] === month && r[1] === category);
    if (rowIndex < 1) return res.status(404).json({ error: 'Not found' });

    // Очищаем строку
    await sheets.spreadsheets.values.clear({
      spreadsheetId: SPREADSHEET_ID,
      range: `budget!A${rowIndex + 1}:E${rowIndex + 1}`,
    });
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to delete budget row' });
  }
});

module.exports = router;
