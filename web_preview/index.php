<?php
declare(strict_types=1);

require __DIR__ . '/config.php';

header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: no-referrer');
header("Permissions-Policy: camera=(), microphone=(), geolocation=()");
header("Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");

session_name('AST_MANAGER_SESSION');
session_set_cookie_params([
    'lifetime' => 0,
    'path' => '/',
    'secure' => true,
    'httponly' => true,
    'samesite' => 'Strict',
]);
session_start();

$storage = __DIR__ . '/storage';
if (!is_dir($storage) && !mkdir($storage, 0770, true) && !is_dir($storage)) {
    http_response_code(500);
    exit('Der geschützte Datenspeicher konnte nicht erstellt werden.');
}

$db = new PDO('sqlite:' . $storage . '/ast-manager.sqlite3', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$db->exec('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');
$db->exec(<<<'SQL'
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','management','readonly')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_hash TEXT NOT NULL,
    email_hash TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    successful INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);
SQL);

function e(mixed $value): string { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function now(): string { return gmdate('Y-m-d\TH:i:s\Z'); }
function redirect(string $url): never { header('Location: ' . $url, true, 303); exit; }
function csrf(): string {
    if (empty($_SESSION['csrf'])) { $_SESSION['csrf'] = bin2hex(random_bytes(32)); }
    return $_SESSION['csrf'];
}
function require_csrf(): void {
    if (!isset($_POST['csrf']) || !hash_equals(csrf(), (string)$_POST['csrf'])) {
        http_response_code(400); exit('Die Sitzung ist abgelaufen. Bitte lade die Seite neu.');
    }
}
function set_flash(string $kind, string $message): void { $_SESSION['flash'] = [$kind, $message]; }
function take_flash(): ?array { $value = $_SESSION['flash'] ?? null; unset($_SESSION['flash']); return $value; }
function audit(PDO $db, ?int $userId, string $action, string $details = ''): void {
    $stmt = $db->prepare('INSERT INTO audit_log(user_id,action,details,created_at) VALUES(?,?,?,?)');
    $stmt->execute([$userId, $action, $details, now()]);
}
function current_user(PDO $db): ?array {
    if (empty($_SESSION['user_id'])) { return null; }
    $stmt = $db->prepare('SELECT * FROM users WHERE id=? AND active=1');
    $stmt->execute([(int)$_SESSION['user_id']]);
    return $stmt->fetch() ?: null;
}
function role_name(string $role): string {
    return ['admin'=>'Administrator', 'management'=>'Verwaltung', 'readonly'=>'Nur Lesen'][$role] ?? $role;
}
function initials(string $name): string {
    $parts = preg_split('/\s+/u', trim($name)); $text = '';
    foreach (array_slice($parts ?: [], 0, 2) as $part) { $text .= mb_substr($part, 0, 1); }
    return mb_strtoupper($text ?: 'A');
}
function client_key(): string { return hash('sha256', ($_SERVER['REMOTE_ADDR'] ?? 'unknown') . AST_LOGIN_PEPPER); }
function password_error(string $password): ?string {
    if (mb_strlen($password) < 12) { return 'Das Passwort muss mindestens 12 Zeichen enthalten.'; }
    if (!preg_match('/[A-ZÄÖÜ]/u', $password) || !preg_match('/[a-zäöü]/u', $password) || !preg_match('/\d/', $password)) {
        return 'Das Passwort muss Gross- und Kleinbuchstaben sowie mindestens eine Zahl enthalten.';
    }
    return null;
}

$userCount = (int)$db->query('SELECT COUNT(*) FROM users')->fetchColumn();
$action = (string)($_POST['action'] ?? '');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    require_csrf();

    if ($action === 'setup' && $userCount === 0) {
        $token = trim((string)($_POST['setup_token'] ?? ''));
        $name = trim((string)($_POST['name'] ?? ''));
        $email = mb_strtolower(trim((string)($_POST['email'] ?? '')));
        $password = (string)($_POST['password'] ?? '');
        $error = null;
        if (!hash_equals(AST_SETUP_TOKEN_HASH, hash('sha256', $token))) { $error = 'Der Einrichtungscode ist nicht korrekt.'; }
        elseif ($name === '' || mb_strlen($name) > 100) { $error = 'Bitte gib den vollständigen Namen an.'; }
        elseif (!filter_var($email, FILTER_VALIDATE_EMAIL)) { $error = 'Bitte gib eine gültige E-Mail-Adresse an.'; }
        elseif ($password !== (string)($_POST['password_confirm'] ?? '')) { $error = 'Die beiden Passwörter stimmen nicht überein.'; }
        elseif (($passwordMessage = password_error($password)) !== null) { $error = $passwordMessage; }
        if ($error) { set_flash('error', $error); redirect('/'); }
        $stamp = now();
        $stmt = $db->prepare('INSERT INTO users(name,email,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)');
        $stmt->execute([$name, $email, password_hash($password, PASSWORD_DEFAULT), 'admin', $stamp, $stamp]);
        $id = (int)$db->lastInsertId(); audit($db, $id, 'setup_completed', 'Erster Administrator erstellt');
        session_regenerate_id(true); $_SESSION['user_id'] = $id; unset($_SESSION['csrf']);
        set_flash('success', 'Die Benutzerverwaltung wurde eingerichtet. Willkommen im AST Manager.');
        redirect('/');
    }

    if ($action === 'login' && $userCount > 0) {
        $email = mb_strtolower(trim((string)($_POST['email'] ?? '')));
        $emailHash = hash('sha256', $email . AST_LOGIN_PEPPER); $ipHash = client_key();
        $since = gmdate('Y-m-d\TH:i:s\Z', time() - 900);
        $stmt = $db->prepare('SELECT COUNT(*) FROM login_attempts WHERE ip_hash=? AND attempted_at>=? AND successful=0');
        $stmt->execute([$ipHash, $since]);
        if ((int)$stmt->fetchColumn() >= 8) {
            set_flash('error', 'Zu viele Anmeldeversuche. Bitte warte 15 Minuten.'); redirect('/');
        }
        $stmt = $db->prepare('SELECT * FROM users WHERE email=?'); $stmt->execute([$email]); $candidate = $stmt->fetch();
        $valid = $candidate && (int)$candidate['active'] === 1 && password_verify((string)($_POST['password'] ?? ''), $candidate['password_hash']);
        $log = $db->prepare('INSERT INTO login_attempts(ip_hash,email_hash,attempted_at,successful) VALUES(?,?,?,?)');
        $log->execute([$ipHash, $emailHash, now(), $valid ? 1 : 0]);
        $db->prepare('DELETE FROM login_attempts WHERE attempted_at<?')->execute([gmdate('Y-m-d\TH:i:s\Z', time() - 86400)]);
        if (!$valid) { set_flash('error', 'E-Mail-Adresse oder Passwort ist nicht korrekt.'); redirect('/'); }
        session_regenerate_id(true); $_SESSION['user_id'] = (int)$candidate['id']; unset($_SESSION['csrf']);
        $db->prepare('UPDATE users SET last_login_at=? WHERE id=?')->execute([now(), (int)$candidate['id']]);
        audit($db, (int)$candidate['id'], 'login'); redirect('/');
    }

    $user = current_user($db);
    if (!$user) { redirect('/'); }

    if ($action === 'logout') {
        audit($db, (int)$user['id'], 'logout'); $_SESSION = []; session_destroy(); redirect('/');
    }

    if ($user['role'] !== 'admin') { http_response_code(403); exit('Diese Aktion ist Administratoren vorbehalten.'); }

    if ($action === 'create_user') {
        $name = trim((string)($_POST['name'] ?? '')); $email = mb_strtolower(trim((string)($_POST['email'] ?? '')));
        $role = (string)($_POST['role'] ?? 'readonly'); $password = (string)($_POST['password'] ?? '');
        $error = null;
        if ($name === '' || mb_strlen($name) > 100) { $error = 'Bitte gib einen Namen an.'; }
        elseif (!filter_var($email, FILTER_VALIDATE_EMAIL)) { $error = 'Bitte gib eine gültige E-Mail-Adresse an.'; }
        elseif (!in_array($role, ['admin','management','readonly'], true)) { $error = 'Die Rolle ist ungültig.'; }
        elseif (($passwordMessage = password_error($password)) !== null) { $error = $passwordMessage; }
        if ($error) { set_flash('error', $error); redirect('/?page=users'); }
        try {
            $stamp = now(); $stmt = $db->prepare('INSERT INTO users(name,email,password_hash,role,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)');
            $stmt->execute([$name,$email,password_hash($password,PASSWORD_DEFAULT),$role,$stamp,$stamp]);
            audit($db,(int)$user['id'],'user_created',$email.' · '.role_name($role));
            set_flash('success','Der Benutzer wurde angelegt.');
        } catch (PDOException $exception) {
            set_flash('error', str_contains($exception->getMessage(),'UNIQUE') ? 'Diese E-Mail-Adresse wird bereits verwendet.' : 'Der Benutzer konnte nicht gespeichert werden.');
        }
        redirect('/?page=users');
    }

    if ($action === 'update_user') {
        $id = (int)($_POST['user_id'] ?? 0); $name = trim((string)($_POST['name'] ?? ''));
        $email = mb_strtolower(trim((string)($_POST['email'] ?? ''))); $role = (string)($_POST['role'] ?? 'readonly');
        $password = (string)($_POST['password'] ?? '');
        if ($id < 1 || $name === '' || !filter_var($email,FILTER_VALIDATE_EMAIL) || !in_array($role,['admin','management','readonly'],true)) {
            set_flash('error','Bitte prüfe Name, E-Mail-Adresse und Rolle.'); redirect('/?page=users');
        }
        if ($id === (int)$user['id'] && $role !== 'admin') { set_flash('error','Die eigene Administratorrolle kann nicht entfernt werden.'); redirect('/?page=users'); }
        if ($password !== '' && ($passwordMessage = password_error($password)) !== null) { set_flash('error',$passwordMessage); redirect('/?page=users&edit='.$id); }
        try {
            if ($password !== '') {
                $stmt=$db->prepare('UPDATE users SET name=?,email=?,role=?,password_hash=?,updated_at=? WHERE id=?');
                $stmt->execute([$name,$email,$role,password_hash($password,PASSWORD_DEFAULT),now(),$id]);
            } else {
                $stmt=$db->prepare('UPDATE users SET name=?,email=?,role=?,updated_at=? WHERE id=?'); $stmt->execute([$name,$email,$role,now(),$id]);
            }
            audit($db,(int)$user['id'],'user_updated',$email); set_flash('success','Der Benutzer wurde aktualisiert.');
        } catch (PDOException $exception) { set_flash('error','Die E-Mail-Adresse wird möglicherweise bereits verwendet.'); }
        redirect('/?page=users');
    }

    if ($action === 'toggle_user') {
        $id=(int)($_POST['user_id']??0); $active=(int)($_POST['active']??0)===1?1:0;
        if ($id === (int)$user['id']) { set_flash('error','Das eigene Konto kann nicht gesperrt werden.'); redirect('/?page=users'); }
        $stmt=$db->prepare('UPDATE users SET active=?,updated_at=? WHERE id=?'); $stmt->execute([$active,now(),$id]);
        audit($db,(int)$user['id'],$active?'user_activated':'user_deactivated','Benutzer-ID '.$id);
        set_flash('success',$active?'Der Benutzer wurde aktiviert.':'Der Benutzer wurde gesperrt.'); redirect('/?page=users');
    }
}

