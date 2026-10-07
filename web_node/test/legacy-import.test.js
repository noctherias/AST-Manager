const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const Database = require('better-sqlite3');
const { tokenMatches, validateDatabase } = require('../src/legacy-import');

test('setup token is compared by SHA-256 hash', () => {
  const hash = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b';
  assert.equal(tokenMatches('secret', hash), true);
  assert.equal(tokenMatches('wrong', hash), false);
  assert.equal(tokenMatches('', hash), false);
});

test('legacy database validation accepts a complete AST backup', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ast-import-test-'));
  const file = path.join(dir, 'backup.sqlite3');
  const db = new Database(file);
  for (const table of [
    'app_settings', 'customers', 'employees', 'invoices', 'invoice_payments',
    'reminders', 'time_entries', 'certificates', 'applications',
    'application_files', 'salary_certificates',
  ]) db.exec(`CREATE TABLE "${table}" (id INTEGER PRIMARY KEY)`);
  db.exec('CREATE TABLE users (id INTEGER PRIMARY KEY); INSERT INTO users VALUES (1)');
  db.close();
  const counts = validateDatabase(file);
  assert.equal(counts.users, 1);
  assert.equal(counts.employees, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('legacy database validation rejects a backup without users', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ast-import-test-'));
  const file = path.join(dir, 'backup.sqlite3');
  const db = new Database(file);
  db.exec('CREATE TABLE users (id INTEGER PRIMARY KEY)');
  db.close();
  assert.throws(() => validateDatabase(file), /fehlen Tabellen/);
  fs.rmSync(dir, { recursive: true, force: true });
});
