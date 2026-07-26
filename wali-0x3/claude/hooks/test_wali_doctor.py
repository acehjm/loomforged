from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wali-doctor.py")
ARCHIVE_ROOT = MODULE_PATH.parents[2]


class WaliDoctorCliTests(unittest.TestCase):
    def _write_executable(self, path: Path, body: str) -> None:
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        path.chmod(0o755)

    def _deployed_project(self, directory: str) -> tuple[Path, dict[str, str]]:
        root = Path(directory)
        project_root = root / "project"
        project_root.mkdir()
        shutil.copy2(ARCHIVE_ROOT / "CLAUDE.md", project_root / "CLAUDE.md")
        shutil.copytree(ARCHIVE_ROOT / "claude", project_root / ".claude")
        shutil.copytree(ARCHIVE_ROOT / "docs", project_root / "docs")
        (project_root / ".svn").mkdir()

        command_log = root / "commands.jsonl"
        fake_bin = root / "bin"
        fake_bin.mkdir()
        self._write_executable(
            fake_bin / "claude",
            """
import json
import os
import sys

with open(os.environ["WALI_TEST_COMMAND_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(["claude", *sys.argv[1:]]) + "\\n")
if sys.argv[1:] == ["--version"]:
    print("2.1.207 (Claude Code)")
    raise SystemExit(0)
if sys.argv[1:] == ["doctor"]:
    print("Claude Code diagnostics passed")
    raise SystemExit(0)
raise SystemExit(2)
""",
        )
        self._write_executable(
            fake_bin / "svn",
            """
import json
import os
import sys

with open(os.environ["WALI_TEST_COMMAND_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(["svn", *sys.argv[1:]]) + "\\n")
args = sys.argv[1:]
if args == ["--version", "--quiet"]:
    print("1.14.2")
    raise SystemExit(0)
if args == ["info", "--show-item", "wc-root"]:
    print(os.environ["WALI_TEST_PROJECT_ROOT"])
    raise SystemExit(0)
if args == [
    "status",
    "--xml",
    "--no-ignore",
    "--config-option",
    "config:miscellany:global-ignores=",
    ".",
]:
    print('''<?xml version="1.0" encoding="UTF-8"?>
<status><target path=".">
  <entry path="build"><wc-status item="ignored" props="none"/></entry>
</target></status>''')
    raise SystemExit(0)
raise SystemExit(2)
""",
        )
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
        environment["WALI_TEST_COMMAND_LOG"] = str(command_log)
        environment["WALI_TEST_PROJECT_ROOT"] = str(project_root.resolve())
        return project_root, environment

    def _snapshot(self, project_root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(project_root).as_posix(): path.read_bytes()
            for path in project_root.rglob("*")
            if path.is_file()
        }

    def test_empty_project_reports_missing_core_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            environment = os.environ.copy()
            environment["PATH"] = ""
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] 项目结构", result.stdout)
        self.assertIn("CLAUDE.md", result.stdout)
        self.assertIn(".claude/settings.json", result.stdout)

    def test_complete_deployment_passes_read_only_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for check_name in (
            "项目结构",
            "Python",
            "Claude Code",
            "Hook 配置",
            "SVN",
            "Goal 契约",
            "工作图",
            "原生 Ignore",
        ):
            self.assertIn(f"[PASS] {check_name}", result.stdout)
        self.assertIn("1 个项目本地产物", result.stdout)
        self.assertIn("0 项失败", result.stdout)

    def test_diagnostics_do_not_write_or_run_mutating_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            before = self._snapshot(project_root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )
            after = self._snapshot(project_root)
            command_log = Path(environment["WALI_TEST_COMMAND_LOG"])
            commands = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)
        self.assertEqual(
            commands,
            [
                ["claude", "--version"],
                ["claude", "doctor"],
                ["svn", "--version", "--quiet"],
                ["svn", "info", "--show-item", "wc-root"],
                [
                    "svn",
                    "status",
                    "--xml",
                    "--no-ignore",
                    "--config-option",
                    "config:miscellany:global-ignores=",
                    ".",
                ],
            ],
        )

    def test_missing_required_hook_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            settings_path = project_root / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            del settings["hooks"]["Stop"]
            settings_path.write_text(
                json.dumps(settings, ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] Hook 配置", result.stdout)
        self.assertIn("Stop", result.stdout)

    def test_incomplete_post_tool_matcher_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            settings_path = project_root / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["hooks"]["PostToolUse"][0]["matcher"] = "Bash"
            settings_path.write_text(
                json.dumps(settings, ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] Hook 配置", result.stdout)
        self.assertIn("PostToolUse matcher", result.stdout)

    def test_unrestricted_post_tool_matcher_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            settings_path = project_root / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            del settings["hooks"]["PostToolUse"][0]["matcher"]
            settings_path.write_text(
                json.dumps(settings, ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[PASS] Hook 配置", result.stdout)

    def test_split_post_tool_matchers_can_cover_required_tools_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            settings_path = project_root / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            handlers = settings["hooks"]["PostToolUse"][0]["hooks"]
            settings["hooks"]["PostToolUse"] = [
                {"matcher": "Bash|Write", "hooks": handlers},
                {
                    "matcher": "Edit|MultiEdit|NotebookEdit",
                    "hooks": handlers,
                },
            ]
            settings_path.write_text(
                json.dumps(settings, ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[PASS] Hook 配置", result.stdout)

    def test_nested_directory_is_not_accepted_as_svn_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            environment["WALI_TEST_PROJECT_ROOT"] = str(project_root.parent.resolve())
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] SVN", result.stdout)
        self.assertIn("不是 SVN 工作副本根", result.stdout)
        self.assertIn("[WARN] 原生 Ignore", result.stdout)

    def test_invalid_goal_schema_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, environment = self._deployed_project(directory)
            goal_path = project_root / "docs" / "wali-0x3" / "goal.md"
            goal_path.write_text(
                goal_path.read_text(encoding="utf-8").replace(
                    "wali_schema: 1", "wali_schema: 99", 1
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--project-root",
                    str(project_root),
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL] Goal 契约", result.stdout)
        self.assertIn("wali_schema", result.stdout)


if __name__ == "__main__":
    unittest.main()
