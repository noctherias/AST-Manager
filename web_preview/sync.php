<?php
declare(strict_types=1);
require __DIR__.'/config.php';
header('Content-Type: application/json; charset=utf-8'); header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff'); header('X-Frame-Options: DENY');

$db=new PDO('sqlite:'.__DIR__.'/storage/ast-manager.sqlite3',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
$db->exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=10000;');
$email=mb_strtolower(trim((string)($_SERVER['PHP_AUTH_USER']??''))); $password=(string)($_SERVER['PHP_AUTH_PW']??'');
if($email==='' && isset($_SERVER['HTTP_AUTHORIZATION']) && str_starts_with($_SERVER['HTTP_AUTHORIZATION'],'Basic ')) {
    $decoded=base64_decode(substr($_SERVER['HTTP_AUTHORIZATION'],6),true); if($decoded!==false) [$email,$password]=array_pad(explode(':',$decoded,2),2,'');
}
$ipHash=hash('sha256',($_SERVER['REMOTE_ADDR']??'unknown').AST_LOGIN_PEPPER);
$emailHash=hash('sha256',$email.AST_LOGIN_PEPPER);
$cutoff=gmdate('Y-m-d\TH:i:s\Z',time()-900);
$db->prepare('DELETE FROM login_attempts WHERE attempted_at<?')->execute([gmdate('Y-m-d\TH:i:s\Z',time()-86400)]);
$attempt=$db->prepare('SELECT COUNT(*) FROM login_attempts WHERE successful=0 AND attempted_at>=? AND (ip_hash=? OR email_hash=?)');
$attempt->execute([$cutoff,$ipHash,$emailHash]);
if((int)$attempt->fetchColumn()>=8) { http_response_code(429); header('Retry-After: 900'); echo json_encode(['error'=>'Zu viele Anmeldeversuche. Bitte später erneut versuchen.']); exit; }
$stmt=$db->prepare('SELECT * FROM users WHERE email=? AND active=1'); $stmt->execute([$email]); $user=$stmt->fetch();
if(!$user || !password_verify($password,$user['password_hash'])) {
    $db->prepare('INSERT INTO login_attempts(ip_hash,email_hash,attempted_at,successful) VALUES(?,?,?,0)')->execute([$ipHash,$emailHash,gmdate('c')]);
    header('WWW-Authenticate: Basic realm="AST Manager Sync"'); http_response_code(401); echo json_encode(['error'=>'Anmeldung fehlgeschlagen.']); exit;
}
$db->prepare('INSERT INTO login_attempts(ip_hash,email_hash,attempted_at,successful) VALUES(?,?,?,1)')->execute([$ipHash,$emailHash,gmdate('c')]);
if(!in_array($user['role'],['admin','management'],true)) { http_response_code(403); echo json_encode(['error'=>'Keine Synchronisationsberechtigung.']); exit; }

$tables=[
 'customers'=>['id','name','customer_number','address','postcode','city','email','created_at','updated_at'],
 'employees'=>['id','first_name','last_name','personnel_number','employee_type','entry_date','vacation_hours','active','created_at','updated_at','salutation','ahv','ahv_old','birth_date','address','postcode','city','job','workload'],
 'invoices'=>['id','invoice_number','customer','invoice_date','due_date','amount','paid_amount','notes','created_at','updated_at'],
 'invoice_payments'=>['id','invoice_id','payment_date','amount','notes','created_at'],
 'reminders'=>['id','invoice_id','customer','invoice_number','level','amount','reminder_date','reminder_text','status','created_at'],
 'time_entries'=>['id','employee_id','work_date','hours','reason','notes','created_at'],
 'certificates'=>['id','employee_id','certificate_type','reference_date','status','notes','created_at','reason','tasks','ratings','generated_text'],
 'applications'=>['id','applicant_name','email','phone','application_type','received_date','rating','notes','source','created_at','first_name','last_name','address','postcode','city','status','trial_dates','vocational_baccalaureate','message','server_deleted'],
 'application_files'=>['id','application_id','category','original_name','source_ref','created_at'],
 'salary_certificates'=>['id','employee_id','tax_year','gross_salary','status','notes','created_at','period_start','period_end','fields_json'],
 'app_settings'=>['setting_key','setting_value','updated_at'],
 'reminder_templates'=>['level','title','body','updated_at']
];
$revision=(int)$db->query('SELECT revision FROM sync_state WHERE id=1')->fetchColumn();
if($_SERVER['REQUEST_METHOD']==='GET') {
    $result=[]; foreach($tables as $table=>$columns) {
        $sql='SELECT '.implode(',',$columns).' FROM '.$table;
        if($table==='app_settings') $sql.=" WHERE setting_key IN ('company','address','postcode','city','phone','email','website','contact','reminder_text_1','reminder_text_2','reminder_text_3','reminder_text_4')";
        $result[$table]=$db->query($sql)->fetchAll();
    }
    echo json_encode(['schema'=>1,'revision'=>$revision,'generated_at'=>gmdate('c'),'tables'=>$result],JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES); exit;
}
if($_SERVER['REQUEST_METHOD']!=='POST') { http_response_code(405); echo json_encode(['error'=>'Methode nicht erlaubt.']); exit; }
$expected=(int)($_SERVER['HTTP_IF_MATCH']??-1); if($expected!==$revision) { http_response_code(409); echo json_encode(['error'=>'Der Serverdatenstand wurde zwischenzeitlich geändert.','revision'=>$revision]); exit; }
if((int)($_SERVER['CONTENT_LENGTH']??0)>32*1024*1024) { http_response_code(413); echo json_encode(['error'=>'Synchronisationspaket zu gross.']); exit; }
$payload=json_decode((string)file_get_contents('php://input'),true); if(!is_array($payload) || ($payload['schema']??null)!==1 || !is_array($payload['tables']??null)) { http_response_code(400); echo json_encode(['error'=>'Ungültiges Synchronisationspaket.']); exit; }
try {
    $db->beginTransaction();
    foreach(['application_files','invoice_payments','reminders','invoices','time_entries','certificates','salary_certificates','applications','employees','customers','reminder_templates','app_settings'] as $table) $db->exec('DELETE FROM '.$table);
    foreach($tables as $table=>$columns) {
        $rows=$payload['tables'][$table]??[]; if(!is_array($rows)) throw new RuntimeException('Ungültige Tabelle: '.$table);
        if($table==='app_settings') $rows=array_values(array_filter($rows,fn($row)=>is_array($row) && in_array($row['setting_key']??'', ['company','address','postcode','city','phone','email','website','contact','reminder_text_1','reminder_text_2','reminder_text_3','reminder_text_4'],true)));
        $sql='INSERT INTO '.$table.'('.implode(',',$columns).') VALUES('.implode(',',array_fill(0,count($columns),'?')).')'; $stmt=$db->prepare($sql);
        foreach($rows as $row) { if(!is_array($row)) throw new RuntimeException('Ungültiger Datensatz in '.$table); $values=[]; foreach($columns as $column) $values[]=$row[$column]??null; $stmt->execute($values); }
    }
    $newRevision=$revision+1; $db->prepare('UPDATE sync_state SET revision=?,updated_at=? WHERE id=1')->execute([$newRevision,gmdate('c')]);
    $db->prepare('INSERT INTO audit_log(user_id,action,details,created_at) VALUES(?,?,?,?)')->execute([(int)$user['id'],'desktop_sync','Revision '.$newRevision,gmdate('c')]);
    $db->commit(); echo json_encode(['ok'=>true,'revision'=>$newRevision]);
} catch(Throwable $exception) { if($db->inTransaction()) $db->rollBack(); http_response_code(400); echo json_encode(['error'=>'Synchronisation abgelehnt: '.$exception->getMessage()]); }
