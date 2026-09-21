"""GitHub release checks and verified downloads, including private repositories."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from . import __version__

ASSET_NAME = "AST-Verwaltung-Setup-x64.exe"
MAX_INSTALLER = 400 * 1024 * 1024


class UpdateError(ValueError):
    pass


def version_tuple(value):
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", str(value))
    if not match:
        raise UpdateError("Die Version muss im Format 0.2.0 angegeben sein.")
    return tuple(int(n) for n in match.groups())


def repository_name(value):
    value = str(value).strip().removesuffix("/").removesuffix(".git")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):]
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]+", value):
        raise UpdateError("Bitte ein Repository als benutzer/projekt oder GitHub-Link eingeben.")
    if value.split("/")[1] in (".", ".."):
        raise UpdateError("Ungültiger Repository-Name.")
    return value


def configured_repository(settings):
    if settings.get("update_repository"):
        return repository_name(settings["update_repository"])
    config = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "release_config.json"
    if config.exists():
        value = json.loads(config.read_text(encoding="utf-8")).get("repository", "")
        if value:
            return repository_name(value)
    return ""


def allowed_url(url):
    p = urlparse(url)
    return p.scheme == "https" and p.port in (None, 443) and not p.username and not p.password and p.hostname in (
        "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")


class GithubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise UpdateError("Der Download wurde auf eine unerwartete Adresse umgeleitet.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urlparse(newurl).netloc != urlparse(req.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def open_url(url, timeout=15, token=""):
    if not allowed_url(url):
        raise UpdateError("Nur sichere GitHub-Download-Adressen sind erlaubt.")
    request = Request(url, headers={"User-Agent": f"AST-Verwaltung/{__version__}",
                                   "Accept": "application/octet-stream" if "/releases/assets/" in url or not url.startswith("https://api.github.com/") else "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28"})
    if token and urlparse(url).hostname == "api.github.com":
        request.add_unredirected_header("Authorization", "Bearer " + token)
    return build_opener(GithubRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    download_url: str
    size: int
    sha256: str


def parse_release(data, repository, current=__version__):
    repo = repository_name(repository)
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name", ""))
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", tag):
        return None
    if version_tuple(tag) <= version_tuple(current):
        return None
    assets = [a for a in data.get("assets", []) if a.get("name") == ASSET_NAME and a.get("state") == "uploaded"]
    if len(assets) != 1:
        raise UpdateError("Das neue Release enthält noch kein vollständiges Windows-Setup.")
    asset = assets[0]
    expected = f"https://github.com/{repo}/releases/download/{quote(tag, safe='')}/{ASSET_NAME}"
    if asset.get("browser_download_url", "").casefold() != expected.casefold():
        raise UpdateError("Der Installer gehört nicht zum eingestellten Repository und Release.")
    asset_id = asset.get("id")
    if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id <= 0:
        raise UpdateError("Die Download-Kennung fehlt.")
    api_url = f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}"
    if asset.get("url", "").casefold() != api_url.casefold():
        raise UpdateError("Die Download-Adresse gehört nicht zum Repository.")
    digest = asset.get("digest", "") or ""
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        raise UpdateError("Für das Setup fehlt die SHA-256-Prüfsumme von GitHub.")
    size = asset.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_INSTALLER:
        raise UpdateError("Die Grösse des Setups ist ungültig.")
    return Release(tag.removeprefix("v"), str(data.get("body") or "Verbesserungen und Fehlerbehebungen.")[:20000],
                   f"https://github.com/{repo}/releases/tag/{quote(tag, safe='')}", api_url, size, digest[7:].lower())


def check_release(repository, current=__version__, opener=open_url):
    repo = repository_name(repository)
    try:
        with opener(f"https://api.github.com/repos/{repo}/releases/latest") as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise UpdateError("Die Release-Antwort ist zu gross.")
            data = json.loads(raw)
        if not isinstance(data, dict):
            raise UpdateError("GitHub hat ungültige Release-Daten geliefert.")
        return parse_release(data, repo, current)
    except HTTPError as e:
        if e.code == 404:
            raise UpdateError("Noch kein Release gefunden oder kein Zugriff. Bei einem privaten Repository den Zugang unter Einstellungen > Updates hinterlegen.") from None
        if e.code == 401:
            raise UpdateError("Der GitHub-Zugang ist abgelaufen oder ungültig. Bitte unter Einstellungen > Updates erneuern.") from None
        if e.code in (403, 429):
            raise UpdateError("GitHub erlaubt momentan keine weitere Prüfung. Bitte später versuchen.") from None
        raise UpdateError(f"GitHub ist momentan nicht erreichbar (HTTP {e.code}).") from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise UpdateError("Die Versionsprüfung ist momentan nicht möglich. Bitte die Internetverbindung prüfen.") from e


def download_release(release, directory, progress=lambda current, total: None, cancelled=lambda: False, opener=open_url):
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    # Only fixed filenames plus a previously validated version enter local paths.
    version_tuple(release.version)
    final = folder / f"AST-Verwaltung-{release.version}-Setup.exe"
    partial = final.with_suffix(".part")
    digest, size = hashlib.sha256(), 0
    started = time.monotonic()
    try:
        with opener(release.download_url) as response, partial.open("wb") as out:
            while True:
                if cancelled():
                    raise UpdateError("Download abgebrochen.")
                if time.monotonic() - started > 600:
                    raise UpdateError("Der Download dauert zu lange. Bitte erneut versuchen.")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > release.size or size > MAX_INSTALLER:
                    raise UpdateError("Die Download-Grösse stimmt nicht mit dem Release überein.")
                out.write(chunk)
                digest.update(chunk)
                progress(size, release.size)
        if size != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError("Die Datei ist unvollständig oder ihre Prüfsumme stimmt nicht. Sie wird nicht installiert.")
        with partial.open("rb") as check:
            if check.read(2) != b"MZ":
                raise UpdateError("Die Datei ist kein Windows-Setup.")
        partial.replace(final)
        return final
    finally:
        partial.unlink(missing_ok=True)


def start_installer(path, release, data_dir, demo=False):
    if os.name != "nt" or not getattr(sys, "frozen", False):
        raise UpdateError("Das automatische Aktualisieren ist in der installierten Windows-Version verfügbar.")
    # Recheck immediately before execution, even if an old download already exists.
    path = Path(path).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != release.sha256:
        raise UpdateError("Die Setup-Datei wurde verändert. Bitte neu herunterladen.")
    args = [str(path), "/SP-", "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
            "/ASTUPDATE=1", f"/ASTDATADIR={Path(data_dir).resolve()}", f"/ASTDEMO={int(demo)}"]
    subprocess.Popen(args, close_fds=True)
