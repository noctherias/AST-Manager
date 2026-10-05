"""One-time, reversible integration patch for the AST apprenticeship form.

Usage after explicit approval:
    python tools/enable_website_applications.py /path/to/mailer.php
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import ftplib
import io
import os
from pathlib import Path
import shutil
import ssl
import xml.etree.ElementTree as ET


CALLS = {
    "process($_FILES['bewerbung'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['bewerbung']);":
        "process($_FILES['bewerbung'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['bewerbung'], $application_files, 'application');",
    "process($_FILES['lebenslauf'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['lebenslauf']);":
        "process($_FILES['lebenslauf'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['lebenslauf'], $application_files, 'cv');",
    "process($_FILES['zeugnisse'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['zeugnisse']);":
        "process($_FILES['zeugnisse'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['zeugnisse'], $application_files, 'certificates');",
    "process($_FILES['sonstige'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['sonstige']);":
        "process($_FILES['sonstige'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['sonstige'], $application_files, 'other');",
    "process($_FILES['anhang'] ?? $_FILES['anhang_chatbot'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['anhang']);":
        "process($_FILES['anhang'] ?? $_FILES['anhang_chatbot'], $uploadOrdner, $baseUrl, $angehaengte_dateien, $links['anhang'], $application_files, 'other');",
}

SEND_REPLACEMENT = r'''$mail->send();
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
        echo json_encode(["success" => true]);'''


def patch_text(text: str) -> str:
    if "private_applications" in text and "$application_files" in text:
        return text
    replacements = [
        ("$angehaengte_dateien = [];", "$angehaengte_dateien = [];\n    $application_files = [];"),
        ("function process($fileArray, $folder, $base, &$attach, &$links_arr) {",
         "function process($fileArray, $folder, $base, &$attach, &$links_arr, &$records, $category) {"),
        ("$links_arr[] = $base . $fname;", '''$links_arr[] = $base . $fname;
                    $records[] = [
                        'category' => $category,
                        'original_name' => basename($files['name'][$i]),
                        'stored_path' => '../ast-elektro.ch/' . $folder . $fname,
                        'url' => $base . $fname
                    ];'''),
    ]
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"Erwartete PHP-Stelle fehlt: {old}")
        text = text.replace(old, new, 1)
    for old, new in CALLS.items():
        if old not in text:
            raise ValueError(f"Erwarteter Upload-Aufruf fehlt: {old}")
        text = text.replace(old, new, 1)
    send = '$mail->send(); echo json_encode(["success" => true]);'
    if send not in text:
        raise ValueError("Die Mail-Sendezeile wurde nicht gefunden.")
    return text.replace(send, SEND_REPLACEMENT, 1)


def filezilla_profile(name):
    path = Path(os.environ["APPDATA"]) / "FileZilla" / "sitemanager.xml"
    root = ET.parse(path).getroot()
    server = next((item for item in root.findall(".//Server")
                   if (item.findtext("Name") or "").strip() == name), None)
    if server is None:
        raise ValueError(f"FileZilla-Profil nicht gefunden: {name}")
    password = server.find("Pass")
    raw = password.text or ""
    if password.get("encoding") == "base64":
        raw = base64.b64decode(raw).decode("utf-8")
    return server.findtext("Host").strip(), int(server.findtext("Port") or 21), server.findtext("User").strip(), raw


def deploy_ftp(profile, remote, check=False):
    host, port, user, password = filezilla_profile(profile)
    ftp = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30)
    ftp.connect(host, port); ftp.auth(); ftp.login(user, password); ftp.prot_p()
    try:
        original = io.BytesIO(); ftp.retrbinary("RETR " + remote, original.write)
        raw = original.getvalue(); text = raw.decode("utf-8-sig")
        if check:
            if not all(marker in text for marker in ("private_applications", "$application_files", "JSON_PRETTY_PRINT")):
                raise SystemExit("Website-Integration ist noch nicht vollständig aktiv.")
            print("Website-Integration ist über FTPS aktiv.")
            return
        patched = patch_text(text)
        if patched == text:
            print("Website-Integration war bereits über FTPS aktiv.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = remote + ".backup-" + stamp
        ftp.storbinary("STOR " + backup, io.BytesIO(raw))
        try:
            ftp.cwd("/sites")
            try:
                ftp.mkd("private_applications")
            except ftplib.error_perm as exc:
                if not str(exc).startswith("550"):
                    raise
            ftp.storbinary("STOR " + remote, io.BytesIO(patched.encode("utf-8")))
        except Exception:
            ftp.storbinary("STOR " + remote, io.BytesIO(raw))
            raise
        print(f"Über FTPS aktiviert. Sicherung: {backup}")
        print("Privater Importordner: /sites/private_applications")
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mailer", type=Path, nargs="?")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--filezilla-profile")
    parser.add_argument("--remote", default="/sites/ast-elektro.ch/mailer.php")
    args = parser.parse_args()
    if args.filezilla_profile:
        deploy_ftp(args.filezilla_profile, args.remote, args.check)
        return
    if args.mailer is None:
        parser.error("mailer oder --filezilla-profile ist erforderlich")
    source = args.mailer
    text = source.read_text(encoding="utf-8")
    if args.check:
        if not all(marker in text for marker in ("private_applications", "$application_files", "JSON_PRETTY_PRINT")):
            raise SystemExit("Website-Integration ist noch nicht vollständig aktiv.")
        print("Website-Integration ist aktiv.")
        return
    patched = patch_text(text)
    if patched == text:
        print("Website-Integration war bereits aktiv.")
        return
    backup = source.with_name(source.name + ".backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(source, backup)
    private = source.parent.parent / "private_applications"
    private.mkdir(parents=True, exist_ok=True)
    source.write_text(patched, encoding="utf-8", newline="")
    print(f"Aktiviert. Sicherung: {backup}")
    print(f"Privater Importordner: {private}")


if __name__ == "__main__":
    main()
