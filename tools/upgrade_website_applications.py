"""Upgrade the live apprenticeship form to applicant folders and trial-date selection."""
from __future__ import annotations

import re


MARKER = "AST_APPLICATION_FOLDERS_V2"
UPLOADS_HTACCESS = """Options -Indexes
<FilesMatch "\\.json$">
    Require all denied
</FilesMatch>
"""


def patch_mailer(text: str) -> str:
    if MARKER in text:
        return text
    old = '$berufsmatura = isset($_POST["berufsmatura"]) && ($_POST["berufsmatura"] === "Ja" || $_POST["berufsmatura"] === "on") ? "ja" : "nein";'
    new = old + r'''
    // AST_APPLICATION_FOLDERS_V2
    $schnupperdaten = [];
    foreach ((array)($_POST["schnupperdaten"] ?? []) as $datum) {
        $datum = trim((string)$datum);
        $parsed = DateTime::createFromFormat("Y-m-d", $datum);
        if ($parsed && $parsed->format("Y-m-d") === $datum) $schnupperdaten[$datum] = $datum;
    }
    $schnupperdaten = array_values($schnupperdaten);'''
    if old not in text:
        raise ValueError("Feld für Berufsmatura wurde in mailer.php nicht gefunden.")
    text = text.replace(old, new, 1)

    old_upload = '''    $uploadOrdner = "uploads/";
    if (!is_dir($uploadOrdner)) mkdir($uploadOrdner, 0777, true);
    $baseUrl = "https://" . $_SERVER['HTTP_HOST'] . rtrim(dirname($_SERVER['PHP_SELF']), '/\\\\') . "/" . $uploadOrdner;'''
    new_upload = r'''    $application_id = "";
    if ($form_type === "lehrstelle") {
        $slug = static function ($value) {
            $value = trim(html_entity_decode((string)$value, ENT_QUOTES | ENT_HTML5, "UTF-8"));
            $value = preg_replace('/[^\pL\pN]+/u', '_', $value);
            return trim((string)$value, '_');
        };
        $person = trim($slug($name) . "_" . $slug($vorname), "_");
        if ($person === "") $person = "Bewerber";
        $application_id = $person . "_" . date("Ymd_His") . "_" . bin2hex(random_bytes(3));
        $uploadOrdner = "uploads/" . $application_id . "/";
    } else {
        $uploadOrdner = "uploads/";
    }
    if (!is_dir($uploadOrdner) && !mkdir($uploadOrdner, 0770, true) && !is_dir($uploadOrdner)) {
        throw new RuntimeException("Upload-Ordner konnte nicht erstellt werden.");
    }
    $baseUrl = "https://" . $_SERVER['HTTP_HOST'] . rtrim(dirname($_SERVER['PHP_SELF']), '/\\') . "/" . $uploadOrdner;'''
    if old_upload not in text:
        raise ValueError("Upload-Ordnerblock wurde in mailer.php nicht gefunden.")
    text = text.replace(old_upload, new_upload, 1)
    text = text.replace("'stored_path' => '../ast-elektro.ch/' . $folder . $fname,", "'stored_path' => $fname,", 1)

    old_line = r'''$email_text = "Name: $name\nVorname: $vorname\nStrasse/Nr: ".($_POST['strasse']??'')." ".($_POST['hausnummer']??'')."\nPLZ/Ort: ".($_POST['plz']??'')." ".($_POST['ort']??'')."\nE-Mail: $email\nTelefon: $telefon\nNachricht: $nachricht\nBewerbung für: $bewerbung_fuer\nZusatz: $berufsmatura\n\n";'''
    new_line = r'''$schnupperdaten_text = !empty($schnupperdaten) ? implode(", ", array_map(static function ($datum) { return date("d.m.Y", strtotime($datum)); }, $schnupperdaten)) : "-";
        $email_text = "Name: $name\nVorname: $vorname\nStrasse/Nr: ".($_POST['strasse']??'')." ".($_POST['hausnummer']??'')."\nPLZ/Ort: ".($_POST['plz']??'')." ".($_POST['ort']??'')."\nE-Mail: $email\nTelefon: $telefon\nNachricht: $nachricht\nBewerbung für: $bewerbung_fuer\nZusatz: $berufsmatura\nMögliche Schnupperdaten: $schnupperdaten_text\n\n";'''
    if old_line not in text:
        raise ValueError("Bewerbungs-Mailtext wurde in mailer.php nicht gefunden.")
    text = text.replace(old_line, new_line, 1)

    block = re.compile(r'''\n        if \(\$form_type === "lehrstelle"\) \{\n            // Stored outside.*?\n        \}\n        echo json_encode''', re.DOTALL)
    replacement = r'''
        if ($form_type === "lehrstelle") {
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
                "trial_dates" => $schnupperdaten,
                "message" => $plain($nachricht),
                "files" => $application_files
            ];
            $manifest_path = $uploadOrdner . "application.json";
            if (file_put_contents($manifest_path, json_encode($manifest, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX) === false) {
                error_log("Bewerbungsmanifest konnte nicht gespeichert werden: " . $manifest_path);
            }
        }
        echo json_encode'''
    text, count = block.subn(lambda _: replacement, text, count=1)
    if count != 1:
        raise ValueError("Alter Manifestblock wurde in mailer.php nicht gefunden.")
    return text


