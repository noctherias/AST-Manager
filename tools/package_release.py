"""Create the source ZIP and ready-to-run Windows ZIP in the outputs folder."""
from pathlib import Path
import hashlib
import json
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent
DIST = ROOT / "dist" / "AST-Verwaltung"

def main():
    if not (DIST / "AST-Verwaltung.exe").exists():
        raise SystemExit("Windows-Build fehlt.")
    (DIST / "Demo starten.bat").write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0AST-Verwaltung.exe" --demo\r\n')
    (DIST / "AST starten.bat").write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0AST-Verwaltung.exe"\r\n')
    (DIST / "BITTE ZUERST LESEN.txt").write_text(
        "AST Verwaltung - Windows-MVP\n\n"
        "1. Gesamten ZIP-Ordner entpacken.\n"
        "2. Demo starten.bat: mit getrennten fiktiven Beispieldaten ausprobieren.\n"
        "3. AST-Verwaltung.exe: produktive, anfangs leere Datenbank.\n\n"
        "Der Ordner _internal muss neben der EXE bleiben. Python und Excel sind nicht erforderlich.\n"
        "Daten: %LOCALAPPDATA%\\AST-Erfassungstool\\\n"
        "Sicherungen: Einstellungen > Daten & Sicherung.\n\n"
        "Die EXE ist nicht digital signiert. Technischer Funktionstest auf Windows 11 x64.\n"
        "Dies ist ein MVP auf Basis der gelieferten Vorlagen, keine zertifizierte Lohnbuchhaltung.\n"
        "Details: README.md und docs/TESTPROTOKOLL.md im beiliegenden Quellcodepaket.\n", encoding="utf-8-sig")
    shutil.copy2(ROOT / "README.md", DIST / "README.md")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", DIST / "THIRD_PARTY_NOTICES.md")
    shutil.copytree(ROOT / "docs", DIST / "docs", dirs_exist_ok=True)
    packages = []
    for folder, filename, exclude in [(ROOT, "AST-Erfassungstool-Quellcode.zip", {"dist", "build", "build-smoke", "tmp", "output", ".venv", "__pycache__", ".git", ".pytest_cache", "credentials", "installer-output"}),
                                       (DIST, "AST-Verwaltung-Windows.zip", {"__pycache__"})]:
        path = OUT / filename
        with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for file in sorted(folder.rglob("*")):
                relative = file.relative_to(folder)
                if not file.is_file() or any(part in exclude for part in relative.parts) or file.suffix in (".pyc", ".sqlite3", ".log"):
                    continue
                archive.write(file, Path(folder.name) / relative)
        packages.append({"file": filename, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(filename, path.stat().st_size)
    (OUT / "Pruefsummen.json").write_text(json.dumps(packages, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
