<?php
error_reporting(0);
ini_set('display_errors', 0);
header('Content-Type: application/json');

// --- TEIL 1: LENA ABFRAGE ---
if (isset($_GET['action']) && $_GET['action'] === 'getLehrstellen') {
    $stellen = ["Elektroinstallateur/in EFZ" => 0, "Montage-Elektriker/in EFZ" => 0];

    // Wir prüfen das aktuelle, nächste und übernächste Jahr automatisch
    $currentYear = (int)date('Y');
    $yearsToCheck = [$currentYear, $currentYear + 1, $currentYear + 2];

    foreach ($yearsToCheck as $year) {
        $url = "https://www.ag.ch/de/themen/bildung-forschung/berufsbildung/lehre/lehrstellennachweis-lena/offene-lehrstellen?job=&company=AST+Elektro+T%C3%BCscher+AG&place=0&distance=&distance=&year={$year}&graduation=0&_vocational=on&_sportFriendly=on&vacant=active&_vacant=on&search=true&submit=Suchen&jumpto=accordion__header--null--0";

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
        $html = curl_exec($ch);
        curl_close($ch);

        if ($html) {
            libxml_use_internal_errors(true);
            $doc = new DOMDocument();
            $doc->loadHTML(mb_convert_encoding($html, 'HTML-ENTITIES', 'UTF-8'));
            $xpath = new DOMXPath($doc);

            foreach ($xpath->query('//tr') as $row) {
                $rowText = $row->textContent;
                if (strpos($rowText, 'Elektroinstallateur/-in EFZ') !== false || strpos($rowText, 'Montage-Elektriker/-in EFZ') !== false) {
                    $key = strpos($rowText, 'Elektroinstallateur') !== false ? "Elektroinstallateur/in EFZ" : "Montage-Elektriker/in EFZ";
                    foreach ($xpath->query('.//td', $row) as $col) {
                        $val = trim($col->textContent);
                        if (preg_match('/^\d+$/', $val)) {
                            // Addiere die gefundenen Stellen zu den bisherigen
                            $stellen[$key] += intval($val);
                            break;
                        }
                    }
                }
            }
        }
    }

    echo json_encode(["success" => true, "data" => $stellen]);
    exit;
}

