"""Behavior tests for wali-0x3's narrow policy boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_wali_liveness import GOAL, WORK


SCRIPT = Path(__file__).with_name("wali_policy.py")
SETTINGS = SCRIPT.parents[1] / "settings.json"


class WaliPolicyLightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        (self.state / "goal.md").write_text(GOAL, encoding="utf-8")
        (self.state / "work.md").write_text(WORK, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def hook(self, tool_name: str, tool_input: dict[str, object]) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(self.root), "hook"],
            input=json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                },
                ensure_ascii=False,
            ),
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def decision(self, tool_name: str, tool_input: dict[str, object]) -> dict[str, str]:
        output = json.loads(self.hook(tool_name, tool_input))["hookSpecificOutput"]
        return {
            "decision": output["permissionDecision"],
            "reason": output["permissionDecisionReason"],
        }

    def test_implementation_writes_use_only_the_active_task_scope(self) -> None:
        allowed = self.hook("Write", {"file_path": str(self.root / "src/feature/new.py"), "content": ""})
        denied = self.decision("Write", {"file_path": str(self.root / "src/other.py"), "content": ""})

        self.assertEqual(allowed, "")
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("Scope", denied["reason"])

    def test_verify_phase_cannot_modify_implementation(self) -> None:
        work = self.state / "work.md"
        work.write_text(work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"), encoding="utf-8")

        denied = self.decision("Edit", {"file_path": str(self.root / "src/feature/app.py")})

        self.assertEqual(denied["decision"], "deny")
        self.assertIn("verify phase", denied["reason"])

    def test_destructive_commands_remain_blocked_without_blocking_normal_shell(self) -> None:
        self.assertEqual(self.hook("Bash", {"command": "python3 -m unittest -v tests/test_feature.py"}), "")
        self.assertEqual(self.hook("Bash", {"command": "svn cleanup"}), "")

        denied = self.decision("Bash", {"command": "git reset --hard HEAD~1"})
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("破坏性", denied["reason"])

        cleanup = self.decision("Bash", {"command": "svn cleanup --remove-unversioned"})
        self.assertEqual(cleanup["decision"], "deny")

    def test_external_writes_require_goal_authority_and_live_confirmation(self) -> None:
        denied = self.decision("Bash", {"command": "git push origin main"})
        self.assertEqual(denied["decision"], "deny")

        goal = self.state / "goal.md"
        goal.write_text(
            goal.read_text(encoding="utf-8").replace(
                "allow_external_writes: false",
                "allow_external_writes: true",
            ),
            encoding="utf-8",
        )
        asked = self.decision("Bash", {"command": "git push origin main"})
        self.assertEqual(asked["decision"], "ask")

        chained = self.decision("Bash", {"command": "python3 check.py && git push origin main"})
        self.assertEqual(chained["decision"], "ask")

    def test_settings_skip_read_tools_and_do_not_enable_team_supervision_by_default(self) -> None:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        matcher = settings["hooks"]["PreToolUse"][0]["matcher"]

        self.assertNotIn("Read", matcher)
        self.assertNotIn("Glob", matcher)
        self.assertNotIn("Grep", matcher)
        self.assertNotIn("Skill", matcher)
        self.assertNotIn("Agent", matcher)
        self.assertNotIn("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", settings.get("env", {}))
        for event in ("TeammateIdle", "TaskCompleted", "StopFailure"):
            self.assertNotIn(event, settings["hooks"])


if __name__ == "__main__":
    unittest.main()
