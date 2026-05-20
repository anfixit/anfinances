const express = require('express');
const { google } = require('googleapis');
const path = require('path');
const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const auth = new google.auth.GoogleAuth({
      keyFile: path.resolve(process.cwd(), process.env.GOOGLE_CREDENTIALS_PATH || './credentials.json'),
      scopes: ['https://www.googleapis.com/auth/spreadsheets'],
    });
    const sheets = google.sheets({ version: 'v4', auth });
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: process.env.SPREADSHEET_ID,
      range: 'reference',
    });

    const rows = response.data.values || [];
    const result = {};

    // Пропускаем первую строку (заголовок "Категория")
    rows.slice(1).forEach(row => {
      const category = row[0];
      if (!category) return;
      const subcategories = row.slice(1).filter(v => v && v.trim() !== '');
      result[category] = subcategories;
    });

    res.json(result);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch reference' });
  }
});

module.exports = router;
