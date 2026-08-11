"""Deployment-level smoke test for the lightweight wali-0x3 layout."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("wali-doctor.py")
PROJECT_ROOT = SCRIPT.parents[2]


class WaliDoctorLightTest(unittest.TestCase):
    def test_current_archive_has_a_healthy_lightweight_control_plane(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(PROJECT_ROOT)],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)
        self.assertIn("goal.md + work.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
