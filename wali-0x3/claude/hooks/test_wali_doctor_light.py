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
WALI_AGENT = PROJECT_ROOT / "claude" / "agents" / "wali.md"
INSPECT_SKILL = PROJECT_ROOT / "claude" / "skills" / "wali-inspect" / "SKILL.md"
LEGACY_AGENT_NAMES = (
    "wali-0x3",
    "architect",
    "backend-dev",
    "frontend-dev",
    "reviewer",
    "tester",
    "coordinator",
    "developer",
)


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
        self.assertIn("# 对话到规格的编译规则", skill)
        self.assertIn("默认交付产物只有", skill)
        self.assertNotIn("to-spec", skill.lower())
        self.assertNotIn("Matt", skill)

    def test_deployment_defines_short_named_specialists_with_one_work_writer(self) -> None:
        product = (PROJECT_ROOT / "claude" / "agents" / "product.md").read_text(encoding="utf-8")
        backend = (PROJECT_ROOT / "claude" / "agents" / "backend.md").read_text(encoding="utf-8")
        frontend = (PROJECT_ROOT / "claude" / "agents" / "frontend.md").read_text(encoding="utf-8")
        review = (PROJECT_ROOT / "claude" / "agents" / "review.md").read_text(encoding="utf-8")
        verifier = (PROJECT_ROOT / "claude" / "agents" / "verify.md").read_text(encoding="utf-8")
        wali_agent = WALI_AGENT.read_text(encoding="utf-8")
        settings = json.loads(
            (PROJECT_ROOT / "claude" / "settings.json").read_text(encoding="utf-8")
        )

        for legacy_name in LEGACY_AGENT_NAMES:
            self.assertFalse(
                (PROJECT_ROOT / "claude" / "agents" / f"{legacy_name}.md").exists()
            )
        self.assertEqual(settings.get("agent"), "wali")
        self.assertIn("name: wali", wali_agent)
        self.assertIn("name: product", product)
        self.assertIn("tools: Read, Glob, Grep, Bash", product)
        self.assertNotIn("Write", product.split("---", 2)[1])
        self.assertNotIn("Edit", product.split("---", 2)[1])
        self.assertIn("name: backend", backend)
        self.assertIn("name: frontend", frontend)
        self.assertIn("不自行更新 Work", backend)
        self.assertIn("不自行更新 Work", frontend)
        self.assertIn("tools: Read, Glob", review)
        self.assertIn("tools: Read, Glob", verifier)
        self.assertIn("不修改", review)
        self.assertIn("不修改", verifier)
        self.assertIn("从用户体验倒推", product)
        self.assertIn("聚焦", product)
        self.assertIn("不模仿乔布斯", product)
        self.assertIn("不拥有 Goal", product)
        self.assertIn("product", wali_agent)
        self.assertIn("backend", wali_agent)
        self.assertIn("frontend", wali_agent)
        self.assertIn("最多两个", wali_agent)

        for name in (
            "wali",
            "product",
            "arch",
            "backend",
            "frontend",
            "review",
            "verify",
        ):
            with self.subTest(agent=name):
                definition = (
                    PROJECT_ROOT / "claude" / "agents" / f"{name}.md"
                ).read_text(encoding="utf-8")
                self.assertIn("## 身份", definition)
                self.assertIn("wali-0x3", definition)

    def test_doctor_rejects_legacy_agent_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(PROJECT_ROOT, project)
            for name in LEGACY_AGENT_NAMES:
                legacy = project / "claude" / "agents" / f"{name}.md"
                legacy.write_text(f"---\nname: {name}\n---\n", encoding="utf-8")

            result = self.run_doctor(project)

            self.assertEqual(result.returncode, 1)
            for name in LEGACY_AGENT_NAMES:
                self.assertIn(f"{name}.md", result.stdout)

    def test_doctor_rejects_an_agent_without_identity_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(PROJECT_ROOT, project)
            wali_agent = project / "claude" / "agents" / "wali.md"
            wali_agent.write_text(
                wali_agent.read_text(encoding="utf-8").replace("## 身份", "## 简介"),
                encoding="utf-8",
            )

            result = self.run_doctor(project)

            self.assertEqual(result.returncode, 1)
            self.assertIn("身份契约", result.stdout)
            self.assertIn("wali.md", result.stdout)

    def test_done_contract_persists_terminal_state_before_final_check(self) -> None:
        skill = INSPECT_SKILL.read_text(encoding="utf-8")

        terminal = "先在同一编辑回合将 phase 设为 `done`"
        final_check = "再立即运行 `wali_work.py check --checkpoint done`"
        self.assertIn(terminal, skill)
        self.assertIn(final_check, skill)
        self.assertLess(skill.index(terminal), skill.index(final_check))

    def test_doctor_rejects_incomplete_hook_matchers_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(PROJECT_ROOT, project)
            settings_path = project / "claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["hooks"]["PreToolUse"][0]["matcher"] = "Bash"
            settings["hooks"]["PostToolUse"][0]["matcher"] = "Write"
            settings["hooks"].pop("SubagentStart")
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            (project / "claude" / "agents" / "arch.md").unlink()

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
