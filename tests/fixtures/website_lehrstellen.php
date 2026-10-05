<?php
    $pageTitle = "Lehrstellen";
    include 'header.php';

    // Dynamisches Lehrjahr: Ab August (Monat 8) startet die Rekrutierung für nächstes Jahr.
    $naechstesLehrjahr = (date('n') >= 8) ? date('Y') + 1 : date('Y');
?>

    <div id="success-toast" class="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] hidden">
        <div class="toast-success bg-green-500 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-4 border border-white/20">
            <div class="bg-white/20 p-2 rounded-full">
                <i data-lucide="check-circle-2" class="w-6 h-6"></i>
            </div>
            <div>
                <p class="font-bold">Bewerbung erfolgreich gesendet!</p>
                <p class="text-sm opacity-90 text-white">Vielen Dank. Wir melden uns in Kürze bei dir.</p>
            </div>
        </div>
    </div>

    <section class="pt-40 pb-20 bg-white/[0.01] border-b border-white/5 relative overflow-hidden">
        <div class="absolute top-[-20%] left-[-10%] w-[50%] h-[80%] bg-astAccent/5 blur-[150px] rounded-full pointer-events-none"></div>
        <div class="container mx-auto px-6 md:px-12 relative z-10 flex flex-col lg:flex-row lg:items-end justify-between gap-10">
            <div class="max-w-3xl reveal">
                <span class="text-astAccent font-bold tracking-widest uppercase text-xs mb-4 block flex items-center gap-2">
                    <i data-lucide="graduation-cap" class="w-4 h-4"></i> Ausbildung & Zukunft
                </span>
                <h1 class="text-4xl md:text-6xl font-medium tracking-tight mb-6 leading-tight">
                    Starte deine <br><span class="electro-shine">Zukunft bei uns.</span>
                </h1>
                <p class="text-lg opacity-60 font-light leading-relaxed">
                    Du interessierst dich für einen Beruf aus der Elektrotechnik? Wir sind stetig auf der Suche nach interessierten, jungen Leuten für eine starke Berufsausbildung.
                </p>
            </div>
        </div>
    </section>

    <section class="py-16 border-b border-white/5 relative">
        <div class="container mx-auto px-6 md:px-12">
            <div class="flex items-center justify-center gap-2 mb-8 opacity-50 text-xs font-bold tracking-widest uppercase reveal">
                <i data-lucide="refresh-cw" class="w-4 h-4 animate-spin-slow" id="sync-icon"></i> Live-Abgleich mit dem Kanton Aargau (LENA)
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-5xl mx-auto">

                <div id="box-installateur" class="bg-white/[0.02] border border-white/10 rounded-[2rem] p-8 electric-glow flex flex-col items-center justify-center text-center relative overflow-hidden pulse-loading spotlight-card reveal">
                    <div class="absolute inset-0 bg-gradient-to-t from-[#1D1E32]/50 to-transparent"></div>
                    <div class="relative z-10">
                        <h3 class="text-xl font-bold text-white mb-2">Elektroinstallateur/in EFZ</h3>
                        <!-- Hier greift nun die automatische Jahreszahl -->
                        <p class="opacity-70 font-light mb-6 text-sm">Lehrbeginn ab Sommer <?php echo $naechstesLehrjahr; ?></p>
                        <div id="badge-installateur" class="inline-flex items-center gap-2 bg-white/10 text-white/50 border border-white/10 px-4 py-2 rounded-full font-bold text-sm">
                            <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Lade Daten...
                        </div>
                    </div>
                </div>

                <div id="box-montage" class="bg-white/[0.02] border border-white/10 rounded-[2rem] p-8 electric-glow flex flex-col items-center justify-center text-center relative overflow-hidden pulse-loading spotlight-card reveal" style="transition-delay: 150ms;">
                    <div class="absolute inset-0 bg-gradient-to-t from-[#1D1E32]/50 to-transparent"></div>
                    <div class="relative z-10">
                        <h3 class="text-xl font-bold text-white mb-2">Montage-Elektriker/in EFZ</h3>
                        <!-- Hier greift nun die automatische Jahreszahl -->
                        <p class="opacity-70 font-light mb-6 text-sm">Lehrbeginn ab Sommer <?php echo $naechstesLehrjahr; ?></p>
                        <div id="badge-montage" class="inline-flex items-center gap-2 bg-white/10 text-white/50 border border-white/10 px-4 py-2 rounded-full font-bold text-sm">
                            <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Lade Daten...
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </section>

    <section class="py-24 relative flex-grow mb-16">
        <div class="container mx-auto px-6 md:px-12">

            <div class="max-w-4xl mx-auto">
                <div class="p-8 md:p-12 rounded-[2.5rem] bg-white/[0.02] border border-white/10 shadow-2xl relative electric-glow spotlight-card reveal">

                    <div id="loading-overlay" class="absolute inset-0 bg-[#1D1E32]/80 backdrop-blur-sm rounded-[2.5rem] z-10 flex flex-col items-center justify-center hidden">
                        <i data-lucide="loader-2" class="w-10 h-10 text-astAccent animate-spin mb-4"></i>
                        <p class="font-bold tracking-wide">Bewerbung wird gesendet...</p>
                    </div>

                    <h3 class="text-3xl font-bold mb-4 text-center">Wir freuen uns auf deine Bewerbung!</h3>
                    <p class="opacity-60 font-light text-sm mb-10 text-center max-w-xl mx-auto">Wenn du Interesse an einer Lehrstelle oder einer Schnupperlehre hast, fülle einfach dieses Formular aus und lade deine Dokumente hoch.</p>

                    <form id="bewerbung-form" action="mailer.php" method="POST" enctype="multipart/form-data" onsubmit="handleFormSubmit(event)">
                        <input type="hidden" name="form_type" value="lehrstelle">

                        <!-- HONEYPOT FELD (Für Menschen unsichtbar) -->
                        <div style="display:none !important; visibility:hidden;">
                            <label>Bitte dieses Feld komplett leer lassen:</label>
                            <input type="text" name="website_url" autocomplete="off" tabindex="-1">
                        </div>

                        <div class="space-y-6">

                            <div class="bg-white/5 border border-white/10 rounded-2xl p-6 mb-8">
                                <label class="block text-xs font-bold uppercase tracking-wider mb-4 text-astAccent">Ich bewerbe mich für..*</label>
                                <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                    <label class="flex items-center gap-3 cursor-pointer">
                                        <input type="radio" name="bewerbung_fuer" value="Schnupperlehre Elektroberufe" required class="w-4 h-4 accent-astAccent bg-white/10 border-white/20">
                                        <span class="text-sm opacity-90">Schnupperlehre</span>
                                    </label>

                                    <label id="label-installateur" class="flex items-center gap-3 cursor-pointer opacity-50">
                                        <input type="radio" id="radio-installateur" name="bewerbung_fuer" value="Lehrstelle Elektroinstallateur EFZ" disabled class="w-4 h-4 accent-astAccent bg-white/10 border-white/20">
                                        <span id="text-installateur" class="text-sm opacity-90">Elektroinstallateur (Lade...)</span>
                                    </label>

                                    <label id="label-montage" class="flex items-center gap-3 cursor-pointer opacity-50">
                                        <input type="radio" id="radio-montage" name="bewerbung_fuer" value="Lehrstelle Montage-Elektriker EFZ" disabled class="w-4 h-4 accent-astAccent bg-white/10 border-white/20">
                                        <span id="text-montage" class="text-sm opacity-90">Montage-Elektriker (Lade...)</span>
                                    </label>
                                </div>
                            </div>

                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Name*</label>
                                    <input type="text" name="name" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Vorname*</label>
                                    <input type="text" name="vorname" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                            </div>

                            <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
                                <div class="sm:col-span-2">
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Strasse*</label>
                                    <input type="text" name="strasse" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Hausnr.*</label>
                                    <input type="text" name="hausnummer" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                            </div>

                            <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">PLZ*</label>
                                    <input type="text" name="plz" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                                <div class="sm:col-span-2">
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Ort*</label>
                                    <input type="text" name="ort" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                            </div>

                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">E-Mail*</label>
                                    <input type="email" name="email" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                                <div>
                                    <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Telefon / Mobile*</label>
                                    <input type="text" name="telefon" required class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm">
                                </div>
                            </div>

                            <div class="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center gap-4 cursor-pointer">
                                <input type="checkbox" id="berufsmatura" name="berufsmatura" value="Ja" class="w-5 h-5 accent-astAccent rounded bg-white/10 border-white/20 cursor-pointer">
                                <label for="berufsmatura" class="text-sm font-medium opacity-90 cursor-pointer select-none w-full">Zusatzleistung: Ich möchte die Berufsmatura parallel zur Lehre absolvieren.</label>
                            </div>

                            <div>
                                <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">Deine Nachricht an uns</label>
                                <textarea name="nachricht" rows="4" placeholder="Schreibe uns kurz, warum du den Beruf spannend findest..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 focus:outline-none focus:border-astAccent focus:bg-white/10 transition-colors text-sm resize-none"></textarea>
                            </div>

                            <div class="pt-6 border-t border-white/10">
                                <h4 class="text-lg font-bold mb-4">Deine Unterlagen</h4>
                                <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">

                                    <div>
                                        <label id="label-bewerbung" class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1 transition-all">1. Bewerbung / Motivationsschreiben*</label>
                                        <label class="dropzone flex flex-col items-center justify-center w-full h-32 border-2 border-white/20 border-dashed rounded-xl cursor-pointer bg-white/5 hover:bg-white/10 hover:border-astAccent transition-all overflow-hidden relative">
                                            <div class="flex flex-col items-center justify-center pt-4 pb-4 text-center px-4 w-full">
                                                <i data-lucide="file-text" class="upload-icon w-6 h-6 text-astAccent mb-2"></i>
                                                <p class="file-name-display text-xs opacity-80 truncate w-full"><span class="font-bold">Datei auswählen</span></p>
                                            </div>
                                            <input type="file" id="input-bewerbung" name="bewerbung" class="hidden" onchange="updateSingleFile(this)" accept=".pdf" required />
                                        </label>
                                    </div>

                                    <div>
                                        <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">2. Lebenslauf*</label>
                                        <label class="dropzone flex flex-col items-center justify-center w-full h-32 border-2 border-white/20 border-dashed rounded-xl cursor-pointer bg-white/5 hover:bg-white/10 hover:border-astAccent transition-all overflow-hidden relative">
                                            <div class="flex flex-col items-center justify-center pt-4 pb-4 text-center px-4 w-full">
                                                <i data-lucide="user" class="upload-icon w-6 h-6 text-astAccent mb-2"></i>
                                                <p class="file-name-display text-xs opacity-80 truncate w-full"><span class="font-bold">Datei auswählen</span></p>
                                            </div>
                                            <input type="file" name="lebenslauf" class="hidden" onchange="updateSingleFile(this)" accept=".pdf" required />
                                        </label>
                                    </div>

                                    <div>
                                        <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">3. Zeugnisse*</label>
                                        <label class="dropzone flex flex-col items-center justify-center w-full h-32 border-2 border-white/20 border-dashed rounded-xl cursor-pointer bg-white/5 hover:bg-white/10 hover:border-astAccent transition-all overflow-hidden relative">
                                            <div class="flex flex-col items-center justify-center pt-4 pb-4 text-center px-4 w-full">
                                                <i data-lucide="award" class="upload-icon w-6 h-6 text-astAccent mb-2"></i>
                                                <p class="file-name-display text-xs opacity-80 truncate w-full"><span class="font-bold">Dateien auswählen</span></p>
                                            </div>
                                            <input type="file" name="zeugnisse[]" class="hidden" onchange="updateMultipleFiles(this)" accept=".pdf,.jpg,.jpeg,.png" multiple required />
                                        </label>
                                    </div>

                                    <div>
                                        <label class="block text-xs font-bold uppercase tracking-wider mb-2 opacity-60 ml-1">4. Sonstige Uploads</label>
                                        <label class="dropzone flex flex-col items-center justify-center w-full h-32 border-2 border-white/20 border-dashed rounded-xl cursor-pointer bg-white/5 hover:bg-white/10 hover:border-astAccent transition-all overflow-hidden relative">
                                            <div class="flex flex-col items-center justify-center pt-4 pb-4 text-center px-4 w-full">
                                                <i data-lucide="paperclip" class="upload-icon w-6 h-6 text-astAccent mb-2"></i>
                                                <p class="file-name-display text-xs opacity-80 truncate w-full"><span class="font-bold">Dateien auswählen (optional)</span></p>
                                            </div>
                                            <input type="file" name="sonstige[]" class="hidden" onchange="updateMultipleFiles(this)" accept=".pdf,.jpg,.jpeg,.png" multiple />
                                        </label>
                                    </div>

                                </div>
                            </div>

                            <div class="pt-2">
                                <p class="text-xs opacity-50 italic">* Alle so markierten Felder sind Pflichtfelder und müssen zwingend ausgefüllt werden.</p>
                            </div>

                            <button type="submit" class="btn-shine w-full py-5 bg-astAccent text-[#1D1E32] rounded-xl font-bold hover:bg-orange-500 transition-all shadow-[0_10px_30px_-10px_rgba(229,158,46,0.5)] flex justify-center items-center gap-2 group text-lg">
                                Bewerbung absenden <i data-lucide="send" class="w-5 h-5 group-hover:translate-x-1 group-hover:-translate-y-1 transition-transform"></i>
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </section>

    <script>
        // Neue JS Funktionen für die strukturierten Upload-Felder
        function updateSingleFile(input) {
            const dropzone = input.closest('.dropzone');
            const display = dropzone.querySelector('.file-name-display');
            const icon = dropzone.querySelector('.upload-icon');

            if (input.files && input.files[0]) {
                display.innerHTML = `<span class="font-bold text-astAccent">${input.files[0].name}</span>`;
                dropzone.classList.add('border-astAccent', 'bg-white/10');
                icon.setAttribute('data-lucide', 'check-circle');
            } else {
                display.innerHTML = '<span class="font-bold">Datei auswählen</span>';
                dropzone.classList.remove('border-astAccent', 'bg-white/10');
                icon.setAttribute('data-lucide', 'file-text'); // Fallback Icon
            }
            lucide.createIcons();
        }

        function updateMultipleFiles(input) {
            const dropzone = input.closest('.dropzone');
            const display = dropzone.querySelector('.file-name-display');
            const icon = dropzone.querySelector('.upload-icon');

            if (input.files && input.files.length > 0) {
                const text = input.files.length === 1 ? input.files[0].name : `${input.files.length} Dateien ausgewählt`;
                display.innerHTML = `<span class="font-bold text-astAccent">${text}</span>`;
                dropzone.classList.add('border-astAccent', 'bg-white/10');
                icon.setAttribute('data-lucide', 'check-circle');
            } else {
                display.innerHTML = '<span class="font-bold">Dateien auswählen</span>';
                dropzone.classList.remove('border-astAccent', 'bg-white/10');
                icon.setAttribute('data-lucide', 'paperclip'); // Fallback Icon
            }
            lucide.createIcons();
        }

        // ==============================================================
        // DYNAMISCHE PFLICHTFELDER & LENA LIVE-ABFRAGE
        // ==============================================================
        document.addEventListener("DOMContentLoaded", function() {

            // --- 1. Logik für Motivationsschreiben bei Schnupperlehre ---
            const radioBewerbungFuer = document.querySelectorAll('input[name="bewerbung_fuer"]');
            const labelBewerbung = document.getElementById('label-bewerbung');
            const inputBewerbung = document.getElementById('input-bewerbung');

            radioBewerbungFuer.forEach(radio => {
                radio.addEventListener('change', function() {
                    // Wenn Schnupperlehre gewählt wird, ist Motivationsschreiben optional
                    if (this.value === 'Schnupperlehre Elektroberufe') {
                        inputBewerbung.removeAttribute('required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben';
                    } else {
                        // Bei echten Lehrstellen ist es ein Pflichtfeld
                        inputBewerbung.setAttribute('required', 'required');
                        labelBewerbung.innerText = '1. Bewerbung / Motivationsschreiben*';
                    }
                });
            });

            // --- 2. LENA Live-Abfrage (Kanton Aargau) ---
            fetch('mailer.php?action=getLehrstellen')
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    document.getElementById('box-installateur').classList.remove('pulse-loading');
                    document.getElementById('box-montage').classList.remove('pulse-loading');
                    document.getElementById('sync-icon').classList.remove('animate-spin-slow');

                    const offeneInstallateur = data.data["Elektroinstallateur/in EFZ"] || 0;
                    const offeneMontage = data.data["Montage-Elektriker/in EFZ"] || 0;

                    const badgeInst = document.getElementById('badge-installateur');
                    const boxInst = document.getElementById('box-installateur');
                    if(offeneInstallateur > 0) {
                        badgeInst.className = "inline-flex items-center gap-2 bg-green-500/20 text-green-400 border border-green-500/30 px-4 py-2 rounded-full font-bold text-sm";
                        badgeInst.innerHTML = `<i data-lucide="check-circle" class="w-4 h-4"></i> ${offeneInstallateur} Lehrstelle${offeneInstallateur > 1 ? 'n' : ''} offen`;
                        boxInst.classList.remove('opacity-60');
                        boxInst.classList.add('bg-astAccent/10', 'border-astAccent/30');
                    } else {
                        badgeInst.className = "inline-flex items-center gap-2 bg-white/10 text-white/50 border border-white/10 px-4 py-2 rounded-full font-bold text-sm";
                        badgeInst.innerHTML = `<i data-lucide="x-circle" class="w-4 h-4"></i> 0 Lehrstellen offen`;
                        boxInst.classList.add('opacity-60');
                        boxInst.classList.remove('bg-astAccent/10', 'border-astAccent/30');
                    }

                    const badgeMont = document.getElementById('badge-montage');
                    const boxMont = document.getElementById('box-montage');
                    if(offeneMontage > 0) {
                        badgeMont.className = "inline-flex items-center gap-2 bg-green-500/20 text-green-400 border border-green-500/30 px-4 py-2 rounded-full font-bold text-sm";
                        badgeMont.innerHTML = `<i data-lucide="check-circle" class="w-4 h-4"></i> ${offeneMontage} Lehrstelle${offeneMontage > 1 ? 'n' : ''} offen`;
                        boxMont.classList.remove('opacity-60');
                        boxMont.classList.add('bg-astAccent/10', 'border-astAccent/30');
                    } else {
                        badgeMont.className = "inline-flex items-center gap-2 bg-white/10 text-white/50 border border-white/10 px-4 py-2 rounded-full font-bold text-sm";
                        badgeMont.innerHTML = `<i data-lucide="x-circle" class="w-4 h-4"></i> 0 Lehrstellen offen`;
                        boxMont.classList.add('opacity-60');
                        boxMont.classList.remove('bg-astAccent/10', 'border-astAccent/30');
                    }

                    if(offeneInstallateur > 0) {
                        document.getElementById('radio-installateur').disabled = false;
                        document.getElementById('label-installateur').classList.remove('opacity-50');
                        document.getElementById('text-installateur').innerText = "Elektroinstallateur EFZ";
                    } else {
                        document.getElementById('radio-installateur').disabled = true;
                        document.getElementById('label-installateur').classList.add('opacity-50');
                        document.getElementById('text-installateur').innerText = "Elektroinstallateur (Besetzt)";
                    }

                    if(offeneMontage > 0) {
                        document.getElementById('radio-montage').disabled = false;
                        document.getElementById('label-montage').classList.remove('opacity-50');
                        document.getElementById('text-montage').innerText = "Montage-Elektriker EFZ";
                    } else {
                        document.getElementById('radio-montage').disabled = true;
                        document.getElementById('label-montage').classList.add('opacity-50');
                        document.getElementById('text-montage').innerText = "Montage-Elektriker (Besetzt)";
                    }

                    lucide.createIcons();
                }
            })
            .catch(err => {
                console.error("Fehler beim Abrufen der Lehrstellen:", err);
            });
        });

        function handleFormSubmit(event) {
            event.preventDefault();

            const form = document.getElementById('bewerbung-form');
            const formData = new FormData(form);
            const overlay = document.getElementById('loading-overlay');
            const toast = document.getElementById('success-toast');

            overlay.classList.remove('hidden');

            fetch('mailer.php', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                overlay.classList.add('hidden');

                if(data.success) {
                    toast.classList.remove('hidden');
                    setTimeout(() => { toast.classList.add('hidden'); }, 6000);

                    form.reset();
                    // UI für Upload-Felder zurücksetzen
                    document.querySelectorAll('.dropzone').forEach(zone => {
                        zone.classList.remove('border-astAccent', 'bg-white/10');
                        const display = zone.querySelector('.file-name-display');
                        const isMultiple = zone.querySelector('input').hasAttribute('multiple');
                        display.innerHTML = `<span class="font-bold">${isMultiple ? 'Dateien auswählen' : 'Datei auswählen'}</span>`;
                    });

                    // Motivationsschreiben-Label sicherheitshalber wieder auf Default (Pflicht) setzen
                    document.getElementById('label-bewerbung').innerText = '1. Bewerbung / Motivationsschreiben*';

                    lucide.createIcons();
                } else {
                    alert("Es gab ein Problem: " + (data.message || "Unbekannter Fehler"));
                }
            })
            .catch(error => {
                overlay.classList.add('hidden');
                alert("Fehler beim Senden. Bitte lade die Dateien auf den echten Webserver hoch, um PHP auszuführen.");
            });
        }
    </script>

<?php include 'footer.php'; ?>
