# Windows-Code-Signierung

Der Release-Workflow kann `AST-Verwaltung.exe` und das Setup automatisch mit einem Authenticode-Zertifikat signieren. Ohne hinterlegtes Zertifikat bleibt der Build funktionsfähig und weist im Workflow darauf hin, dass die Dateien unsigniert sind.

## Einmalige Einrichtung

1. Ein öffentlich vertrauenswürdiges Windows-Code-Signing-Zertifikat als PFX mit privatem Schlüssel beschaffen.
2. Die PFX-Datei lokal in Base64 umwandeln:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\Pfad\codesigning.pfx')) | Set-Clipboard
   ```

3. Im GitHub-Repository unter **Settings → Secrets and variables → Actions** zwei Repository-Secrets anlegen:
   - `WINDOWS_SIGNING_CERTIFICATE`: Base64-Inhalt der PFX-Datei
   - `WINDOWS_SIGNING_PASSWORD`: Kennwort der PFX-Datei

Beim nächsten Release importiert GitHub Actions das Zertifikat nur für die Dauer des Builds, signiert EXE und Installer mit SHA-256 sowie Zeitstempel, prüft beide Signaturen und entfernt Zertifikat und PFX anschliessend wieder. Die PFX-Datei und ihr Kennwort dürfen niemals ins Repository eingecheckt werden.
