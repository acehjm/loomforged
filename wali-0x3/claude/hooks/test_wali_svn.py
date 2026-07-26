"""Behavior tests for WALI's trusted SVN status interface."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wali_svn


class WaliSvnStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_status_disables_personal_global_ignores(self) -> None:
        status_xml = (
            '<?xml version="1.0"?><status><target path="."></target></status>'
        )
        result = subprocess.CompletedProcess(
            args=["svn", "status"],
            returncode=0,
            stdout=status_xml,
            stderr="",
        )

        with patch.object(
            wali_svn.subprocess,
            "run",
            return_value=result,
        ) as run:
            actual = wali_svn.read_status_xml(self.root)

        self.assertEqual(actual, status_xml)
        command = run.call_args.args[0]
        self.assertIn("--no-ignore", command)
        self.assertIn("--config-option", command)
        self.assertIn("config:miscellany:global-ignores=", command)

    def test_status_separates_native_ignored_items_from_auditable_changes(
        self,
    ) -> None:
        status_xml = """<?xml version="1.0"?>
<status><target path=".">
  <entry path="target"><wc-status item="ignored" props="none"/></entry>
  <entry path="src/new.py"><wc-status item="unversioned" props="none"/></entry>
  <entry path="src/app.py"><wc-status item="modified" props="none"/></entry>
</target></status>
"""

        status = wali_svn.classify_status_xml(self.root, status_xml)

        self.assertEqual(status.local_only_changes, (("target", "ignored"),))
        self.assertEqual(
            status.auditable_changes,
            (
                ("src/new.py", "unversioned"),
                ("src/app.py", "modified"),
            ),
        )

    def test_ignored_descendant_of_modified_properties_remains_auditable(
        self,
    ) -> None:
        status_xml = """<?xml version="1.0"?>
<status><target path=".">
  <entry path="module/target"><wc-status item="ignored" props="none"/></entry>
  <entry path="module"><wc-status item="normal" props="modified"/></entry>
</target></status>
"""

        status = wali_svn.classify_status_xml(self.root, status_xml)

        self.assertEqual(status.local_only_changes, ())
        self.assertEqual(
            status.auditable_changes,
            (
                ("module/target", "ignored"),
                ("module", "properties-modified"),
            ),
        )

    def test_ignored_item_with_property_changes_remains_auditable(self) -> None:
        status_xml = """<?xml version="1.0"?>
<status><target path=".">
  <entry path="cache"><wc-status item="ignored" props="modified"/></entry>
</target></status>
"""

        status = wali_svn.classify_status_xml(self.root, status_xml)

        self.assertEqual(status.local_only_changes, ())
        self.assertEqual(status.auditable_changes, (("cache", "ignored"),))

    def test_invalid_status_xml_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            wali_svn.SvnBoundaryError,
            "SVN status XML 无效",
        ):
            wali_svn.classify_status_xml(self.root, "<status>")


if __name__ == "__main__":
    unittest.main()
