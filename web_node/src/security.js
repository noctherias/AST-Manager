const crypto = require('node:crypto');
const bcrypt = require('bcryptjs');

const COOKIE = 'ast_manager_session';
const now = () => new Date().toISOString();
const token = () => crypto.randomBytes(32).toString('hex');
const hash = value => crypto.createHash('sha256').update(String(value)).digest('hex');

function verifyPassword(password, stored) {
  const compatible = String(stored || '').replace(/^\$2y\$/, '$2b$');
  return bcrypt.compareSync(password, compatible);
}

function cookieMap(header = '') {
  return Object.fromEntries(header.split(';').map(item => item.trim().split(/=(.*)/s).slice(0, 2)).filter(x => x[0]));
}

function createSecurity(db) {
  db.exec(`CREATE TABLE IF NOT EXISTS node_sessions(
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL,
    expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
  );`);
  const clean = db.prepare('DELETE FROM node_sessions WHERE expires_at<?');
  const find = db.prepare('SELECT s.csrf,u.* FROM node_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1');
  const insert = db.prepare('INSERT INTO node_sessions(token_hash,user_id,csrf,expires_at,created_at) VALUES(?,?,?,?,?)');
  const remove = db.prepare('DELETE FROM node_sessions WHERE token_hash=?');
  return {
    current(req) {
      clean.run(now());
      const raw = cookieMap(req.headers.cookie)[COOKIE];
      return raw ? find.get(hash(raw), now()) : null;
    },
    login(res, userId) {
      const raw = token(); const csrf = token();
      const expires = new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString();
      insert.run(hash(raw), userId, csrf, expires, now());
      res.cookie(COOKIE, raw, {httpOnly: true, secure: true, sameSite: 'strict', maxAge: 12 * 60 * 60 * 1000, path: '/'});
      return csrf;
    },
    logout(req, res) {
      const raw = cookieMap(req.headers.cookie)[COOKIE]; if (raw) remove.run(hash(raw));
      res.clearCookie(COOKIE, {path: '/'});
    },
    verifyCsrf(req, user) { const supplied=Buffer.from(String(req.body?.csrf||'')); const expected=Buffer.from(String(user?.csrf||'')); return Boolean(user && supplied.length===expected.length && crypto.timingSafeEqual(supplied,expected)); },
  };
}

module.exports = {createSecurity, verifyPassword};