// --- TEIL 2: MAIL VERSAND & GEO-IP FILTER ---
if ($_SERVER["REQUEST_METHOD"] === "POST") {

    // ==========================================
    // SPAM-SCHUTZ: NUR SCHWEIZER IP-ADRESSEN ZULASSEN (JETZT MIT cURL)
    // ==========================================
    $client_ip = $_SERVER['REMOTE_ADDR'];
    $is_swiss_ip = false;

    if ($client_ip === '127.0.0.1' || $client_ip === '::1') {
        $is_swiss_ip = true;
    } else {
        // Robuste cURL Abfrage für die IP
        $api_url = "http://ip-api.com/json/{$client_ip}?fields=countryCode";
        $ch_ip = curl_init();
        curl_setopt($ch_ip, CURLOPT_URL, $api_url);
        curl_setopt($ch_ip, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch_ip, CURLOPT_TIMEOUT, 3); // 3 Sekunden Timeout
        $response = curl_exec($ch_ip);
        curl_close($ch_ip);

        if ($response) {
            $data = json_decode($response, true);
            if (isset($data['countryCode']) && $data['countryCode'] === 'CH') {
                $is_swiss_ip = true;
            }
        } else {
            // Fallback bleibt bestehen, falls API down ist
            $is_swiss_ip = true;
        }
    }

    if (!$is_swiss_ip) {
        echo json_encode([
            "success" => false,
            "message" => "Error405: You are not allowed to do this. (#php.error.000156)."
        ]);
        exit;
    }
    // ==========================================

    $form_type = $_POST["form_type"] ?? "Allgemeine Anfrage";
    $name = htmlspecialchars($_POST["name"] ?? $_POST['Familienname'] ?? "");
    $vorname = htmlspecialchars($_POST["vorname"] ?? "");
    $email = htmlspecialchars($_POST["email"] ?? $_POST['E-Mail'] ?? "");
    $telefon = htmlspecialchars($_POST["telefon"] ?? $_POST['Telefon'] ?? "");
    $nachricht = htmlspecialchars($_POST["nachricht"] ?? $_POST['Bemerkung_Kunde'] ?? "");
    $bewerbung_fuer = htmlspecialchars($_POST["bewerbung_fuer"] ?? "-");
    $berufsmatura = isset($_POST["berufsmatura"]) && ($_POST["berufsmatura"] === "Ja" || $_POST["berufsmatura"] === "on") ? "ja" : "nein";

    $uploadOrdner = "uploads/";
    if (!is_dir($uploadOrdner)) mkdir($uploadOrdner, 0777, true);
    $baseUrl = "https://" . $_SERVER['HTTP_HOST'] . rtrim(dirname($_SERVER['PHP_SELF']), '/\\') . "/" . $uploadOrdner;

    $angehaengte_dateien = [];
    $application_files = [];
    $links = ['bewerbung' => [], 'lebenslauf' => [], 'zeugnisse' => [], 'sonstige' => [], 'anhang' => []];

    function process($fileArray, $folder, $base, &$attach, &$links_arr, &$records, $category) {
        if (!$fileArray) return;
        $files = is_array($fileArray['name']) ? $fileArray : ['name'=>[$fileArray['name']],'tmp_name'=>[$fileArray['tmp_name']],'error'=>[$fileArray['error']],'size'=>[$fileArray['size']]];
        for ($i=0; $i<count($files['name']); $i++) {
            if ($files['error'][$i] === 0 && $files['size'][$i] <= 15728640) {
                $ext = strtolower(pathinfo($files['name'][$i], PATHINFO_EXTENSION));
                $fname = uniqid("upload_") . "." . $ext;
                if (move_uploaded_file($files['tmp_name'][$i], $folder . $fname)) {
                    $attach[] = $folder . $fname;
                    $links_arr[] = $base . $fname;
                    $records[] = [
                        'category' => $category,
                        'original_name' => basename($files['name'][$i]),
                        'stored_path' => '../ast-elektro.ch/' . $folder . $fname,
                        'url' => $base . $fname
                    ];
                }
            }
        }
    }

    process($_FILES['bewerbung'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['bewerbung'], $application_files, 'application');
    process($_FILES['lebenslauf'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['lebenslauf'], $application_files, 'cv');
    process($_FILES['zeugnisse'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['zeugnisse'], $application_files, 'certificates');
    process($_FILES['sonstige'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['sonstige'], $application_files, 'other');
    process($_FILES['anhang'] ?? $_FILES['anhang_chatbot'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['anhang'], $application_files, 'other');

    $empfaenger = ($form_type === "lehrstelle") ? "manuel.tuescher@ast-elektro.ch" : "info@ast-elektro.ch";
    $betreff = "Neue Website-Anfrage ($form_type) von $vorname $name";

    if (in_array($form_type, ["lehrstelle", "bewerbung", "Spontanbewerbung"])) {
        $email_text = "Name: $name\nVorname: $vorname\nStrasse/Nr: ".($_POST['strasse']??'')." ".($_POST['hausnummer']??'')."\nPLZ/Ort: ".($_POST['plz']??'')." ".($_POST['ort']??'')."\nE-Mail: $email\nTelefon: $telefon\nNachricht: $nachricht\nBewerbung für: $bewerbung_fuer\nZusatz: $berufsmatura\n\n";
        $email_text .= "1. Motivationsschreiben: " . (!empty($links['bewerbung']) ? implode(", ", $links['bewerbung']) : "-") . "\n";
        $email_text .= "2. Lebenslauf: " . (!empty($links['lebenslauf']) ? implode(", ", $links['lebenslauf']) : "-") . "\n";
        $email_text .= "3. Zeugnisse: " . (!empty($links['zeugnisse']) ? implode(", ", $links['zeugnisse']) : "-") . "\n";
        $email_text .= "4. Sonstiges: " . (!empty($links['sonstige']) ? implode(", ", $links['sonstige']) : "-") . "\n";
    } else {
        $email_text = "Nachricht von $vorname $name ($email):\n$nachricht\n\nDateien: " . (!empty($links['anhang']) ? implode(", ", $links['anhang']) : "-");
    }

    $email_text .= "\n---\nDatum: ".date("d.m.Y H:i")."\nIP: ".$_SERVER['REMOTE_ADDR'];

    require 'PHPMailer/Exception.php'; require 'PHPMailer/PHPMailer.php'; require 'PHPMailer/SMTP.php';
    $mail = new PHPMailer\PHPMailer\PHPMailer(true);
    try {
        $mail->isSMTP(); $mail->Host = 'mail.infomaniak.com'; $mail->SMTPAuth = true;

        $mail->Username = 'info@ast-elektro.ch';
        // WICHTIG: Setze hier das Passwort (oder ggf. das Infomaniak App-Passwort) wieder ein!
        $mail->Password = 'TEST_ONLY';

        $mail->SMTPSecure = 'ssl'; $mail->Port = 465; $mail->CharSet = 'UTF-8';
        $mail->setFrom('info@ast-elektro.ch', 'AST Elektro Website');
        $mail->addAddress($empfaenger); $mail->addReplyTo($email, "$vorname $name");
        $mail->Subject = $betreff; $mail->Body = $email_text;
        foreach ($angehaengte_dateien as $f) $mail->addAttachment($f);
        $mail->send();
        if ($form_type === "lehrstelle") {
            // Stored outside the public web root. AST reads this folder over the existing SMB share.
            $manifest_dir = dirname(__DIR__) . DIRECTORY_SEPARATOR . "private_applications";
            if (!is_dir($manifest_dir)) mkdir($manifest_dir, 0770, true);
            $application_id = date("YmdHis") . "_" . bin2hex(random_bytes(6));
            $plain = static function ($value) {
                return trim(html_entity_decode((string)$value, ENT_QUOTES | ENT_HTML5, "UTF-8"));
            };
            $manifest = [
                "id" => $application_id,
                "submitted_at" => date(DATE_ATOM),
                "application_for" => $plain($bewerbung_fuer),
                "first_name" => $plain($vorname),
                "last_name" => $plain($name),
                "address" => trim($plain($_POST["strasse"] ?? "") . " " . $plain($_POST["hausnummer"] ?? "")),
                "postcode" => $plain($_POST["plz"] ?? ""),
                "city" => $plain($_POST["ort"] ?? ""),
                "email" => $plain($email),
                "phone" => $plain($telefon),
                "vocational_baccalaureate" => $berufsmatura,
                "message" => $plain($nachricht),
                "files" => $application_files
            ];
            $manifest_path = $manifest_dir . DIRECTORY_SEPARATOR . $application_id . ".json";
            if (file_put_contents($manifest_path, json_encode($manifest, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX) === false) {
                error_log("Bewerbungsmanifest konnte nicht gespeichert werden: " . $manifest_path);
            }
        }
        echo json_encode(["success" => true]);
    } catch (Exception $e) { echo json_encode(["success" => false, "message" => "SMTP Error: Could not authenticate."]); }
}
?>
