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

    def test_implementation_writes_allow_active_scope_and_ask_outside_it(self) -> None:
        allowed = self.hook("Write", {"file_path": str(self.root / "src/feature/new.py"), "content": ""})
        outside = self.decision("Write", {"file_path": str(self.root / "src/other.py"), "content": ""})

        self.assertEqual(allowed, "")
        self.assertEqual(outside["decision"], "ask")
        self.assertIn("Scope", outside["reason"])

        work = self.state / "work.md"
        work.write_text(
            work.read_text(encoding="utf-8").replace(
                "## Issues\n\n| ID | Task | Acceptance | Severity | Status | Description | Evidence |\n| --- | --- | --- | --- | --- | --- | --- |\n",
                "## Issues\n\n| ID | Task | Acceptance | Severity | Status | Description | Evidence |\n| --- | --- | --- | --- | --- | --- | --- |\n| I-001 | T-999 | AC-001 | medium | open | 稍后修复关系 | none |\n",
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            self.hook("Write", {"file_path": str(self.root / "src/feature/next.py"), "content": ""}),
            "",
        )

    def test_verify_phase_asks_before_modifying_implementation(self) -> None:
        work = self.state / "work.md"
        work.write_text(work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"), encoding="utf-8")

        decision = self.decision("Edit", {"file_path": str(self.root / "src/feature/app.py")})

        self.assertEqual(decision["decision"], "ask")
        self.assertIn("verify phase", decision["reason"])

    def test_recoverable_destructive_commands_ask_without_blocking_normal_shell(self) -> None:
        self.assertEqual(self.hook("Bash", {"command": "python3 -m unittest -v tests/test_feature.py"}), "")
        self.assertEqual(self.hook("Bash", {"command": "python3 -m unittest 2>&1"}), "")
        self.assertEqual(self.hook("Bash", {"command": "svn cleanup"}), "")
        self.assertEqual(self.hook("Bash", {"command": "curl -f https://example.test/health"}), "")
        self.assertEqual(self.hook("Bash", {"command": "curl -x proxy.test https://example.test/health"}), "")
        self.assertEqual(self.hook("Bash", {"command": "truncate -s 0 src/feature/cache.txt"}), "")
        self.assertEqual(self.hook("Bash", {"command": "touch -t 202608111200 src/feature/cache.txt"}), "")

        risky = self.decision("Bash", {"command": "git reset --hard HEAD~1"})
        self.assertEqual(risky["decision"], "ask")
        self.assertIn("高风险", risky["reason"])

        split_flags = self.decision("Bash", {"command": "rm -r -f build"})
        self.assertEqual(split_flags["decision"], "ask")

        svn_options = self.decision("Bash", {"command": "svn --non-interactive revert src/feature/app.py"})
        self.assertEqual(svn_options["decision"], "ask")

        git_options = self.decision("Bash", {"command": "git -C . reset --hard HEAD~1"})
        self.assertEqual(git_options["decision"], "ask")

        cleanup = self.decision("Bash", {"command": "svn cleanup --remove-unversioned"})
        self.assertEqual(cleanup["decision"], "ask")

    def test_external_writes_ask_for_live_confirmation_without_state_toggle(self) -> None:
        commands = (
            "git push origin main",
            "git -C . push origin main",
            "curl --json '{\"ok\":true}' https://example.test",
            "curl --json '{\"text\":\"a|b\"}' https://example.test",
            "env git push origin main",
            "cat payload | ssh deploy.example",
            "(git push origin main)",
            "sh -c 'git push origin main'",
            "time git push origin main",
            "timeout 5 git push origin main",
            "docker --context prod push image:tag",
            "kubectl --context prod apply -f deploy.yaml",
            "kubectl -v 6 apply -f deploy.yaml",
            "kubectl --as admin apply -f deploy.yaml",
            "curl --request=POST https://example.test",
            "curl --data-urlencode a=b https://example.test",
            "python3 check.py && git push origin main",
            "svn add src/outside.py && git push origin main",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision("Bash", {"command": command})["decision"],
                    "ask",
                )

    def test_compound_confirmation_reports_every_detected_risk(self) -> None:
        scoped_external = self.decision(
            "Bash",
            {"command": "touch src/outside.py && svn commit -m 'deliver'"},
        )
        destructive_external = self.decision(
            "Bash",
            {"command": "git reset --hard HEAD~1 && git push origin main"},
        )

        self.assertEqual(scoped_external["decision"], "ask")
        self.assertIn("Scope", scoped_external["reason"])
        self.assertIn("外部", scoped_external["reason"])
        self.assertEqual(destructive_external["decision"], "ask")
        self.assertIn("高风险", destructive_external["reason"])
        self.assertIn("外部", destructive_external["reason"])

    def test_external_effects_ask_without_a_goal_toggle(self) -> None:
        (self.state / "goal.md").unlink()
        (self.state / "work.md").unlink()

        decision = self.decision("Bash", {"command": "svn commit -m 'deliver'"})

        self.assertEqual(decision["decision"], "ask")
        self.assertIn("外部", decision["reason"])

    def test_scope_and_control_plane_exceptions_ask_instead_of_dead_ending(self) -> None:
        outside = self.decision(
            "Write",
            {"file_path": str(self.root / "src/outside.py"), "content": ""},
        )
        control = self.decision(
            "Write",
            {"file_path": str(self.root / "CLAUDE.md"), "content": ""},
        )

        self.assertEqual(outside["decision"], "ask")
        self.assertEqual(control["decision"], "ask")

    def test_recoverable_destructive_commands_ask_but_catastrophic_delete_denies(self) -> None:
        reset = self.decision("Bash", {"command": "git reset --hard HEAD~1"})
        local_delete = self.decision("Bash", {"command": "rm -rf build"})

        self.assertEqual(reset["decision"], "ask")
        self.assertEqual(local_delete["decision"], "ask")
        for command in ("rm -rf /", "rm -rf .", "rm -rf ~", "rm -rf *"):
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision("Bash", {"command": command})["decision"],
                    "deny",
                )

    def test_compound_local_svn_mutations_still_obey_task_scope(self) -> None:
        allowed = self.hook(
            "Bash",
            {"command": "python3 check.py && svn add src/feature/new.py"},
        )
        outside = self.decision(
            "Bash",
            {"command": "python3 check.py && svn add src/outside.py"},
        )

        self.assertEqual(allowed, "")
        self.assertEqual(outside["decision"], "ask")

    def test_explicit_shell_file_writes_obey_scope_and_control_plane(self) -> None:
        self.assertEqual(
            self.hook("Bash", {"command": "touch src/feature/new.py"}),
            "",
        )
        outside = self.decision("Bash", {"command": "touch src/outside.py"})
        control = self.decision("Bash", {"command": "printf x > CLAUDE.md"})
        settings = self.decision("Bash", {"command": "printf x | tee claude/settings.json"})
        quoted = self.decision("Bash", {"command": "printf 'a;b' > src/outside.txt"})
        clobber = self.decision("Bash", {"command": "printf x >| src/outside.txt"})
        sed_many = self.decision(
            "Bash",
            {"command": "sed -i 's/a/b/' CLAUDE.md src/feature/app.py"},
        )
        sed_long = self.decision(
            "Bash",
            {"command": "sed --in-place 's/a/b/' src/outside.py"},
        )
        restore = self.decision("Bash", {"command": "git restore CLAUDE.md"})
        checkout = self.decision("Bash", {"command": "git checkout -- CLAUDE.md"})
        checkout_short = self.decision("Bash", {"command": "git checkout CLAUDE.md"})
        checkout_head = self.decision("Bash", {"command": "git checkout HEAD CLAUDE.md"})
        checkout_force = self.decision("Bash", {"command": "git checkout -f main"})
        cp_target = self.decision(
            "Bash",
            {"command": "cp -t claude src/feature/app.py"},
        )
        mv_target = self.decision(
            "Bash",
            {"command": "mv --target-directory=src/outside src/feature/app.py"},
        )
        install_target = self.decision(
            "Bash",
            {"command": "install -t src/outside src/feature/app.py"},
        )
        ln_target = self.decision(
            "Bash",
            {"command": "ln -t src/outside src/feature/app.py"},
        )

        for decision in (
            outside,
            control,
            settings,
            quoted,
            clobber,
            sed_many,
            sed_long,
            restore,
            checkout,
            checkout_short,
            checkout_head,
            checkout_force,
            cp_target,
            mv_target,
            install_target,
            ln_target,
        ):
            self.assertEqual(decision["decision"], "ask")

        work = self.state / "work.md"
        work.write_text(
            work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"),
            encoding="utf-8",
        )
        verify = self.decision("Bash", {"command": "touch src/feature/verify.py"})
        self.assertEqual(verify["decision"], "ask")

    def test_skill_and_agent_invocation_are_not_restricted_by_wali(self) -> None:
        self.assertEqual(self.hook("Skill", {"skill": "external:example"}), "")
        self.assertEqual(self.hook("Agent", {"description": "delegate"}), "")

    def test_settings_skip_read_tools_and_do_not_enable_team_supervision_by_default(self) -> None:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        matcher = settings["hooks"]["PreToolUse"][0]["matcher"]

        self.assertIs(settings.get("disableSkillShellExecution"), False)
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
