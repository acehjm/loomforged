"""Deployment-level smoke test for the lightweight wali-0x3 layout."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("wali-doctor.py")
PROJECT_ROOT = SCRIPT.parents[2]
START_SKILL = PROJECT_ROOT / "claude" / "skills" / "wali-start" / "SKILL.md"


class WaliDoctorLightTest(unittest.TestCase):
    def run_doctor(self, project_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(project_root)],
            capture_output=True,
            check=False,
            text=True,
        )

    def test_current_archive_has_a_healthy_lightweight_control_plane(self) -> None:
        result = self.run_doctor(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)
        self.assertIn("goal.md + spec.md + work.md", result.stdout)

    def test_start_skill_defers_persistence_until_goal_and_spec_confirmation(self) -> None:
        skill = START_SKILL.read_text(encoding="utf-8")

        self.assertIn("# 持久化时机", skill)
        self.assertIn("确认前不修改", skill)
        self.assertIn("一次性写入", skill)
        self.assertIn("Behavior Scenarios", skill)
        self.assertIn("不发布到 Issue Tracker", skill)

    def test_doctor_rejects_incomplete_hook_matchers_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(PROJECT_ROOT, project)
            settings_path = project / "claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["hooks"]["PreToolUse"][0]["matcher"] = "Bash"
            settings["hooks"]["PostToolUse"][0]["matcher"] = "Write"
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            (project / "claude" / "agents" / "architect.md").unlink()

            result = self.run_doctor(project)

            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] 布局", result.stdout)
            self.assertIn("[FAIL] Hook 设置", result.stdout)

    def test_doctor_only_warns_when_skill_dynamic_commands_are_locally_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(PROJECT_ROOT, project)
            settings_path = project / "claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["disableSkillShellExecution"] = True
            settings_path.write_text(json.dumps(settings), encoding="utf-8")

            result = self.run_doctor(project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[WARN] Hook 设置", result.stdout)
            self.assertIn("Skill", result.stdout)


if __name__ == "__main__":
    unittest.main()
