"""One-time, reversible integration patch for the AST apprenticeship form.

Usage after explicit approval:
    python tools/enable_website_applications.py /path/to/mailer.php
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mailer", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
