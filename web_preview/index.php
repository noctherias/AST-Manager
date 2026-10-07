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
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL, last_name TEXT NOT NULL, personnel_number TEXT NOT NULL DEFAULT '',
    employee_type TEXT NOT NULL DEFAULT 'employee' CHECK(employee_type IN ('employee','apprentice')),
    entry_date TEXT, vacation_hours REAL NOT NULL DEFAULT 173, active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE, customer TEXT NOT NULL, invoice_date TEXT NOT NULL,
    due_date TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, paid_amount REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, customer TEXT NOT NULL,
    invoice_number TEXT NOT NULL DEFAULT '', level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 4),
    amount REAL NOT NULL DEFAULT 0, reminder_date TEXT NOT NULL, reminder_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, work_date TEXT NOT NULL,
    hours REAL NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT 'Arbeit', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, UNIQUE(employee_id,work_date),
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
    certificate_type TEXT NOT NULL CHECK(certificate_type IN ('Arbeitszeugnis','Zwischenzeugnis','Lehrzeugnis')),
    reference_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Entwurf', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, applicant_name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', application_type TEXT NOT NULL, received_date TEXT NOT NULL,
    rating TEXT NOT NULL DEFAULT 'Offen', notes TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'Manuell',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS salary_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, tax_year INTEGER NOT NULL,
    gross_salary REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Entwurf', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, UNIQUE(employee_id,tax_year),
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    customer_number TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', postcode TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, payment_date TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount>0), notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS reminder_templates (
    level INTEGER PRIMARY KEY CHECK(level BETWEEN 1 AND 4), title TEXT NOT NULL, body TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO sync_state(id,revision,updated_at) VALUES(1,0,'');
