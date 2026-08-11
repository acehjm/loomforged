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

    def test_verify_phase_cannot_modify_implementation(self) -> None:
        work = self.state / "work.md"
        work.write_text(work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"), encoding="utf-8")

        denied = self.decision("Edit", {"file_path": str(self.root / "src/feature/app.py")})

        self.assertEqual(denied["decision"], "deny")
        self.assertIn("verify phase", denied["reason"])

    def test_destructive_commands_remain_blocked_without_blocking_normal_shell(self) -> None:
        self.assertEqual(self.hook("Bash", {"command": "python3 -m unittest -v tests/test_feature.py"}), "")
        self.assertEqual(self.hook("Bash", {"command": "python3 -m unittest 2>&1"}), "")
        self.assertEqual(self.hook("Bash", {"command": "svn cleanup"}), "")
        self.assertEqual(self.hook("Bash", {"command": "curl -f https://example.test/health"}), "")
        self.assertEqual(self.hook("Bash", {"command": "curl -x proxy.test https://example.test/health"}), "")
        self.assertEqual(self.hook("Bash", {"command": "truncate -s 0 src/feature/cache.txt"}), "")
        self.assertEqual(self.hook("Bash", {"command": "touch -t 202608111200 src/feature/cache.txt"}), "")

        denied = self.decision("Bash", {"command": "git reset --hard HEAD~1"})
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("破坏性", denied["reason"])

        split_flags = self.decision("Bash", {"command": "rm -r -f build"})
        self.assertEqual(split_flags["decision"], "deny")

        svn_options = self.decision("Bash", {"command": "svn --non-interactive revert src/feature/app.py"})
        self.assertEqual(svn_options["decision"], "deny")

        git_options = self.decision("Bash", {"command": "git -C . reset --hard HEAD~1"})
        self.assertEqual(git_options["decision"], "deny")

        cleanup = self.decision("Bash", {"command": "svn cleanup --remove-unversioned"})
        self.assertEqual(cleanup["decision"], "deny")

    def test_external_writes_require_goal_authority_and_live_confirmation(self) -> None:
        denied = self.decision("Bash", {"command": "git push origin main"})
        self.assertEqual(denied["decision"], "deny")
        self.assertEqual(
            self.decision("Bash", {"command": "git -C . push origin main"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "curl --json '{\"ok\":true}' https://example.test"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "curl --json '{\"text\":\"a|b\"}' https://example.test"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "env git push origin main"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "cat payload | ssh deploy.example"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "(git push origin main)"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "sh -c 'git push origin main'"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "time git push origin main"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "timeout 5 git push origin main"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "docker --context prod push image:tag"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "kubectl --context prod apply -f deploy.yaml"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "kubectl -v 6 apply -f deploy.yaml"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "kubectl --as admin apply -f deploy.yaml"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "curl --request=POST https://example.test"})["decision"],
            "deny",
        )
        self.assertEqual(
            self.decision("Bash", {"command": "curl --data-urlencode a=b https://example.test"})["decision"],
            "deny",
        )

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

        mixed = self.decision(
            "Bash",
            {"command": "svn add src/outside.py && git push origin main"},
        )
        self.assertEqual(mixed["decision"], "deny")

    def test_compound_local_svn_mutations_still_obey_task_scope(self) -> None:
        allowed = self.hook(
            "Bash",
            {"command": "python3 check.py && svn add src/feature/new.py"},
        )
        denied = self.decision(
            "Bash",
            {"command": "python3 check.py && svn add src/outside.py"},
        )

        self.assertEqual(allowed, "")
        self.assertEqual(denied["decision"], "deny")

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

        self.assertEqual(outside["decision"], "deny")
        self.assertEqual(control["decision"], "deny")
        self.assertEqual(settings["decision"], "deny")
        self.assertEqual(quoted["decision"], "deny")
        self.assertEqual(clobber["decision"], "deny")
        self.assertEqual(sed_many["decision"], "deny")
        self.assertEqual(sed_long["decision"], "deny")
        self.assertEqual(restore["decision"], "deny")
        self.assertEqual(checkout["decision"], "deny")
        self.assertEqual(checkout_short["decision"], "deny")
        self.assertEqual(checkout_head["decision"], "deny")
        self.assertEqual(checkout_force["decision"], "deny")
        self.assertEqual(cp_target["decision"], "deny")
        self.assertEqual(mv_target["decision"], "deny")
        self.assertEqual(install_target["decision"], "deny")
        self.assertEqual(ln_target["decision"], "deny")

        work = self.state / "work.md"
        work.write_text(
            work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"),
            encoding="utf-8",
        )
        verify = self.decision("Bash", {"command": "touch src/feature/verify.py"})
        self.assertEqual(verify["decision"], "deny")

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