$user = current_user($db); $flash = take_flash();
$page = (string)($_GET['page'] ?? 'dashboard');
if (!$user) { $page = $userCount === 0 ? 'setup' : 'login'; }
$users = []; $editUser = null; $auditRows = [];
if ($user && $page === 'users' && $user['role'] === 'admin') {
    $users = $db->query('SELECT * FROM users ORDER BY active DESC,name COLLATE NOCASE')->fetchAll();
    if (!empty($_GET['edit'])) { $stmt=$db->prepare('SELECT * FROM users WHERE id=?'); $stmt->execute([(int)$_GET['edit']]); $editUser=$stmt->fetch()?:null; }
    $auditRows = $db->query('SELECT a.*,u.name AS user_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 8')->fetchAll();
}
?>
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#092f39">
<title>AST Manager</title>
<style>
:root{--navy:#092f39;--navy2:#0d414e;--ink:#0b2c3b;--muted:#617783;--green:#07856f;--green2:#0b9c82;--mint:#e5f5f0;--line:#dbe5e9;--paper:#fff;--canvas:#f3f7f8;--red:#c84848;--redbg:#fff0f0;--amber:#9a6816;--amberbg:#fff6df;--shadow:0 18px 55px rgba(14,49,61,.13)}
*{box-sizing:border-box}html{font-family:Inter,"Segoe UI",Arial,sans-serif;color:var(--ink);background:var(--canvas)}body{margin:0;min-height:100vh}button,input,select{font:inherit}button{cursor:pointer}.auth{min-height:100vh;display:grid;grid-template-columns:minmax(340px,46%) 1fr;background:#fff}.auth-brand{background:linear-gradient(145deg,var(--navy),#0e5660);color:#fff;padding:clamp(38px,6vw,90px);display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden}.auth-brand:after{content:"AST";position:absolute;right:-40px;bottom:-50px;font-size:240px;font-weight:900;color:rgba(255,255,255,.045)}.logo{font-size:42px;font-weight:850;letter-spacing:-1px}.logo small{display:block;color:#75dbc9;font-size:12px;letter-spacing:.15em;margin-top:8px}.auth-copy{position:relative;z-index:1}.auth-copy h1{font-size:clamp(32px,4vw,55px);line-height:1.05;letter-spacing:-.045em;margin:0 0 18px}.auth-copy p{color:#cce4e6;line-height:1.6;max-width:520px}.auth-foot{color:#8db9bf;font-size:13px}.auth-main{display:grid;place-items:center;padding:35px}.auth-card{width:min(460px,100%)}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.1em;color:var(--green);text-transform:uppercase;margin-bottom:10px}h1,h2,h3,p{margin-top:0}.auth-card h2{font-size:31px;letter-spacing:-.03em;margin-bottom:9px}.sub{color:var(--muted);line-height:1.5;margin-bottom:26px}.field{display:grid;gap:7px;margin-bottom:16px}.field label{font-size:13px;font-weight:700}.input{width:100%;border:1px solid #cbd9df;background:#fff;border-radius:11px;padding:12px 13px;color:var(--ink);outline:none}.input:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(7,133,111,.12)}.hint{font-size:12px;color:var(--muted);line-height:1.45}.btn{border:0;border-radius:11px;background:var(--green);color:#fff;font-weight:750;padding:12px 17px}.btn:hover{background:var(--green2)}.btn.full{width:100%;margin-top:5px}.btn.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}.btn.danger{background:#fff;color:var(--red);border:1px solid #efc9c9}.alert{padding:13px 15px;border-radius:11px;font-size:13px;line-height:1.45;margin-bottom:18px}.alert.error{color:#8e3030;background:var(--redbg);border:1px solid #f1cccc}.alert.success{color:#075f51;background:var(--mint);border:1px solid #b9dfd6}.setup-note{padding:14px;background:var(--amberbg);color:#765515;border:1px solid #efdcaa;border-radius:12px;font-size:13px;line-height:1.5;margin-bottom:20px}
.shell{min-height:100vh;display:grid;grid-template-columns:252px minmax(0,1fr)}aside{background:linear-gradient(180deg,var(--navy),#0b3945);color:#fff;padding:28px 18px 22px;display:flex;flex-direction:column;position:sticky;top:0;height:100vh}.side-logo{padding:4px 10px 27px}.side-logo strong{font-size:38px;display:block}.side-logo span{color:#79ddcc;font-size:12px;letter-spacing:.13em}.nav-label{font-size:11px;color:#83b4bd;letter-spacing:.13em;padding:0 12px;margin:12px 0 8px}nav{display:grid;gap:5px}.nav{border:0;background:transparent;color:#d8e8eb;border-radius:12px;display:flex;align-items:center;gap:12px;text-decoration:none;padding:12px 13px}.nav:hover{background:rgba(255,255,255,.08);color:#fff}.nav.active{background:#e4f4f0;color:#073c46;font-weight:750;box-shadow:inset 4px 0 #33cbb1}.nav i{font-style:normal;width:22px;text-align:center}.aside-foot{margin-top:auto;padding:15px 10px 3px;color:#a9cad0;font-size:12px;line-height:1.55}.aside-foot strong{color:#7ce0ce;display:block}.logout{border:0;background:transparent;color:#a9cad0;padding:8px 0;text-align:left}.logout:hover{color:#fff}main{padding:37px clamp(24px,4vw,60px) 48px;max-width:1500px;width:100%;margin:0 auto}.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:27px}.top h1{font-size:clamp(29px,3vw,42px);letter-spacing:-.04em;margin-bottom:8px}.profile{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:8px 12px 8px 8px}.avatar{width:39px;height:39px;border-radius:11px;background:var(--mint);color:var(--green);display:grid;place-items:center;font-weight:850}.profile small{display:block;color:var(--muted);margin-top:2px}.card{background:#fff;border:1px solid var(--line);border-radius:17px;padding:21px;box-shadow:0 7px 24px rgba(17,49,61,.045)}.hero{background:linear-gradient(120deg,#0b755f,#0c9077);border:0;color:#fff;padding:28px 30px;margin-bottom:22px;box-shadow:0 16px 40px rgba(7,133,111,.2)}.hero h2{font-size:24px;margin-bottom:7px}.hero p{color:#d8f6ef;margin:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-bottom:25px}.stat .label{font-size:13px;color:var(--muted);margin-bottom:11px}.stat strong{font-size:27px}.stat small{display:block;color:var(--muted);margin-top:7px}.module-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.module{min-height:150px;display:flex;flex-direction:column}.module-icon{width:41px;height:41px;border-radius:12px;background:#edf4f5;display:grid;place-items:center;font-size:20px;margin-bottom:18px}.module h3{font-size:16px;margin-bottom:6px}.module p{font-size:13px;color:var(--muted);line-height:1.45}.tag{display:inline-flex;align-items:center;border-radius:999px;background:#edf4f5;color:#516a75;padding:5px 9px;font-size:11px;font-weight:750;margin-top:auto;width:max-content}.section-head{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:15px}.section-head h2{font-size:21px;margin:0}.user-layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,.7fr);gap:20px}.table-card{padding:0;overflow:hidden}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:14px 16px;text-align:left;border-bottom:1px solid #e6edef;font-size:13px}th{background:#edf3f5;color:#4e6874;font-size:12px;letter-spacing:.02em}tr:last-child td{border-bottom:0}.status{display:inline-flex;align-items:center;gap:6px;font-weight:700}.status:before{content:"";width:8px;height:8px;border-radius:50%;background:#1baa82}.status.off{color:#9c4a4a}.status.off:before{background:#d35d5d}.actions{display:flex;gap:7px;justify-content:flex-end}.mini{border:1px solid var(--line);background:#fff;border-radius:9px;color:var(--ink);padding:7px 10px;font-size:12px;font-weight:700}.mini.red{color:var(--red)}.form-card h2{font-size:19px;margin-bottom:5px}.form-card .sub{font-size:13px;margin-bottom:18px}.form-actions{display:flex;gap:9px;align-items:center}.audit{margin-top:22px}.audit-list{display:grid}.audit-row{display:grid;grid-template-columns:160px 1fr auto;gap:15px;padding:12px 0;border-bottom:1px solid #e8eef0;font-size:13px}.audit-row:last-child{border:0}.audit-row time,.audit-row span{color:var(--muted)}.mobile{display:none}
@media(max-width:1100px){.stats,.module-grid{grid-template-columns:repeat(2,1fr)}.user-layout{grid-template-columns:1fr}}
@media(max-width:760px){.auth{grid-template-columns:1fr}.auth-brand{min-height:230px;padding:30px}.auth-copy h1{font-size:34px}.auth-foot{display:none}.auth-main{padding:28px 20px}.shell{display:block}.mobile{display:flex;background:var(--navy);color:#fff;padding:14px 18px;justify-content:space-between;align-items:center}.mobile button{background:rgba(255,255,255,.1);color:#fff;border:0;border-radius:9px;padding:8px 10px}aside{position:fixed;left:-270px;z-index:20;width:252px;transition:.2s;box-shadow:20px 0 50px rgba(0,0,0,.2)}aside.open{left:0}main{padding:25px 17px}.top{display:block}.profile{display:none}.stats,.module-grid{grid-template-columns:1fr}.audit-row{grid-template-columns:1fr;gap:4px}}
</style>
</head>
<body>
<?php if (!$user): ?>
<div class="auth">
  <section class="auth-brand">
    <div class="logo">AST<small>VERWALTUNG</small></div>
    <div class="auth-copy"><h1>Ein Ort.<br>Klare Abläufe.</h1><p>Die zentrale Verwaltung für Rechnungen, Arbeitszeiten, Personalunterlagen und Bewerbungen.</p></div>
    <div class="auth-foot">AST Elektro Tüscher AG · Geschützter Bereich</div>
  </section>
  <main class="auth-main"><div class="auth-card">
    <div class="eyebrow"><?= $page === 'setup' ? 'Ersteinrichtung' : 'Sicherer Zugang' ?></div>
    <h2><?= $page === 'setup' ? 'Administrator einrichten' : 'Willkommen zurück' ?></h2>
    <p class="sub"><?= $page === 'setup' ? 'Erstelle das erste Administratorkonto. Die Einrichtung wird danach automatisch geschlossen.' : 'Melde dich mit deinem persönlichen Benutzerkonto an.' ?></p>
    <?php if ($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?>
    <?php if ($page === 'setup'): ?>
      <div class="setup-note"><strong>Einmalige Einrichtung</strong><br>Den Einrichtungscode erhältst du von der Person, welche den AST Manager installiert hat.</div>
      <form method="post" autocomplete="off">
        <input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="setup">
        <div class="field"><label for="setup_token">Einrichtungscode</label><input class="input" id="setup_token" name="setup_token" required autocomplete="off"></div>
        <div class="field"><label for="name">Vollständiger Name</label><input class="input" id="name" name="name" maxlength="100" required autocomplete="name"></div>
        <div class="field"><label for="email">E-Mail-Adresse</label><input class="input" type="email" id="email" name="email" required autocomplete="email"></div>
        <div class="field"><label for="password">Passwort</label><input class="input" type="password" id="password" name="password" required minlength="12" autocomplete="new-password"><span class="hint">Mindestens 12 Zeichen, Gross- und Kleinbuchstaben sowie eine Zahl.</span></div>
        <div class="field"><label for="password_confirm">Passwort wiederholen</label><input class="input" type="password" id="password_confirm" name="password_confirm" required minlength="12" autocomplete="new-password"></div>
        <button class="btn full" type="submit">Administrator erstellen →</button>
      </form>
    <?php else: ?>
      <form method="post">
        <input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="login">
        <div class="field"><label for="email">E-Mail-Adresse</label><input class="input" type="email" id="email" name="email" required autofocus autocomplete="username"></div>
        <div class="field"><label for="password">Passwort</label><input class="input" type="password" id="password" name="password" required autocomplete="current-password"></div>
        <button class="btn full" type="submit">Anmelden →</button>
      </form>
    <?php endif; ?>
  </div></main>
</div>
<?php else: ?>
<div class="mobile"><strong>AST Manager</strong><button type="button" onclick="document.querySelector('aside').classList.toggle('open')">☰ Menü</button></div>
<div class="shell">
<aside>
  <div class="side-logo"><strong>AST</strong><span>VERWALTUNG</span></div>
  <div class="nav-label">ARBEITSBEREICHE</div>
  <nav>
    <a class="nav <?= $page==='dashboard'?'active':'' ?>" href="/"><i>▣</i>Übersicht</a>
    <a class="nav" href="/?page=module&name=Debitoren"><i>▤</i>Debitoren</a><a class="nav" href="/?page=module&name=Mahnungen"><i>△</i>Mahnungen</a>
    <a class="nav" href="/?page=module&name=Stundennachweis"><i>◫</i>Stundennachweis</a><a class="nav" href="/?page=module&name=Zeugnisse"><i>◉</i>Zeugnisse</a>
    <a class="nav" href="/?page=module&name=Bewerbungen"><i>▰</i>Bewerbungen</a><a class="nav" href="/?page=module&name=Lohnausweise"><i>◧</i>Lohnausweise</a>
    <?php if ($user['role']==='admin'): ?><a class="nav <?= $page==='users'?'active':'' ?>" href="/?page=users"><i>♟</i>Benutzer</a><?php endif; ?>
  </nav>
  <div class="aside-foot"><strong><?= e($user['name']) ?></strong><?= e(role_name($user['role'])) ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="logout"><button class="logout" type="submit">Abmelden</button></form></div>
</aside>
<main>
  <?php if ($page==='users' && $user['role']==='admin'): ?>
    <div class="top"><div><div class="eyebrow">Einstellungen</div><h1>Benutzerverwaltung</h1><p class="sub">Zugänge, Rollen und Berechtigungen zentral verwalten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if ($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?>
    <div class="user-layout">
      <section><div class="section-head"><h2>Benutzerkonten</h2><span class="tag"><?= count($users) ?> Konten</span></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Rolle</th><th>Status</th><th>Letzte Anmeldung</th><th></th></tr></thead><tbody>
      <?php foreach($users as $row): ?><tr><td><strong><?= e($row['name']) ?></strong><br><span class="hint"><?= e($row['email']) ?></span></td><td><?= e(role_name($row['role'])) ?></td><td><span class="status <?= $row['active']?'':'off' ?>"><?= $row['active']?'Aktiv':'Gesperrt' ?></span></td><td><?= $row['last_login_at'] ? e(date('d.m.Y H:i', strtotime($row['last_login_at']))) : 'Noch nie' ?></td><td><div class="actions"><a class="mini" href="/?page=users&edit=<?= (int)$row['id'] ?>">Bearbeiten</a><?php if ((int)$row['id']!==(int)$user['id']): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="toggle_user"><input type="hidden" name="user_id" value="<?= (int)$row['id'] ?>"><input type="hidden" name="active" value="<?= $row['active']?0:1 ?>"><button class="mini <?= $row['active']?'red':'' ?>" type="submit"><?= $row['active']?'Sperren':'Aktivieren' ?></button></form><?php endif; ?></div></td></tr><?php endforeach; ?>
      </tbody></table></div></div></section>
      <section class="card form-card"><h2><?= $editUser?'Benutzer bearbeiten':'Neuer Benutzer' ?></h2><p class="sub"><?= $editUser?'Änderungen gelten ab der nächsten Anmeldung.':'Erstelle einen persönlichen, nachvollziehbaren Zugang.' ?></p>
        <form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="<?= $editUser?'update_user':'create_user' ?>"><?php if($editUser): ?><input type="hidden" name="user_id" value="<?= (int)$editUser['id'] ?>"><?php endif; ?>
          <div class="field"><label>Name</label><input class="input" name="name" required maxlength="100" value="<?= e($editUser['name']??'') ?>"></div>
          <div class="field"><label>E-Mail-Adresse</label><input class="input" type="email" name="email" required value="<?= e($editUser['email']??'') ?>"></div>
          <div class="field"><label>Rolle</label><select class="input" name="role"><option value="readonly" <?= ($editUser['role']??'')==='readonly'?'selected':'' ?>>Nur Lesen</option><option value="management" <?= ($editUser['role']??'')==='management'?'selected':'' ?>>Verwaltung</option><option value="admin" <?= ($editUser['role']??'')==='admin'?'selected':'' ?>>Administrator</option></select><span class="hint">Administratoren verwalten Benutzer. Verwaltung darf Daten bearbeiten. Nur Lesen kann Daten ansehen.</span></div>
          <div class="field"><label><?= $editUser?'Neues Passwort (optional)':'Startpasswort' ?></label><input class="input" type="password" name="password" <?= $editUser?'':'required' ?> minlength="12" autocomplete="new-password"><span class="hint">Mindestens 12 Zeichen, Gross-/Kleinbuchstaben und eine Zahl.</span></div>
          <div class="form-actions"><button class="btn" type="submit"><?= $editUser?'Änderungen speichern':'Benutzer anlegen' ?></button><?php if($editUser): ?><a class="btn secondary" href="/?page=users">Abbrechen</a><?php endif; ?></div>
        </form>
      </section>
    </div>
    <section class="audit"><div class="section-head"><h2>Letzte Benutzeraktionen</h2></div><div class="card audit-list"><?php foreach($auditRows as $row): ?><div class="audit-row"><time><?= e(date('d.m.Y H:i',strtotime($row['created_at']))) ?></time><strong><?= e($row['user_name']??'System') ?> · <?= e($row['action']) ?></strong><span><?= e($row['details']) ?></span></div><?php endforeach; ?></div></section>
  <?php elseif ($page==='module'): $module=trim((string)($_GET['name']??'Bereich')); ?>
    <div class="top"><div><div class="eyebrow">Arbeitsbereich</div><h1><?= e($module) ?></h1><p class="sub">Dieser Bereich wird als Nächstes mit der gemeinsamen Datenbank verbunden.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <section class="card hero"><h2>Web-Ausbau vorbereitet</h2><p>Anmeldung und Rechteprüfung sind bereits aktiv. Die Fachdaten dieses Moduls werden anschließend übernommen.</p></section><section class="card"><h2>Sicher angemeldet</h2><p class="sub">Dein Zugriff wird entsprechend deiner Rolle <strong><?= e(role_name($user['role'])) ?></strong> geprüft.</p><a class="btn secondary" href="/">Zur Übersicht</a></section>
  <?php else: ?>
    <div class="top"><div><div class="eyebrow">Übersicht</div><h1>Guten Tag, <?= e(explode(' ',trim($user['name']))[0]) ?></h1><p class="sub">Was möchtest du heute erledigen?</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if ($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?>
    <section class="card hero"><h2>Die gemeinsame Web-Grundlage steht</h2><p>Benutzerkonten, Rollen und sichere Anmeldung sind aktiv. Die Fachdaten werden schrittweise angebunden.</p></section>
    <section class="stats"><div class="card stat"><div class="label">Offene Rechnungen</div><strong>–</strong><small>Datenanbindung folgt</small></div><div class="card stat"><div class="label">Arbeitszeiten</div><strong>–</strong><small>Datenanbindung folgt</small></div><div class="card stat"><div class="label">Bewerbungen</div><strong>–</strong><small>Datenanbindung folgt</small></div><div class="card stat"><div class="label">Deine Rolle</div><strong style="font-size:20px"><?= e(role_name($user['role'])) ?></strong><small>Persönlicher Zugang aktiv</small></div></section>
    <div class="section-head"><h2>Arbeitsbereiche</h2></div><section class="module-grid"><?php foreach([['▤','Debitoren'],['◫','Stundennachweis'],['▰','Bewerbungen'],['◉','Zeugnisse']] as [$icon,$name]): ?><article class="card module"><div class="module-icon"><?= $icon ?></div><h3><?= e($name) ?></h3><p>Für die Übernahme in die gemeinsame Web-Datenbank vorbereitet.</p><span class="tag">Nächster Ausbau</span></article><?php endforeach; ?></section>
  <?php endif; ?>
</main></div>
<?php endif; ?>
</body></html>
