import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ast_app.updates import (ASSET_NAME, Release, UpdateError, version_tuple, repository_name,
                             parse_release, check_release, download_release, open_url,
                             GithubRedirect, start_installer, configured_repository)


REPO = "manueltuescher/AST-Manager"
PAYLOAD = b"MZ" + b"test installer bytes" * 50000


def metadata():
    return {"tag_name": "v0.3.0", "body": "Neue Funktionen", "draft": False, "prerelease": False,
            "assets": [{"name": ASSET_NAME, "id": 1234, "state": "uploaded", "size": len(PAYLOAD),
                        "digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest(),
                        "url": f"https://api.github.com/repos/{REPO}/releases/assets/1234",
                        "browser_download_url": f"https://github.com/{REPO}/releases/download/v0.3.0/{ASSET_NAME}"}]}


class UpdateTests(unittest.TestCase):
    def test_versions_and_release_policy(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.9.9"))
        self.assertEqual(repository_name(f"https://github.com/{REPO}.git"), REPO)
        for bad in ("../evil", "https://example.com/x/y", "x/..", "x/y?token=secret"):
            with self.assertRaises(UpdateError): repository_name(bad)
        for bad in ("1.0", "1.01.0", "v1.0.0-rc1"):
            with self.assertRaises(UpdateError): version_tuple(bad)
        self.assertIsNone(parse_release(metadata(), REPO, "0.3.0"))
        for flag in ("draft", "prerelease"):
            data = metadata(); data[flag] = True
            self.assertIsNone(parse_release(data, REPO, "0.2.0"))
        release = check_release(REPO, "0.2.0", lambda url: io.BytesIO(json.dumps(metadata()).encode()))
        self.assertEqual(release.version, "0.3.0")
        self.assertIn("api.github.com/repos/", release.download_url)

    def test_bundled_update_channel_overrides_stale_user_setting(self):
        self.assertEqual(configured_repository({"update_repository": "old-owner/old-repo"}),
                         "noctherias/AST-Manager")

    def test_reject_tampered_assets(self):
        for field, value in [("digest", None), ("size", -1), ("id", "1234"),
                             ("url", "https://evil.example/setup.exe"),
                             ("browser_download_url", f"https://github.com/other/repo/releases/download/v0.3.0/{ASSET_NAME}")]:
            data = metadata(); data["assets"][0][field] = value
            with self.assertRaises(UpdateError): parse_release(data, REPO, "0.2.0")
        data = metadata(); data["assets"] *= 2
        with self.assertRaises(UpdateError): parse_release(data, REPO, "0.2.0")

    def test_private_access_and_redirect_never_leak_token(self):
        with patch("ast_app.updates.build_opener") as factory:
            open_url(f"https://api.github.com/repos/{REPO}/releases/latest", token="fake-token")
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"), "Bearer fake-token")
            open_url(f"https://api.github.com/repos/{REPO}/releases/assets/1234", token="fake-token")
            self.assertEqual(factory.return_value.open.call_args.args[0].get_header("Accept"), "application/octet-stream")
            open_url("https://release-assets.githubusercontent.com/test", token="fake-token")
            self.assertIsNone(factory.return_value.open.call_args.args[0].get_header("Authorization"))
        req = Request("https://api.github.com/test", headers={"Authorization": "Bearer fake-token"})
        redirected = GithubRedirect().redirect_request(req, None, 302, "", {}, "https://release-assets.githubusercontent.com/setup")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(UpdateError):
            GithubRedirect().redirect_request(req, None, 302, "", {}, "https://evil.example/setup")
        with self.assertRaises(UpdateError): open_url("http://api.github.com/test", token="fake-token")

    def test_verified_download_and_failure_cleanup(self):
        release = parse_release(metadata(), REPO, "0.2.0")
        with tempfile.TemporaryDirectory() as temp:
            progress = []
            path = download_release(release, temp, lambda done, total: progress.append((done, total)), opener=lambda url: io.BytesIO(PAYLOAD))
            self.assertEqual(path.read_bytes(), PAYLOAD)
            self.assertEqual(progress[-1], (len(PAYLOAD), len(PAYLOAD)))
            for data in (PAYLOAD[:-5], b"MZ" + b"x" * (len(PAYLOAD)-2), PAYLOAD + b"overflow"):
                with self.assertRaises(UpdateError): download_release(release, temp, opener=lambda url: io.BytesIO(data))
                self.assertFalse(list(Path(temp).glob("*.part")))
            with self.assertRaises(UpdateError): download_release(release, temp, cancelled=lambda: True, opener=lambda url: io.BytesIO(PAYLOAD))
            self.assertFalse(list(Path(temp).glob("*.part")))

    def test_offline_and_access_failures_have_actionable_messages(self):
        for error, message in [(URLError("offline"), "Internetverbindung"),
                                (HTTPError("url", 404, "not found", {}, None), "nicht öffentlich"),
                                (HTTPError("url", 401, "denied", {}, None), "abgelehnt")]:
            with self.assertRaisesRegex(UpdateError, message):
                check_release(REPO, opener=lambda url: (_ for _ in ()).throw(error))

    @unittest.skipUnless(os.name == "nt", "Windows installer")
    def test_installer_rechecks_integrity_and_preserves_start_options(self):
        release = parse_release(metadata(), REPO, "0.2.0")
        with tempfile.TemporaryDirectory() as temp, patch("sys.frozen", True, create=True), patch("ast_app.updates.subprocess.Popen") as run:
            path = Path(temp) / "setup.exe"; path.write_bytes(PAYLOAD)
            start_installer(path, release, Path(temp) / "Daten mit Leerzeichen", True)
            args = run.call_args.args[0]
            self.assertIn("/ASTDEMO=1", args)
            self.assertTrue(any(a.endswith("Daten mit Leerzeichen") for a in args))
            path.write_bytes(b"modified")
            with self.assertRaises(UpdateError): start_installer(path, release, temp)
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__": unittest.main()
