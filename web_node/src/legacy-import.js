const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const Database = require('better-sqlite3');
const multer = require('multer');

const DEFAULT_SETUP_TOKEN_HASH = 'abea5dc9aceaeb970a31dc2d2ec4d7a75a49b7b8ab2dc156b09d3440a13dbaa5';
const REQUIRED_TABLES = [
  'users', 'app_settings', 'customers', 'employees', 'invoices',
  'invoice_payments', 'reminders', 'time_entries', 'certificates',
  'applications', 'application_files', 'salary_certificates',
];

function sha256(value) {
  return crypto.createHash('sha256').update(String(value)).digest();
}

function tokenMatches(value, expectedHex) {
  if (!value || !/^[a-f0-9]{64}$/i.test(String(expectedHex || ''))) return false;
  const supplied = sha256(value);
  const expected = Buffer.from(expectedHex, 'hex');
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}

function validateDatabase(filePath) {
  const candidate = new Database(filePath, { readonly: true, fileMustExist: true });
  try {
    const integrity = candidate.pragma('integrity_check', { simple: true });
    if (integrity !== 'ok') throw new Error('Die Sicherungsdatei ist beschädigt.');
    const tables = new Set(candidate.prepare(
      "SELECT name FROM sqlite_master WHERE type='table'"
    ).all().map(row => row.name));
    const missing = REQUIRED_TABLES.filter(table => !tables.has(table));
    if (missing.length) throw new Error(`In der Sicherung fehlen Tabellen: ${missing.join(', ')}`);
    const users = candidate.prepare('SELECT COUNT(*) AS count FROM users').get().count;
    if (users < 1) throw new Error('Die Sicherung enthält keine Benutzerkonten.');
    return Object.fromEntries(REQUIRED_TABLES.map(table => [
      table,
      candidate.prepare(`SELECT COUNT(*) AS count FROM "${table}"`).get().count,
    ]));
  } finally {
    candidate.close();
  }
}

function registerLegacyImport(app, db, dbPath, options = {}) {
  const tokenHash = process.env.AST_SETUP_TOKEN_HASH || DEFAULT_SETUP_TOKEN_HASH;
  const importDir = path.join(path.dirname(dbPath), 'imports');
  fs.mkdirSync(importDir, { recursive: true });
  const upload = multer({ dest: importDir, limits: { files: 1, fileSize: 25 * 1024 * 1024 } });

  app.post('/internal/setup/import', (req, res, next) => {
    const hasUsers = db.prepare('SELECT COUNT(*) AS count FROM users').get().count > 0;
    if (hasUsers || !tokenMatches(req.get('x-ast-setup-token'), tokenHash)) return res.sendStatus(404);
    next();
  }, upload.single('database'), (req, res, next) => {
    if (!req.file) return res.status(400).json({ ok: false, error: 'Keine Datenbankdatei empfangen.' });
    try {
      const counts = validateDatabase(req.file.path);
      db.pragma('wal_checkpoint(TRUNCATE)');
      db.close();
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const backup = `${dbPath}.before-import-${stamp}`;
      if (fs.existsSync(dbPath)) fs.renameSync(dbPath, backup);
      for (const suffix of ['-wal', '-shm']) fs.rmSync(`${dbPath}${suffix}`, { force: true });
      fs.renameSync(req.file.path, dbPath);
      res.status(202).json({ ok: true, imported: counts, restarting: true });
      const restart = options.restart || (() => process.exit(0));
      setTimeout(restart, 750).unref();
    } catch (error) {
      fs.rmSync(req.file.path, { force: true });
      next(error);
    }
  });
}

module.exports = { registerLegacyImport, tokenMatches, validateDatabase };