def patch_form(text: str) -> str:
    if MARKER in text:
        return text
    old = '''                            <div class="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center gap-4 cursor-pointer">
                                <input type="checkbox" id="berufsmatura" name="berufsmatura" value="Ja" class="w-5 h-5 accent-astAccent rounded bg-white/10 border-white/20 cursor-pointer">
                                <label for="berufsmatura" class="text-sm font-medium opacity-90 cursor-pointer select-none w-full">Zusatzleistung: Ich möchte die Berufsmatura parallel zur Lehre absolvieren.</label>
                            </div>'''
    new = '''                            <!-- AST_APPLICATION_FOLDERS_V2 -->
                            <div id="berufsmatura-section" class="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center gap-4 cursor-pointer">
                                <input type="checkbox" id="berufsmatura" name="berufsmatura" value="Ja" class="w-5 h-5 accent-astAccent rounded bg-white/10 border-white/20 cursor-pointer">
                                <label for="berufsmatura" class="text-sm font-medium opacity-90 cursor-pointer select-none w-full">Zusatzleistung: Ich möchte die Berufsmatura parallel zur Lehre absolvieren.</label>
                            </div>

                            <div id="schnupperdaten-section" class="hidden bg-white/5 border border-white/10 rounded-2xl p-5">
                                <label for="schnupperdatum" class="block text-xs font-bold uppercase tracking-wider mb-2 text-astAccent">Mögliche Daten für die Schnupperlehre*</label>
                                <p class="text-sm opacity-70 mb-4">Du kannst mehrere passende Daten angeben. Wähle ein Datum und klicke jeweils auf «Datum hinzufügen».</p>
                                <div class="flex flex-col sm:flex-row gap-3">
                                    <input type="date" id="schnupperdatum" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-astAccent text-sm">
                                    <button type="button" id="schnupperdatum-add" class="px-5 py-3 bg-astAccent text-[#1D1E32] rounded-xl font-bold">Datum hinzufügen</button>
                                </div>
                                <div id="schnupperdaten-list" class="flex flex-wrap gap-2 mt-4"></div>
                                <div id="schnupperdaten-inputs"></div>
                            </div>'''
    if old not in text:
        raise ValueError("Berufsmatura-Feld wurde in lehrstellen.php nicht gefunden.")
    text = text.replace(old, new, 1)

    hook = '''        document.addEventListener("DOMContentLoaded", function() {

            // --- 1. Logik für Motivationsschreiben bei Schnupperlehre ---'''
    helpers = '''        const selectedTrialDates = new Set();
        function renderTrialDates() {
            const list = document.getElementById('schnupperdaten-list');
            const inputs = document.getElementById('schnupperdaten-inputs');
            list.innerHTML = '';
            inputs.innerHTML = '';
            [...selectedTrialDates].sort().forEach(value => {
                const date = new Date(value + 'T12:00:00');
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'px-3 py-2 rounded-lg bg-astAccent/20 border border-astAccent/40 text-sm';
                chip.textContent = date.toLocaleDateString('de-CH') + ' ×';
                chip.setAttribute('aria-label', 'Datum ' + chip.textContent + ' entfernen');
                chip.addEventListener('click', () => { selectedTrialDates.delete(value); renderTrialDates(); });
                list.appendChild(chip);
                const hidden = document.createElement('input');
                hidden.type = 'hidden'; hidden.name = 'schnupperdaten[]'; hidden.value = value;
                inputs.appendChild(hidden);
            });
        }

        document.addEventListener("DOMContentLoaded", function() {
            const trialDate = document.getElementById('schnupperdatum');
            trialDate.min = new Date().toISOString().slice(0, 10);
            document.getElementById('schnupperdatum-add').addEventListener('click', function() {
                if (!trialDate.value) { trialDate.focus(); return; }
                selectedTrialDates.add(trialDate.value);
                trialDate.value = '';
                renderTrialDates();
            });

            // --- 1. Logik für Motivationsschreiben bei Schnupperlehre ---'''
    if hook not in text:
        raise ValueError("Formularinitialisierung wurde in lehrstellen.php nicht gefunden.")
    text = text.replace(hook, helpers, 1)

    old_change = '''                    if (this.value === 'Schnupperlehre Elektroberufe') {
                        inputBewerbung.removeAttribute('required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben';
                    } else {
                        // Bei echten Lehrstellen ist es ein Pflichtfeld
                        inputBewerbung.setAttribute('required', 'required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben*';
                    }'''
    new_change = '''                    const isTrial = this.value === 'Schnupperlehre Elektroberufe';
                    document.getElementById('schnupperdaten-section').classList.toggle('hidden', !isTrial);
                    document.getElementById('berufsmatura-section').classList.toggle('hidden', isTrial);
                    if (isTrial) {
                        document.getElementById('berufsmatura').checked = false;
                        inputBewerbung.removeAttribute('required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben';
                    } else {
                        inputBewerbung.setAttribute('required', 'required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben*';
                    }'''
    if old_change not in text:
        raise ValueError("Auswahllogik wurde in lehrstellen.php nicht gefunden.")
    text = text.replace(old_change, new_change, 1)

    old_submit = '''            const toast = document.getElementById('success-toast');

            overlay.classList.remove('hidden');'''
    new_submit = '''            const toast = document.getElementById('success-toast');
            const selectedType = form.querySelector('input[name="bewerbung_fuer"]:checked');
            if (selectedType && selectedType.value === 'Schnupperlehre Elektroberufe' && selectedTrialDates.size === 0) {
                alert('Bitte gib mindestens ein mögliches Datum für die Schnupperlehre an.');
                document.getElementById('schnupperdatum').focus();
                return;
            }

            overlay.classList.remove('hidden');'''
    if old_submit not in text:
        raise ValueError("Absendehandler wurde in lehrstellen.php nicht gefunden.")
    text = text.replace(old_submit, new_submit, 1)

    reset = '''                    form.reset();
                    // UI für Upload-Felder zurücksetzen'''
    reset_new = '''                    form.reset();
                    selectedTrialDates.clear();
                    renderTrialDates();
                    document.getElementById('schnupperdaten-section').classList.add('hidden');
                    document.getElementById('berufsmatura-section').classList.remove('hidden');
                    // UI für Upload-Felder zurücksetzen'''
    if reset not in text:
        raise ValueError("Formular-Reset wurde in lehrstellen.php nicht gefunden.")
    return text.replace(reset, reset_new, 1)