CREATE TABLE IF NOT EXISTS application_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL, category TEXT NOT NULL DEFAULT 'other',
    original_name TEXT NOT NULL, source_ref TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    UNIQUE(application_id,source_ref), FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
);
SQL);
$columnMigrations = [
    'employees' => [
        'salutation'=>"TEXT NOT NULL DEFAULT ''", 'ahv'=>"TEXT NOT NULL DEFAULT ''", 'ahv_old'=>"TEXT NOT NULL DEFAULT ''",
        'birth_date'=>"TEXT NOT NULL DEFAULT ''", 'address'=>"TEXT NOT NULL DEFAULT ''", 'postcode'=>"TEXT NOT NULL DEFAULT ''",
        'city'=>"TEXT NOT NULL DEFAULT ''", 'job'=>"TEXT NOT NULL DEFAULT ''", 'workload'=>"REAL NOT NULL DEFAULT 100"
    ],
    'applications' => [
        'first_name'=>"TEXT NOT NULL DEFAULT ''", 'last_name'=>"TEXT NOT NULL DEFAULT ''", 'address'=>"TEXT NOT NULL DEFAULT ''",
        'postcode'=>"TEXT NOT NULL DEFAULT ''", 'city'=>"TEXT NOT NULL DEFAULT ''", 'status'=>"TEXT NOT NULL DEFAULT 'Neu'",
        'trial_dates'=>"TEXT NOT NULL DEFAULT ''", 'vocational_baccalaureate'=>"INTEGER NOT NULL DEFAULT 0",
        'message'=>"TEXT NOT NULL DEFAULT ''", 'server_deleted'=>"INTEGER NOT NULL DEFAULT 0"
    ],
    'certificates' => [
        'reason'=>"TEXT NOT NULL DEFAULT ''", 'tasks'=>"TEXT NOT NULL DEFAULT ''", 'ratings'=>"TEXT NOT NULL DEFAULT '{}'",
        'generated_text'=>"TEXT NOT NULL DEFAULT ''"
    ],
    'salary_certificates' => ['period_start'=>"TEXT NOT NULL DEFAULT ''", 'period_end'=>"TEXT NOT NULL DEFAULT ''", 'fields_json'=>"TEXT NOT NULL DEFAULT '{}'"]
];
foreach($columnMigrations as $table=>$columns) {
    $existing=[]; foreach($db->query("PRAGMA table_info($table)") as $info) $existing[$info['name']]=true;
    foreach($columns as $name=>$definition) if(!isset($existing[$name])) $db->exec("ALTER TABLE $table ADD COLUMN $name $definition");
}
$templateCount=(int)$db->query('SELECT COUNT(*) FROM reminder_templates')->fetchColumn();
if($templateCount===0) {
    $templates=[1=>['Zahlungserinnerung','Bitte begleichen Sie den offenen Betrag der Rechnung {rechnungsnummer} bis {zahlungsfrist}.'],2=>['Mahnung 1','Trotz unserer Zahlungserinnerung ist der Betrag der Rechnung {rechnungsnummer} noch offen.'],3=>['Mahnung 2','Wir bitten Sie letztmals, den offenen Betrag der Rechnung {rechnungsnummer} zu begleichen.'],4=>['Betreibung','Die Forderung der Rechnung {rechnungsnummer} wird zur Betreibung vorbereitet.']];
    $stmt=$db->prepare('INSERT INTO reminder_templates(level,title,body,updated_at) VALUES(?,?,?,?)'); foreach($templates as $level=>$values) $stmt->execute([$level,$values[0],$values[1],now()]);
}

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
function decimal_input(string $key): float {
    $value = str_replace(["'", ' '], '', trim((string)($_POST[$key] ?? '0')));
    $value = str_replace(',', '.', $value);
    return round(max(0, (float)$value), 2);
}
function money(float $value): string { return 'CHF ' . number_format($value, 2, '.', "'"); }
function valid_date(string $value): bool { $date = DateTimeImmutable::createFromFormat('Y-m-d', $value); return $date && $date->format('Y-m-d') === $value; }
function can_write(array $user): bool { return in_array($user['role'], ['admin','management'], true); }
function bump_revision(PDO $db): void { $db->prepare('UPDATE sync_state SET revision=revision+1,updated_at=? WHERE id=1')->execute([now()]); }
function source_has_table(PDO $source, string $table): bool {
    $stmt=$source->prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"); $stmt->execute([$table]); return (bool)$stmt->fetchColumn();
}
function source_rows(PDO $source, string $sql): array { return $source->query($sql)->fetchAll(PDO::FETCH_ASSOC); }

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

    $businessActions = ['save_invoice','save_reminder','save_employee','save_time','save_certificate','save_application','rate_application','save_salary','save_settings'];
    if (in_array($action, $businessActions, true) && !can_write($user)) {
        http_response_code(403); exit('Deine Rolle erlaubt keine Änderungen.');
    }

    if ($action === 'save_invoice') {
        $number=trim((string)($_POST['invoice_number']??'')); $customer=trim((string)($_POST['customer']??''));
        $invoiceDate=(string)($_POST['invoice_date']??''); $dueDate=(string)($_POST['due_date']??'');
        if ($number==='' || $customer==='' || !valid_date($invoiceDate) || !valid_date($dueDate)) { set_flash('error','Bitte fülle Rechnungsnummer, Kunde und beide Datumsfelder aus.'); redirect('/?page=invoices'); }
        try { $stmt=$db->prepare('INSERT INTO invoices(invoice_number,customer,invoice_date,due_date,amount,paid_amount,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)');
            $stmt->execute([$number,$customer,$invoiceDate,$dueDate,decimal_input('amount'),decimal_input('paid_amount'),trim((string)($_POST['notes']??'')),now(),now()]);
            bump_revision($db); audit($db,(int)$user['id'],'invoice_created',$number); set_flash('success','Die Rechnung wurde gespeichert.');
        } catch(PDOException $exception) { set_flash('error','Diese Rechnungsnummer ist bereits vorhanden.'); }
        redirect('/?page=invoices');
    }
    if ($action === 'save_reminder') {
        $level=(int)($_POST['level']??1); $date=(string)($_POST['reminder_date']??''); $customer=trim((string)($_POST['customer']??''));
        if ($customer==='' || !valid_date($date) || $level<1 || $level>4) { set_flash('error','Bitte prüfe Empfänger, Datum und Mahnstufe.'); redirect('/?page=reminders'); }
        $stmt=$db->prepare('INSERT INTO reminders(invoice_id,customer,invoice_number,level,amount,reminder_date,reminder_text,status,created_at) VALUES(NULL,?,?,?,?,?,?,?,?)');
        $stmt->execute([$customer,trim((string)($_POST['invoice_number']??'')),$level,decimal_input('amount'),$date,trim((string)($_POST['reminder_text']??'')),'Entwurf',now()]);
        bump_revision($db); audit($db,(int)$user['id'],'reminder_created',$customer.' · Stufe '.$level); set_flash('success','Die Mahnung wurde als Entwurf gespeichert.'); redirect('/?page=reminders');
    }
    if ($action === 'save_employee') {
        $first=trim((string)($_POST['first_name']??'')); $last=trim((string)($_POST['last_name']??'')); $type=(string)($_POST['employee_type']??'employee');
        if ($first==='' || $last==='' || !in_array($type,['employee','apprentice'],true)) { set_flash('error','Bitte gib Vorname, Nachname und Personengruppe an.'); redirect('/?page=timesheets'); }
        $vacation=$type==='apprentice'?216.25:173.0; $stmt=$db->prepare('INSERT INTO employees(first_name,last_name,personnel_number,employee_type,entry_date,vacation_hours,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)');
        $stmt->execute([$first,$last,trim((string)($_POST['personnel_number']??'')),$type,($_POST['entry_date']??'')?:null,$vacation,now(),now()]);
        bump_revision($db); audit($db,(int)$user['id'],'employee_created',$first.' '.$last); set_flash('success','Die Person wurde gespeichert.'); redirect('/?page=timesheets');
    }
    if ($action === 'save_time') {
        $employee=(int)($_POST['employee_id']??0); $date=(string)($_POST['work_date']??''); $hours=decimal_input('hours');
        $reasons=['Arbeit','Ferien','Krankheit','Unfall','Begründete Minderzeit']; $reason=(string)($_POST['reason']??'Arbeit');
        if ($employee<1 || !valid_date($date) || $hours>24 || !in_array($reason,$reasons,true)) { set_flash('error','Bitte prüfe Person, Datum, Stunden und Grund.'); redirect('/?page=timesheets'); }
        $stmt=$db->prepare('INSERT INTO time_entries(employee_id,work_date,hours,reason,notes,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(employee_id,work_date) DO UPDATE SET hours=excluded.hours,reason=excluded.reason,notes=excluded.notes');
        $stmt->execute([$employee,$date,$hours,$reason,trim((string)($_POST['notes']??'')),now()]); bump_revision($db); audit($db,(int)$user['id'],'time_saved',$date.' · '.$hours.' h'); set_flash('success','Der Zeiteintrag wurde gespeichert.'); redirect('/?page=timesheets');
    }
    if ($action === 'save_certificate') {
        $employee=(int)($_POST['employee_id']??0); $type=(string)($_POST['certificate_type']??'Arbeitszeugnis'); $date=(string)($_POST['reference_date']??'');
        if ($employee<1 || !valid_date($date) || !in_array($type,['Arbeitszeugnis','Zwischenzeugnis','Lehrzeugnis'],true)) { set_flash('error','Bitte prüfe Person, Zeugnisart und Datum.'); redirect('/?page=certificates'); }
        $stmt=$db->prepare('INSERT INTO certificates(employee_id,certificate_type,reference_date,status,notes,created_at) VALUES(?,?,?,\'Entwurf\',?,?)');
        $stmt->execute([$employee,$type,$date,trim((string)($_POST['notes']??'')),now()]); bump_revision($db); audit($db,(int)$user['id'],'certificate_created',$type); set_flash('success','Der Zeugnisentwurf wurde angelegt.'); redirect('/?page=certificates');
    }
    if ($action === 'save_application') {
        $name=trim((string)($_POST['applicant_name']??'')); $type=(string)($_POST['application_type']??'Schnupperlehre'); $date=(string)($_POST['received_date']??'');
        if ($name==='' || !valid_date($date)) { set_flash('error','Bitte gib Name und Eingangsdatum an.'); redirect('/?page=applications'); }
        $stmt=$db->prepare('INSERT INTO applications(applicant_name,email,phone,application_type,received_date,rating,notes,source,created_at) VALUES(?,?,?,?,?,\'Offen\',?,\'Manuell\',?)');
        $stmt->execute([$name,trim((string)($_POST['email']??'')),trim((string)($_POST['phone']??'')),$type,$date,trim((string)($_POST['notes']??'')),now()]); bump_revision($db); audit($db,(int)$user['id'],'application_created',$name); set_flash('success','Die Bewerbung wurde erfasst.'); redirect('/?page=applications');
    }
    if ($action === 'rate_application') {
        $id=(int)($_POST['application_id']??0); $rating=(string)($_POST['rating']??'Offen');
        if (!in_array($rating,['Offen','Nicht geeignet','Eventuell','Geeignet'],true)) { set_flash('error','Die Beurteilung ist ungültig.'); redirect('/?page=applications'); }
        $stmt=$db->prepare('UPDATE applications SET rating=?,notes=? WHERE id=?'); $stmt->execute([$rating,trim((string)($_POST['notes']??'')),$id]); bump_revision($db); audit($db,(int)$user['id'],'application_rated','Bewerbung '.$id.' · '.$rating); set_flash('success','Beurteilung und Notiz wurden gespeichert.'); redirect('/?page=applications');
    }
    if ($action === 'save_salary') {
        $employee=(int)($_POST['employee_id']??0); $year=(int)($_POST['tax_year']??date('Y'));
        if ($employee<1 || $year<2000 || $year>2100) { set_flash('error','Bitte prüfe Person und Steuerjahr.'); redirect('/?page=salary'); }
        try { $stmt=$db->prepare('INSERT INTO salary_certificates(employee_id,tax_year,gross_salary,status,notes,created_at) VALUES(?,?,?,\'Entwurf\',?,?)');
            $stmt->execute([$employee,$year,decimal_input('gross_salary'),trim((string)($_POST['notes']??'')),now()]); bump_revision($db); set_flash('success','Der Lohnausweis-Entwurf wurde angelegt.'); audit($db,(int)$user['id'],'salary_created',(string)$year);
        } catch(PDOException $exception) { set_flash('error','Für diese Person und dieses Jahr besteht bereits ein Lohnausweis.'); }
        redirect('/?page=salary');
    }
    if ($action === 'save_settings') {
        foreach(['company_name','company_address','company_postcode_city','company_phone','company_email'] as $key) {
            $stmt=$db->prepare('INSERT INTO app_settings(setting_key,setting_value,updated_at) VALUES(?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at');
            $stmt->execute([$key,trim((string)($_POST[$key]??'')),now()]);
        }
        bump_revision($db); audit($db,(int)$user['id'],'settings_updated'); set_flash('success','Die Firmeneinstellungen wurden gespeichert.'); redirect('/?page=settings');
    }

    if ($user['role'] !== 'admin') { http_response_code(403); exit('Diese Aktion ist Administratoren vorbehalten.'); }

    if ($action === 'import_backup') {
        $file=$_FILES['backup_file']??null;
        if (!$file || (int)$file['error']!==UPLOAD_ERR_OK) { set_flash('error','Bitte wähle eine gültige AST-Sicherungsdatei.'); redirect('/?page=settings'); }
        if ((int)$file['size']<100 || (int)$file['size']>64*1024*1024) { set_flash('error','Die Sicherung muss zwischen 100 Bytes und 64 MB gross sein.'); redirect('/?page=settings'); }
        $handle=fopen($file['tmp_name'],'rb'); $header=$handle?fread($handle,16):''; if($handle) fclose($handle);
        if ($header!=="SQLite format 3\0") { set_flash('error','Die Datei ist keine gültige SQLite-Sicherung.'); redirect('/?page=settings'); }
        $importDir=$storage.'/imports'; $backupDir=$storage.'/backups';
        if(!is_dir($importDir)) mkdir($importDir,0770,true); if(!is_dir($backupDir)) mkdir($backupDir,0770,true);
        $importPath=$importDir.'/desktop-'.bin2hex(random_bytes(8)).'.sqlite3';
        if(!move_uploaded_file($file['tmp_name'],$importPath)) { set_flash('error','Die Sicherung konnte nicht geschützt abgelegt werden.'); redirect('/?page=settings'); }
        try {
            $source=new PDO('sqlite:'.$importPath,null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
            foreach(['employees','customers','invoices','payments','time_records'] as $required) if(!source_has_table($source,$required)) throw new RuntimeException('Die Datei ist keine vollständige AST-Desktop-Sicherung. Tabelle fehlt: '.$required);
            $db->exec('PRAGMA wal_checkpoint(FULL)');
            $safety=$backupDir.'/web-vor-import-'.date('Ymd-His').'.sqlite3';
            if(!copy($storage.'/ast-manager.sqlite3',$safety)) throw new RuntimeException('Die automatische Sicherung vor dem Import ist fehlgeschlagen.');
            $counts=['Kunden'=>0,'Personen'=>0,'Rechnungen'=>0,'Zahlungen'=>0,'Zeiten'=>0,'Zeugnisse'=>0,'Bewerbungen'=>0,'Lohnausweise'=>0];
            $db->beginTransaction();
            foreach(['invoice_payments','reminders','invoices','time_entries','certificates','salary_certificates','applications','employees','customers'] as $table) $db->exec('DELETE FROM '.$table);
            $stmt=$db->prepare('INSERT INTO customers(id,name,customer_number,address,postcode,city,email,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)');
            foreach(source_rows($source,'SELECT * FROM customers ORDER BY id') as $row) { $stmt->execute([(int)$row['id'],$row['name'],$row['customer_number']??'',$row['address']??'',$row['postcode']??'',$row['city']??'',$row['email']??'',now(),now()]); $counts['Kunden']++; }
            $stmt=$db->prepare('INSERT INTO employees(id,first_name,last_name,personnel_number,employee_type,entry_date,vacation_hours,active,created_at,updated_at,salutation,ahv,ahv_old,birth_date,address,postcode,city,job,workload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
            foreach(source_rows($source,'SELECT * FROM employees ORDER BY id') as $row) { $stmt->execute([(int)$row['id'],$row['first_name'],$row['last_name'],$row['code']??'',($row['kind']??'employee')==='apprentice'?'apprentice':'employee',$row['hired']??null,((int)($row['allowance']??17300))/100,(int)($row['active']??1),now(),now(),$row['salutation']??'',$row['ahv']??'',$row['ahv_old']??'',$row['birth_date']??'',$row['address']??'',$row['postcode']??'',$row['city']??'',$row['job']??'',((int)($row['workload']??10000))/100]); $counts['Personen']++; }
            $invoiceRows=source_rows($source,"SELECT i.*,c.name AS customer,COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id=i.id),0) AS paid FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.id");
            $stmt=$db->prepare('INSERT INTO invoices(id,invoice_number,customer,invoice_date,due_date,amount,paid_amount,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)');
            $reminderStmt=$db->prepare('INSERT INTO reminders(invoice_id,customer,invoice_number,level,amount,reminder_date,reminder_text,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)');
            foreach($invoiceRows as $row) { $amount=((int)$row['amount'])/100; $paid=((int)$row['paid'])/100; $stmt->execute([(int)$row['id'],$row['number'],$row['customer'],$row['issued'],$row['due'],$amount,$paid,$row['note']??'',now(),now()]); $counts['Rechnungen']++; if((int)($row['reminder_level']??0)>0) $reminderStmt->execute([(int)$row['id'],$row['customer'],$row['number'],(int)$row['reminder_level'],max(0,$amount-$paid),$row['reminder_date']?:date('Y-m-d'),'','Aktiv',now()]); }
            $stmt=$db->prepare('INSERT INTO invoice_payments(id,invoice_id,payment_date,amount,notes,created_at) VALUES(?,?,?,?,?,?)');
            foreach(source_rows($source,'SELECT * FROM payments ORDER BY id') as $row) { $stmt->execute([(int)$row['id'],(int)$row['invoice_id'],$row['day'],((int)$row['amount'])/100,$row['note']??'',now()]); $counts['Zahlungen']++; }
            $reasonMap=[''=>'Arbeit','H'=>'Feiertag','F'=>'Ferien','K'=>'Krankheit','U'=>'Unfall','M'=>'Begründete Minderzeit','HO'=>'Homeoffice','B'=>'Bereitschaft'];
            $stmt=$db->prepare('INSERT INTO time_entries(id,employee_id,work_date,hours,reason,notes,created_at) VALUES(?,?,?,?,?,?,?)');
            foreach(source_rows($source,'SELECT * FROM time_records ORDER BY id') as $row) { $code=strtoupper(trim((string)($row['code']??''))); $stmt->execute([(int)$row['id'],(int)$row['employee_id'],$row['day'],((int)($row['worked_minutes']??0))/60,$reasonMap[$code]??'Begründete Minderzeit',$row['note']??'',now()]); $counts['Zeiten']++; }
            if(source_has_table($source,'employment_references')) { $stmt=$db->prepare('INSERT INTO certificates(id,employee_id,certificate_type,reference_date,status,notes,created_at,reason,tasks,ratings,generated_text) VALUES(?,?,?,?,?,?,?,?,?,?,?)'); $typeMap=['work'=>'Arbeitszeugnis','interim'=>'Zwischenzeugnis','apprentice'=>'Lehrzeugnis']; foreach(source_rows($source,'SELECT * FROM employment_references ORDER BY id') as $row) { $stmt->execute([(int)$row['id'],(int)$row['employee_id'],$typeMap[$row['reference_type']]??'Arbeitszeugnis',$row['issue_date'],'Gespeichert','',now(),$row['reason']??'',$row['tasks']??'',$row['ratings']??'{}',$row['text']??'']); $counts['Zeugnisse']++; } }
            if(source_has_table($source,'applicants')) { $stmt=$db->prepare('INSERT INTO applications(id,applicant_name,email,phone,application_type,received_date,rating,notes,source,created_at,first_name,last_name,address,postcode,city,status,trial_dates,vocational_baccalaureate,message,server_deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'); $cat=['trial'=>'Schnupperlehre','installer'=>'Elektroinstallateur/in EFZ','assembly'=>'Montage-Elektriker/in EFZ']; $rating=[''=>'Offen','unsuitable'=>'Nicht geeignet','possible'=>'Eventuell','suitable'=>'Geeignet']; foreach(source_rows($source,'SELECT * FROM applicants ORDER BY id') as $row) { $full=trim(($row['first_name']??'').' '.($row['last_name']??'')); $stmt->execute([(int)$row['id'],$full,$row['email']??'',$row['phone']??'',$cat[$row['category']]??'Schnupperlehre',substr((string)$row['submitted_at'],0,10),$rating[$row['suitability']??'']??'Offen',$row['notes']??'','Desktop-Import',now(),$row['first_name']??'',$row['last_name']??'',$row['address']??'',$row['postcode']??'',$row['city']??'',$row['status']??'new',$row['trial_dates']??'',(int)($row['vocational_baccalaureate']??0),$row['message']??'',(int)($row['server_deleted']??0)]); $counts['Bewerbungen']++; } }
            if(source_has_table($source,'salaries')) { $stmt=$db->prepare('INSERT INTO salary_certificates(id,employee_id,tax_year,gross_salary,status,notes,created_at,period_start,period_end,fields_json) VALUES(?,?,?,?,?,?,?,?,?,?)'); foreach(source_rows($source,'SELECT * FROM salaries ORDER BY id') as $row) { $fields=json_decode((string)$row['fields'],true)?:[]; $gross=(float)($fields['8']??$fields['8Brutto']??0); $stmt->execute([(int)$row['id'],(int)$row['employee_id'],(int)$row['year'],$gross,'Gespeichert','',now(),$row['start']??'',$row['end']??'',$row['fields']??'{}']); $counts['Lohnausweise']++; } }
            $allowedSettings=['company','address','postcode','city','phone','email','website','uid','reminder_text_1','reminder_text_2','reminder_text_3','reminder_text_4'];
            if(source_has_table($source,'settings')) { $stmt=$db->prepare('INSERT INTO app_settings(setting_key,setting_value,updated_at) VALUES(?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at'); foreach(source_rows($source,'SELECT key,value FROM settings') as $row) if(in_array($row['key'],$allowedSettings,true)) $stmt->execute([$row['key'],$row['value'],now()]); }
            $db->commit(); bump_revision($db); audit($db,(int)$user['id'],'desktop_backup_imported',json_encode($counts,JSON_UNESCAPED_UNICODE));
            set_flash('success','Desktop-Sicherung importiert: '.implode(' · ',array_map(fn($key,$value)=>$key.' '.$value,array_keys($counts),$counts)).'.');
        } catch(Throwable $exception) { if($db->inTransaction()) $db->rollBack(); set_flash('error','Import nicht durchgeführt: '.$exception->getMessage()); }
        finally { @unlink($importPath); }
        redirect('/?page=settings');
    }

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
$employees=$invoices=$reminders=$timeEntries=$certificates=$applications=$salaryRows=[]; $appSettings=[];
if ($user) {
    $employees=$db->query('SELECT * FROM employees WHERE active=1 ORDER BY last_name,first_name')->fetchAll();
    if ($page==='dashboard') {
        $dashboardOpen=(float)$db->query('SELECT COALESCE(SUM(MAX(amount-paid_amount,0)),0) FROM invoices')->fetchColumn();
        $dashboardOverdue=(int)$db->query("SELECT COUNT(*) FROM invoices WHERE amount>paid_amount AND due_date<date('now')")->fetchColumn();
        $dashboardApplications=(int)$db->query("SELECT COUNT(*) FROM applications WHERE rating='Offen'")->fetchColumn();
    }
    if ($page==='invoices') $invoices=$db->query('SELECT *,MAX(amount-paid_amount,0) AS open_amount FROM invoices ORDER BY invoice_date DESC,id DESC')->fetchAll();
    if ($page==='reminders') $reminders=$db->query('SELECT * FROM reminders ORDER BY reminder_date DESC,id DESC')->fetchAll();
    if ($page==='timesheets') $timeEntries=$db->query('SELECT t.*,e.first_name||\' \'||e.last_name AS employee_name FROM time_entries t JOIN employees e ON e.id=t.employee_id ORDER BY t.work_date DESC,t.id DESC LIMIT 120')->fetchAll();
    if ($page==='certificates') $certificates=$db->query('SELECT c.*,e.first_name||\' \'||e.last_name AS employee_name FROM certificates c JOIN employees e ON e.id=c.employee_id ORDER BY c.reference_date DESC,c.id DESC')->fetchAll();
    if ($page==='applications') $applications=$db->query('SELECT * FROM applications ORDER BY received_date DESC,id DESC')->fetchAll();
    if ($page==='salary') $salaryRows=$db->query('SELECT s.*,e.first_name||\' \'||e.last_name AS employee_name FROM salary_certificates s JOIN employees e ON e.id=s.employee_id ORDER BY s.tax_year DESC,e.last_name')->fetchAll();
    if ($page==='settings') { foreach($db->query('SELECT setting_key,setting_value FROM app_settings') as $row) $appSettings[$row['setting_key']]=$row['setting_value']; }
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
.workspace{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(320px,.65fr);gap:20px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 13px}.field.wide{grid-column:1/-1}.input[type=number]{appearance:textfield}.empty-state{padding:45px 20px;text-align:center;color:var(--muted)}.empty-state strong{display:block;color:var(--ink);margin-bottom:5px}.pill{display:inline-flex;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:750;background:#edf4f5;color:#506a74}.pill.green{background:#ddf4e9;color:#13704e}.pill.yellow{background:#fff2c8;color:#815c0d}.pill.red{background:#fde2e2;color:#9a3838}.pill.blue{background:#e3effb;color:#31668f}.amount{font-variant-numeric:tabular-nums;white-space:nowrap}.toolbar-note{font-size:12px;color:var(--muted)}textarea.input{resize:vertical;min-height:86px}.readonly-note{border-left:4px solid #6ab8a8;padding:12px 14px;background:#edf8f5;color:#46646b;border-radius:8px;font-size:13px;margin-bottom:18px}.module-link{color:inherit;text-decoration:none}.module-link:hover{transform:translateY(-2px);box-shadow:var(--shadow)}
@media(max-width:1100px){.workspace{grid-template-columns:1fr}}
@media(max-width:760px){.form-grid{grid-template-columns:1fr}.field.wide{grid-column:auto}th,td{padding:12px 11px}}
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
    <a class="nav <?= $page==='invoices'?'active':'' ?>" href="/?page=invoices"><i>▤</i>Debitoren</a><a class="nav <?= $page==='reminders'?'active':'' ?>" href="/?page=reminders"><i>△</i>Mahnungen</a>
    <a class="nav <?= $page==='timesheets'?'active':'' ?>" href="/?page=timesheets"><i>◫</i>Stundennachweis</a><a class="nav <?= $page==='certificates'?'active':'' ?>" href="/?page=certificates"><i>◉</i>Zeugnisse</a>
    <a class="nav <?= $page==='applications'?'active':'' ?>" href="/?page=applications"><i>▰</i>Bewerbungen</a><a class="nav <?= $page==='salary'?'active':'' ?>" href="/?page=salary"><i>◧</i>Lohnausweise</a>
    <a class="nav <?= $page==='settings'?'active':'' ?>" href="/?page=settings"><i>⚙</i>Einstellungen</a>
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
  <?php elseif ($page==='invoices'): ?>
    <div class="top"><div><div class="eyebrow">Finanzen</div><h1>Debitoren</h1><p class="sub">Rechnungen, Zahlungen, offene Beträge und Quartale im Blick behalten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Rechnungen</h2><span class="tag"><?= count($invoices) ?> Einträge</span></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Rechnung</th><th>Kunde</th><th>Datum</th><th>Quartal</th><th>Betrag</th><th>Offen</th><th>Status</th></tr></thead><tbody><?php foreach($invoices as $row): $open=(float)$row['open_amount']; ?><tr><td><strong><?= e($row['invoice_number']) ?></strong><br><span class="hint"><?= e($row['notes']) ?></span></td><td><?= e($row['customer']) ?></td><td><?= e(date('d.m.Y',strtotime($row['invoice_date']))) ?></td><td>Q<?= (int)ceil((int)date('n',strtotime($row['invoice_date']))/3) ?></td><td class="amount"><?= e(money((float)$row['amount'])) ?></td><td class="amount"><?= e(money($open)) ?></td><td><span class="pill <?= $open>0?'yellow':'green' ?>"><?= $open>0?'Offen':'Bezahlt' ?></span></td></tr><?php endforeach; ?><?php if(!$invoices): ?><tr><td colspan="7" class="empty-state"><strong>Noch keine Rechnungen</strong>Erfasse rechts die erste Rechnung.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section class="card form-card"><h2>Neue Rechnung</h2><p class="sub">Die Quartalsspalte wird automatisch aus dem Rechnungsdatum berechnet.</p><?php if(!can_write($user)): ?><div class="readonly-note">Mit deiner Rolle kannst du Rechnungen ansehen, aber nicht verändern.</div><?php else: ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_invoice"><div class="form-grid"><div class="field"><label>Rechnungsnummer</label><input class="input" name="invoice_number" required></div><div class="field"><label>Kunde</label><input class="input" name="customer" required></div><div class="field"><label>Rechnungsdatum</label><input class="input" type="date" name="invoice_date" value="<?= date('Y-m-d') ?>" required></div><div class="field"><label>Fällig am</label><input class="input" type="date" name="due_date" required></div><div class="field"><label>Betrag CHF</label><input class="input" inputmode="decimal" name="amount" placeholder="0.00" required></div><div class="field"><label>Bereits bezahlt CHF</label><input class="input" inputmode="decimal" name="paid_amount" value="0.00"></div><div class="field wide"><label>Bemerkung</label><textarea class="input" name="notes"></textarea></div></div><button class="btn" type="submit">Rechnung speichern</button></form><?php endif; ?></section></div>
  <?php elseif ($page==='reminders'): ?>
    <div class="top"><div><div class="eyebrow">Debitoren</div><h1>Mahnungen</h1><p class="sub">Zahlungserinnerungen und vier Mahnstufen zentral vorbereiten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Mahnübersicht</h2><span class="tag"><?= count($reminders) ?> Entwürfe</span></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Datum</th><th>Empfänger</th><th>Rechnung</th><th>Stufe</th><th>Betrag</th><th>Status</th></tr></thead><tbody><?php $levels=[1=>'Zahlungserinnerung',2=>'Mahnung 1',3=>'Mahnung 2',4=>'Betreibung']; foreach($reminders as $row): ?><tr><td><?= e(date('d.m.Y',strtotime($row['reminder_date']))) ?></td><td><?= e($row['customer']) ?></td><td><?= e($row['invoice_number']) ?></td><td><?= e($levels[(int)$row['level']]) ?></td><td class="amount"><?= e(money((float)$row['amount'])) ?></td><td><span class="pill blue"><?= e($row['status']) ?></span></td></tr><?php endforeach; ?><?php if(!$reminders): ?><tr><td colspan="6" class="empty-state"><strong>Noch keine Mahnungen</strong>Erstelle rechts den ersten Entwurf.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section class="card form-card"><h2>Mahnung vorbereiten</h2><p class="sub">Die Ausgabe als gestalteter Brief wird im nächsten Ausbauschritt ergänzt.</p><?php if(can_write($user)): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_reminder"><div class="field"><label>Empfänger</label><input class="input" name="customer" required></div><div class="form-grid"><div class="field"><label>Rechnungsnummer</label><input class="input" name="invoice_number"></div><div class="field"><label>Betrag CHF</label><input class="input" inputmode="decimal" name="amount"></div><div class="field"><label>Mahnstufe</label><select class="input" name="level"><option value="1">Zahlungserinnerung</option><option value="2">Mahnung 1</option><option value="3">Mahnung 2</option><option value="4">Betreibung</option></select></div><div class="field"><label>Datum</label><input class="input" type="date" name="reminder_date" value="<?= date('Y-m-d') ?>" required></div><div class="field wide"><label>Mahntext</label><textarea class="input" name="reminder_text" placeholder="Die Variablen und Vorlagen werden beim Dokumentexport ergänzt."></textarea></div></div><button class="btn" type="submit">Entwurf speichern</button></form><?php else: ?><div class="readonly-note">Nur lesender Zugriff.</div><?php endif; ?></section></div>
  <?php elseif ($page==='timesheets'): ?>
    <div class="top"><div><div class="eyebrow">Personal</div><h1>Stundennachweis</h1><p class="sub">Arbeitszeit und Abwesenheitsgründe in Dezimalstunden erfassen.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Letzte Einträge</h2><span class="tag"><?= count($employees) ?> Personen</span></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Datum</th><th>Person</th><th>Stunden</th><th>Grund</th><th>Bemerkung</th></tr></thead><tbody><?php foreach($timeEntries as $row): ?><tr><td><?= e(date('d.m.Y',strtotime($row['work_date']))) ?></td><td><?= e($row['employee_name']) ?></td><td class="amount"><?= e(number_format((float)$row['hours'],2,'.','')) ?> h</td><td><span class="pill <?= $row['reason']==='Arbeit'?'green':'yellow' ?>"><?= e($row['reason']) ?></span></td><td><?= e($row['notes']) ?></td></tr><?php endforeach; ?><?php if(!$timeEntries): ?><tr><td colspan="5" class="empty-state"><strong>Noch keine Zeiteinträge</strong>Lege zuerst eine Person und danach einen Arbeitstag an.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section><div class="card form-card"><h2>Arbeitszeit erfassen</h2><?php if(can_write($user) && $employees): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_time"><div class="field"><label>Person</label><select class="input" name="employee_id"><?php foreach($employees as $row): ?><option value="<?= (int)$row['id'] ?>"><?= e($row['first_name'].' '.$row['last_name']) ?></option><?php endforeach; ?></select></div><div class="form-grid"><div class="field"><label>Datum</label><input class="input" type="date" name="work_date" value="<?= date('Y-m-d') ?>" required></div><div class="field"><label>Stunden</label><input class="input" inputmode="decimal" name="hours" placeholder="8.75" required></div><div class="field wide"><label>Grund</label><select class="input" name="reason"><option>Arbeit</option><option>Ferien</option><option>Krankheit</option><option>Unfall</option><option>Begründete Minderzeit</option></select></div><div class="field wide"><label>Bemerkung</label><textarea class="input" name="notes"></textarea></div></div><button class="btn" type="submit">Zeit speichern</button></form><?php elseif(!$employees): ?><div class="readonly-note">Erfasse zuerst unten eine Person.</div><?php else: ?><div class="readonly-note">Nur lesender Zugriff.</div><?php endif; ?></div>
    <?php if(can_write($user)): ?><div class="card form-card" style="margin-top:18px"><h2>Person hinzufügen</h2><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_employee"><div class="form-grid"><div class="field"><label>Vorname</label><input class="input" name="first_name" required></div><div class="field"><label>Nachname</label><input class="input" name="last_name" required></div><div class="field"><label>Personal-Nr.</label><input class="input" name="personnel_number"></div><div class="field"><label>Personengruppe</label><select class="input" name="employee_type"><option value="employee">Mitarbeiter</option><option value="apprentice">Lernender</option></select></div><div class="field wide"><label>Eintritt</label><input class="input" type="date" name="entry_date"></div></div><button class="btn secondary" type="submit">Person speichern</button></form></div><?php endif; ?></section></div>
  <?php elseif ($page==='certificates'): ?>
    <div class="top"><div><div class="eyebrow">Personal</div><h1>Zeugnisse</h1><p class="sub">Arbeits-, Zwischen- und Lehrzeugnisse als Vorgang vorbereiten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Zeugnisvorgänge</h2></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Person</th><th>Zeugnisart</th><th>Stichtag</th><th>Status</th><th>Notiz</th></tr></thead><tbody><?php foreach($certificates as $row): ?><tr><td><?= e($row['employee_name']) ?></td><td><?= e($row['certificate_type']) ?></td><td><?= e(date('d.m.Y',strtotime($row['reference_date']))) ?></td><td><span class="pill blue"><?= e($row['status']) ?></span></td><td><?= e($row['notes']) ?></td></tr><?php endforeach; ?><?php if(!$certificates): ?><tr><td colspan="5" class="empty-state"><strong>Noch keine Zeugnisse</strong>Lege rechts den ersten Vorgang an.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section class="card form-card"><h2>Zeugnis anlegen</h2><p class="sub">Der geführte Multiple-Choice-Textgenerator wird auf diesen Vorgängen aufgebaut.</p><?php if(can_write($user) && $employees): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_certificate"><div class="field"><label>Person</label><select class="input" name="employee_id"><?php foreach($employees as $row): ?><option value="<?= (int)$row['id'] ?>"><?= e($row['first_name'].' '.$row['last_name']) ?></option><?php endforeach; ?></select></div><div class="field"><label>Zeugnisart</label><select class="input" name="certificate_type"><option>Arbeitszeugnis</option><option>Zwischenzeugnis</option><option>Lehrzeugnis</option></select></div><div class="field"><label>Stichtag</label><input class="input" type="date" name="reference_date" value="<?= date('Y-m-d') ?>" required></div><div class="field"><label>Interne Notiz</label><textarea class="input" name="notes"></textarea></div><button class="btn" type="submit">Vorgang anlegen</button></form><?php else: ?><div class="readonly-note"><?= !$employees?'Zuerst im Stundennachweis eine Person anlegen.':'Nur lesender Zugriff.' ?></div><?php endif; ?></section></div>
  <?php elseif ($page==='applications'): ?>
    <div class="top"><div><div class="eyebrow">Nachwuchs</div><h1>Bewerbungen</h1><p class="sub">Jede Bewerbung als übersichtliches Dossier mit Beurteilung führen.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Bewerbungsdossiers</h2><span class="toolbar-note">Serverimport wird separat verbunden</span></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Eingang</th><th>Name</th><th>Bewerbung für</th><th>Kontakt</th><th>Beurteilung</th></tr></thead><tbody><?php foreach($applications as $row): $ratingClass=['Nicht geeignet'=>'red','Eventuell'=>'yellow','Geeignet'=>'green','Offen'=>'blue'][$row['rating']]??'blue'; ?><tr><td><?= e(date('d.m.Y',strtotime($row['received_date']))) ?></td><td><strong><?= e($row['applicant_name']) ?></strong><br><span class="hint"><?= e($row['source']) ?></span></td><td><?= e($row['application_type']) ?></td><td><?= e($row['email']) ?><br><span class="hint"><?= e($row['phone']) ?></span></td><td><span class="pill <?= $ratingClass ?>"><?= e($row['rating']) ?></span><?php if(can_write($user)): ?><form method="post" style="margin-top:8px"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="rate_application"><input type="hidden" name="application_id" value="<?= (int)$row['id'] ?>"><select class="input" name="rating" style="padding:7px"><option>Offen</option><option>Nicht geeignet</option><option>Eventuell</option><option>Geeignet</option></select><input class="input" name="notes" value="<?= e($row['notes']) ?>" placeholder="Notiz" style="padding:7px;margin-top:5px"><button class="mini" type="submit" style="margin-top:5px">Speichern</button></form><?php endif; ?></td></tr><?php endforeach; ?><?php if(!$applications): ?><tr><td colspan="5" class="empty-state"><strong>Noch keine Bewerbungen</strong>Eine Bewerbung kann rechts manuell erfasst werden.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section class="card form-card"><h2>Manuell erfassen</h2><p class="sub">Stammdaten bleiben danach unverändert; nur Beurteilung und Notiz werden weitergeführt.</p><?php if(can_write($user)): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_application"><div class="field"><label>Name</label><input class="input" name="applicant_name" required></div><div class="form-grid"><div class="field"><label>E-Mail</label><input class="input" type="email" name="email"></div><div class="field"><label>Telefon</label><input class="input" name="phone"></div><div class="field wide"><label>Bewerbung für</label><select class="input" name="application_type"><option>Schnupperlehre</option><option>Montage-Elektriker EFZ</option><option>Elektroinstallateur EFZ</option></select></div><div class="field wide"><label>Eingang</label><input class="input" type="date" name="received_date" value="<?= date('Y-m-d') ?>" required></div><div class="field wide"><label>Notiz</label><textarea class="input" name="notes"></textarea></div></div><button class="btn" type="submit">Bewerbung erfassen</button></form><?php else: ?><div class="readonly-note">Nur lesender Zugriff.</div><?php endif; ?></section></div>
  <?php elseif ($page==='salary'): ?>
    <div class="top"><div><div class="eyebrow">Personal</div><h1>Lohnausweise</h1><p class="sub">Lohnausweise pro Person und Steuerjahr vorbereiten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section><div class="section-head"><h2>Ausweise</h2></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Jahr</th><th>Person</th><th>Bruttolohn</th><th>Status</th><th>Notiz</th></tr></thead><tbody><?php foreach($salaryRows as $row): ?><tr><td><strong><?= (int)$row['tax_year'] ?></strong></td><td><?= e($row['employee_name']) ?></td><td class="amount"><?= e(money((float)$row['gross_salary'])) ?></td><td><span class="pill blue"><?= e($row['status']) ?></span></td><td><?= e($row['notes']) ?></td></tr><?php endforeach; ?><?php if(!$salaryRows): ?><tr><td colspan="5" class="empty-state"><strong>Noch keine Lohnausweise</strong>Lege rechts einen neuen Entwurf an.</td></tr><?php endif; ?></tbody></table></div></div></section>
    <section class="card form-card"><h2>Neuer Lohnausweis</h2><p class="sub">Die offizielle PDF-Vorlage wird im nächsten Ausbauschritt serverseitig ausgefüllt.</p><?php if(can_write($user) && $employees): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_salary"><div class="field"><label>Person</label><select class="input" name="employee_id"><?php foreach($employees as $row): ?><option value="<?= (int)$row['id'] ?>"><?= e($row['first_name'].' '.$row['last_name']) ?></option><?php endforeach; ?></select></div><div class="form-grid"><div class="field"><label>Steuerjahr</label><input class="input" type="number" name="tax_year" value="<?= date('Y') ?>" min="2000" max="2100"></div><div class="field"><label>Bruttolohn CHF</label><input class="input" inputmode="decimal" name="gross_salary"></div><div class="field wide"><label>Notiz</label><textarea class="input" name="notes"></textarea></div></div><button class="btn" type="submit">Entwurf anlegen</button></form><?php else: ?><div class="readonly-note"><?= !$employees?'Zuerst im Stundennachweis eine Person anlegen.':'Nur lesender Zugriff.' ?></div><?php endif; ?></section></div>
  <?php elseif ($page==='settings'): ?>
    <div class="top"><div><div class="eyebrow">Konfiguration</div><h1>Einstellungen</h1><p class="sub">Zentrale Firmen- und Webeinstellungen verwalten.</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?><div class="workspace"><section class="card form-card"><h2>Firmendaten</h2><p class="sub">Diese Angaben werden für Mahnungen, Zeugnisse und Exporte verwendet.</p><?php if(can_write($user)): ?><form method="post"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="save_settings"><div class="field"><label>Firmenname</label><input class="input" name="company_name" value="<?= e($appSettings['company_name']??$appSettings['company']??'AST Elektro Tüscher AG') ?>"></div><div class="field"><label>Adresse</label><input class="input" name="company_address" value="<?= e($appSettings['company_address']??$appSettings['address']??'') ?>"></div><div class="field"><label>PLZ und Ort</label><input class="input" name="company_postcode_city" value="<?= e($appSettings['company_postcode_city']??trim(($appSettings['postcode']??'').' '.($appSettings['city']??''))) ?>"></div><div class="form-grid"><div class="field"><label>Telefon</label><input class="input" name="company_phone" value="<?= e($appSettings['company_phone']??$appSettings['phone']??'') ?>"></div><div class="field"><label>E-Mail</label><input class="input" type="email" name="company_email" value="<?= e($appSettings['company_email']??$appSettings['email']??'') ?>"></div></div><button class="btn" type="submit">Einstellungen speichern</button></form><?php else: ?><div class="readonly-note">Nur lesender Zugriff.</div><?php endif; ?></section><section class="card"><h2>Gemeinsamer Datenstand</h2><p class="sub">Eine Desktop-Sicherung kann als vollständiger Ausgangsstand übernommen werden.</p><?php if($user['role']==='admin'): ?><form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="<?= e(csrf()) ?>"><input type="hidden" name="action" value="import_backup"><div class="field"><label>AST-Sicherung auswählen</label><input class="input" type="file" name="backup_file" accept=".sqlite3,.db" required><span class="hint">Übernimmt Fachdaten und Stammdaten. Web-Benutzerkonten bleiben unverändert. Vorher wird automatisch eine Web-Sicherung erstellt.</span></div><button class="btn" type="submit">Desktop-Sicherung importieren</button></form><hr style="border:0;border-top:1px solid var(--line);margin:24px 0"><a class="btn secondary" href="/?page=users">Benutzerverwaltung öffnen</a><?php else: ?><div class="readonly-note">Sicherungsimporte sind Administratoren vorbehalten.</div><?php endif; ?></section></div>
  <?php else: ?>
    <div class="top"><div><div class="eyebrow">Übersicht</div><h1>Guten Tag, <?= e(explode(' ',trim($user['name']))[0]) ?></h1><p class="sub">Was möchtest du heute erledigen?</p></div><div class="profile"><div class="avatar"><?= e(initials($user['name'])) ?></div><div><strong><?= e($user['name']) ?></strong><small><?= e(role_name($user['role'])) ?></small></div></div></div>
    <?php if ($flash): ?><div class="alert <?= e($flash[0]) ?>"><?= e($flash[1]) ?></div><?php endif; ?>
    <section class="card hero"><h2>Die Webmodule sind bereit</h2><p>Alle Bereiche verwenden dieselbe geschützte Datenbank und berücksichtigen deine Benutzerrolle.</p></section>
    <section class="stats"><div class="card stat"><div class="label">Offene Rechnungen</div><strong><?= e(money($dashboardOpen??0)) ?></strong><small>Aktueller offener Betrag</small></div><div class="card stat"><div class="label">Überfällige Rechnungen</div><strong><?= (int)($dashboardOverdue??0) ?></strong><small>Fälligkeit überschritten</small></div><div class="card stat"><div class="label">Offene Bewerbungen</div><strong><?= (int)($dashboardApplications??0) ?></strong><small>Noch nicht beurteilt</small></div><div class="card stat"><div class="label">Aktive Personen</div><strong><?= count($employees) ?></strong><small>Mitarbeitende und Lernende</small></div></section>
    <div class="section-head"><h2>Arbeitsbereiche</h2></div><section class="module-grid"><?php foreach([['▤','Debitoren','invoices'],['◫','Stundennachweis','timesheets'],['▰','Bewerbungen','applications'],['◉','Zeugnisse','certificates']] as [$icon,$name,$route]): ?><a class="card module module-link" href="/?page=<?= e($route) ?>"><div class="module-icon"><?= $icon ?></div><h3><?= e($name) ?></h3><p>Webbereich öffnen und zentral bearbeiten.</p><span class="tag">Bereit</span></a><?php endforeach; ?></section>
  <?php endif; ?>
</main></div>
<?php endif; ?>
</body></html>
