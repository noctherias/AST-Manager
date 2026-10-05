"""Tests for the reversible website manifest patch."""
import unittest

from tools.enable_website_applications import CALLS, patch_text
from tools.upgrade_website_applications import MARKER, UPLOADS_HTACCESS, patch_form, patch_mailer


class WebsiteIntegrationTests(unittest.TestCase):
    def test_patch_is_complete_and_idempotent(self):
        calls = "\n".join(CALLS)
        source = """<?php
$angehaengte_dateien = [];
function process($fileArray, $folder, $base, &$attach, &$links_arr) {
    $links_arr[] = $base . $fname;
}
%s
$mail->send(); echo json_encode(["success" => true]);
""" % calls
        patched = patch_text(source)
        self.assertIn("private_applications", patched)
        self.assertIn("$application_files", patched)
        self.assertIn("original_name", patched)
        self.assertIn("JSON_PRETTY_PRINT", patched)
        self.assertEqual(patch_text(patched), patched)

    def test_current_live_files_upgrade_to_applicant_folders(self):
        from pathlib import Path
        folder = Path(__file__).resolve().parent / "fixtures"
        mailer = patch_mailer((folder / "website_mailer.php").read_text(encoding="utf-8-sig"))
        form = patch_form((folder / "website_lehrstellen.php").read_text(encoding="utf-8-sig"))
        self.assertIn(MARKER, mailer)
        self.assertIn('$uploadOrdner = "uploads/" . $application_id . "/"', mailer)
        self.assertIn('$manifest_path = $uploadOrdner . "application.json"', mailer)
        self.assertIn('"trial_dates" => $schnupperdaten', mailer)
        self.assertIn('name = \'schnupperdaten[]\'', form)
        self.assertIn("mehrere passende Daten", form)
        self.assertIn("Options -Indexes", UPLOADS_HTACCESS)
        self.assertIn('Require all denied', UPLOADS_HTACCESS)
        self.assertEqual(patch_mailer(mailer), mailer)
        self.assertEqual(patch_form(form), form)


if __name__ == "__main__":
    unittest.main()
