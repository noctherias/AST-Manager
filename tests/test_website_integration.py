"""Tests for the reversible website manifest patch."""
import unittest

from tools.enable_website_applications import CALLS, patch_text


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


if __name__ == "__main__":
    unittest.main()
