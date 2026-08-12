"""Behavior tests for wali-0x3's narrow policy boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_wali_liveness import GOAL, SPEC, WORK


SCRIPT = Path(__file__).with_name("wali_policy.py")
WORK_SCRIPT = Path(__file__).with_name("wali_work.py")
SETTINGS = SCRIPT.parents[1] / "settings.json"


class WaliPolicyLightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        (self.state / "goal.md").write_text(GOAL, encoding="utf-8")
        (self.state / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.state / "work.md").write_text(WORK, encoding="utf-8")

    def tearDown(self) -> None:
        subprocess.run(
            [
                sys.executable,
                str(WORK_SCRIPT),
                "--project-root",
                str(self.root),
                "clear-claims",
                "--all-agents-stopped",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        self.temporary_directory.cleanup()

    def hook(
        self,
        tool_name: str,
        tool_input: dict[str, object],
        **identity: str,
    ) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(self.root), "hook"],
            input=json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    **identity,
                },
                ensure_ascii=False,
            ),
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def decision(
        self,
        tool_name: str,
        tool_input: dict[str, object],
        **identity: str,
    ) -> dict[str, str]:
        output = json.loads(self.hook(tool_name, tool_input, **identity))["hookSpecificOutput"]
        return {
            "decision": output["permissionDecision"],
            "reason": output.get("permissionDecisionReason", ""),
        }

    def lifecycle(self, command: str, agent_id: str, agent_type: str) -> dict[str, object]:
        result = subprocess.run(
            [
                sys.executable,
                str(WORK_SCRIPT),
                "--project-root",
                str(self.root),
                command,
            ],
            input=json.dumps(
                {
                    "hook_event_name": "SubagentStart" if command == "claim-hook" else "SubagentStop",
                    "session_id": "session-test",
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                }
            ),
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout else {}

    def clear_claims(self) -> str:
        result = subprocess.run(
            [
                sys.executable,
                str(WORK_SCRIPT),
                "--project-root",
                str(self.root),
                "clear-claims",
                "--all-agents-stopped",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write_parallel_state(self, *, same_role: bool = False) -> None:
        spec = SPEC.replace(
            "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | `src/feature/**` |",
            "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | "
            "`src/backend/**`, `src/frontend/**` |",
        )
        second_owner = "backend-dev" if same_role else "frontend-dev"
        work = WORK.replace("active_task: T-001", "active_task: T-001, T-002").replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | backend-dev | none |",
            "| T-001 | AC-001 | 实现后端 | working | none | `src/backend/**` | none | backend-dev | none |\n"
            f"| T-002 | AC-001 | 实现前端 | working | none | `src/frontend/**` | none | {second_owner} | none |",
        )
        (self.state / "spec.md").write_text(spec, encoding="utf-8")
        (self.state / "work.md").write_text(work, encoding="utf-8")

    def test_implementation_writes_allow_active_scope_and_ask_outside_it(self) -> None:
        allowed = self.decision("Write", {"file_path": str(self.root / "src/feature/new.py"), "content": ""})
        outside = self.decision("Write", {"file_path": str(self.root / "src/other.py"), "content": ""})

        self.assertEqual(allowed["decision"], "allow")
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
            self.decision("Write", {"file_path": str(self.root / "src/feature/next.py"), "content": ""})["decision"],
            "allow",
        )

    def test_parallel_subagents_claim_distinct_tasks_and_only_write_their_scope(self) -> None:
        self.write_parallel_state()
        backend_claim = self.lifecycle("claim-hook", "agent-back", "backend-dev")
        frontend_claim = self.lifecycle("claim-hook", "agent-front", "frontend-dev")

        self.assertIn("T-001", json.dumps(backend_claim, ensure_ascii=False))
        self.assertIn("T-002", json.dumps(frontend_claim, ensure_ascii=False))
        backend = {
            "session_id": "session-test",
            "agent_id": "agent-back",
            "agent_type": "backend-dev",
        }
        frontend = {
            "session_id": "session-test",
            "agent_id": "agent-front",
            "agent_type": "frontend-dev",
        }
        self.assertEqual(
            self.decision("Write", {"file_path": str(self.root / "src/backend/app.py")}, **backend)["decision"],
            "allow",
        )
        self.assertEqual(
            self.decision("Write", {"file_path": str(self.root / "src/frontend/app.ts")}, **frontend)["decision"],
            "allow",
        )
        crossed = self.decision(
            "Write",
            {"file_path": str(self.root / "src/frontend/stolen.ts")},
            **backend,
        )
        self.assertEqual(crossed["decision"], "deny")
        self.assertIn("T-001", crossed["reason"])
        crossed_bash = self.decision(
            "Bash",
            {"command": "touch src/frontend/stolen-by-shell.ts"},
            **backend,
        )
        self.assertEqual(crossed_bash["decision"], "deny")

        state_write = self.decision(
            "Edit",
            {"file_path": str(self.state / "work.md")},
            **backend,
        )
        self.assertEqual(state_write["decision"], "deny")
        self.assertIn("Coordinator", state_write["reason"])
        state_bash = self.decision(
            "Bash",
            {"command": f"printf x > {self.state / 'work.md'}"},
            **backend,
        )
        self.assertEqual(state_bash["decision"], "deny")

        svn = self.decision(
            "Bash",
            {"command": "svn add src/backend/new.py"},
            **backend,
        )
        svn_commit = self.decision(
            "Bash",
            {"command": "svn commit -m 'deliver' src/backend"},
            **backend,
        )
        self.assertEqual(svn["decision"], "deny")
        self.assertEqual(svn_commit["decision"], "deny")
        self.assertIn("SVN", svn["reason"])
        for command in ("git reset --hard HEAD~1", "git clean -fd"):
            with self.subTest(command=command):
                destructive = self.decision("Bash", {"command": command}, **backend)
                self.assertEqual(destructive["decision"], "deny")
                self.assertIn("Subagent", destructive["reason"])

        self.lifecycle("release-hook", "agent-back", "backend-dev")
        released = self.decision(
            "Write",
            {"file_path": str(self.root / "src/backend/after.py")},
            **backend,
        )
        self.assertEqual(released["decision"], "deny")

    def test_claim_is_invalidated_if_current_owner_changes(self) -> None:
        self.write_parallel_state()
        self.lifecycle("claim-hook", "agent-back", "backend-dev")
        work = self.state / "work.md"
        work.write_text(
            work.read_text(encoding="utf-8").replace(
                "| T-001 | AC-001 | 实现后端 | working | none | `src/backend/**` | none | backend-dev | none |",
                "| T-001 | AC-001 | 实现后端 | working | none | `src/backend/**` | none | frontend-dev | none |",
            ),
            encoding="utf-8",
        )

        result = self.decision(
            "Write",
            {"file_path": str(self.root / "src/backend/after-owner-change.py")},
            session_id="session-test",
            agent_id="agent-back",
            agent_type="backend-dev",
        )

        self.assertEqual(result["decision"], "deny")
        self.assertIn("未认领", result["reason"])

    def test_coordinator_can_clear_stale_claims_after_all_agents_stop(self) -> None:
        self.write_parallel_state(same_role=True)
        self.lifecycle("claim-hook", "agent-stale", "backend-dev")

        output = self.clear_claims()
        replacement = self.lifecycle("claim-hook", "agent-replacement", "backend-dev")

        self.assertIn("已清理 1", output)
        self.assertIn("T-001", json.dumps(replacement, ensure_ascii=False))

    def test_clear_claims_requires_confirmation_and_is_denied_to_implementation_agents(self) -> None:
        missing_confirmation = subprocess.run(
            [
                sys.executable,
                str(WORK_SCRIPT),
                "--project-root",
                str(self.root),
                "clear-claims",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        denied = self.decision(
            "Bash",
            {
                "command": "python3 .claude/hooks/wali_work.py --project-root . "
                "clear-claims --all-agents-stopped"
            },
            session_id="session-test",
            agent_id="agent-back",
            agent_type="backend-dev",
        )
        denied_api = self.decision(
            "Bash",
            {
                "command": "PYTHONPATH=.claude/hooks python3 -c \"from pathlib import Path; "
                "from wali_work import clear_agent_claims; clear_agent_claims(Path('.'))\""
            },
            session_id="session-test",
            agent_id="agent-back",
            agent_type="backend-dev",
        )

        self.assertNotEqual(missing_confirmation.returncode, 0)
        self.assertIn("--all-agents-stopped", missing_confirmation.stdout)
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("claim", denied["reason"])
        self.assertEqual(denied_api["decision"], "deny")
        self.assertIn("claim", denied_api["reason"])

    def test_named_implementation_agent_without_agent_id_has_no_coordinator_write_access(self) -> None:
        identity = {"agent_type": "backend-dev"}

        state_write = self.decision(
            "Write",
            {"file_path": str(self.state / "work.md")},
            **identity,
        )
        implementation_write = self.decision(
            "Write",
            {"file_path": str(self.root / "src/feature/direct.py")},
            **identity,
        )
        shell_write = self.decision(
            "Bash",
            {"command": "touch src/feature/direct.py"},
            **identity,
        )
        hidden_shell_write = self.decision(
            "Bash",
            {
                "command": "python3 -c \"from pathlib import Path; "
                "Path('docs/wali-0x3/work.md').write_text('stolen')\""
            },
            **identity,
        )

        for result in (
            state_write,
            implementation_write,
            shell_write,
            hidden_shell_write,
        ):
            self.assertEqual(result["decision"], "deny")

    def test_two_backend_instances_atomically_claim_different_tasks(self) -> None:
        self.write_parallel_state(same_role=True)

        first = self.lifecycle("claim-hook", "agent-one", "backend-dev")
        second = self.lifecycle("claim-hook", "agent-two", "backend-dev")

        self.assertIn("T-001", json.dumps(first, ensure_ascii=False))
        self.assertIn("T-002", json.dumps(second, ensure_ascii=False))

    def test_coordinator_must_not_bypass_claim_boundary_with_two_active_tasks(self) -> None:
        self.write_parallel_state()

        result = self.decision(
            "Write",
            {"file_path": str(self.root / "src/backend/direct.py")},
        )

        self.assertEqual(result["decision"], "ask")
        self.assertIn("未认领", result["reason"])

    def test_concurrent_backend_claims_do_not_select_the_same_task(self) -> None:
        self.write_parallel_state(same_role=True)
        command = [
            sys.executable,
            str(WORK_SCRIPT),
            "--project-root",
            str(self.root),
            "claim-hook",
        ]
        processes = [
            subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        for index, process in enumerate(processes, start=1):
            assert process.stdin is not None
            process.stdin.write(
                json.dumps(
                    {
                        "hook_event_name": "SubagentStart",
                        "session_id": "session-concurrent",
                        "agent_id": f"agent-race-{index}",
                        "agent_type": "backend-dev",
                    }
                )
            )
            process.stdin.close()
        outputs = []
        for process in processes:
            process.wait(timeout=5)
            assert process.stdout is not None and process.stderr is not None
            output = process.stdout.read()
            error = process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            self.assertEqual(process.returncode, 0, error)
            outputs.append(output)

        combined = "\n".join(outputs)
        self.assertEqual(combined.count("T-001"), 1)
        self.assertEqual(combined.count("T-002"), 1)

    def test_verify_phase_asks_before_modifying_implementation(self) -> None:
        work = self.state / "work.md"
        work.write_text(work.read_text(encoding="utf-8").replace("phase: work", "phase: verify"), encoding="utf-8")

        decision = self.decision("Edit", {"file_path": str(self.root / "src/feature/app.py")})

        self.assertEqual(decision["decision"], "ask")
        self.assertIn("verify phase", decision["reason"])

    def test_recoverable_destructive_commands_ask_without_blocking_normal_shell(self) -> None:
        for command in (
            "python3 -m unittest -v tests/test_feature.py",
            "python3 -m unittest 2>&1",
            "svn cleanup",
            "curl -f https://example.test/health",
            "curl -x proxy.test https://example.test/health",
            "truncate -s 0 src/feature/cache.txt",
            "touch -t 202608111200 src/feature/cache.txt",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.decision("Bash", {"command": command})["decision"],
                    "allow",
                )

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
        allowed = self.decision(
            "Bash",
            {"command": "python3 check.py && svn add src/feature/new.py"},
        )
        outside = self.decision(
            "Bash",
            {"command": "python3 check.py && svn add src/outside.py"},
        )

        self.assertEqual(allowed["decision"], "allow")
        self.assertEqual(outside["decision"], "ask")

    def test_all_working_copy_svn_mutations_are_denied_to_implementation_agents(self) -> None:
        self.lifecycle("claim-hook", "agent-back", "backend-dev")
        identity = {
            "session_id": "session-test",
            "agent_id": "agent-back",
            "agent_type": "backend-dev",
        }
        commands = (
            "svn patch changes.patch src/feature",
            "svn merge ^/trunk src/feature",
            "svn switch ^/branches/feature src/feature",
            "svn checkout https://svn.example.test/trunk src/feature/checkout",
            "svn export https://svn.example.test/assets src/feature/assets",
            "svn changelist ready src/feature/app.py",
            "svn ps feature-enabled yes src/feature/app.py",
            "svn pd feature-enabled src/feature/app.py",
            "svn pe feature-enabled src/feature/app.py",
            "svn relocate https://old.example.test https://new.example.test src/feature",
            "svn resolved src/feature/app.py",
            "svn upgrade src/feature",
            "SVN_EXPERIMENTAL_COMMANDS=shelf3 svn x-shelve feature src/feature/app.py",
            "SVN_EXPERIMENTAL_COMMANDS=shelf3 svn x-unshelve feature",
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.decision("Bash", {"command": command}, **identity)
                self.assertEqual(result["decision"], "deny")
                self.assertIn("SVN", result["reason"])

    def test_implementation_agents_only_run_explicitly_read_only_svn_commands(self) -> None:
        self.lifecycle("claim-hook", "agent-back", "backend-dev")
        identity = {
            "session_id": "session-test",
            "agent_id": "agent-back",
            "agent_type": "backend-dev",
        }
        commands = (
            "svn status",
            "svn diff --internal-diff src/feature",
            "svn info src/feature",
            "svn log -l 1",
            "svn list ^/trunk",
            "svn propget feature-enabled src/feature/app.py",
            "svn --version",
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.decision("Bash", {"command": command}, **identity)
                self.assertEqual(result["decision"], "allow")

    def test_coordinator_svn_source_operands_do_not_count_as_scope_targets(self) -> None:
        commands = (
            "svn patch changes.patch src/feature",
            "svn patch --strip 1 changes.patch src/feature",
            "svn merge ^/trunk src/feature",
            "svn merge src/source src/feature",
            "svn merge -r 1:2 src/source src/feature",
            "svn switch ^/branches/feature src/feature",
            "svn switch --relocate https://old.example.test https://new.example.test src/feature",
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.decision("Bash", {"command": command})
                self.assertEqual(result["decision"], "allow")

        outside = self.decision(
            "Bash",
            {"command": "svn merge ^/trunk src/outside"},
        )
        implicit_current_directory = self.decision(
            "Bash",
            {"command": "svn merge src/feature/source"},
        )
        cherrypick_implicit_current_directory = self.decision(
            "Bash",
            {"command": "svn merge -r 1:2 src/feature/source"},
        )
        two_source_implicit_current_directory = self.decision(
            "Bash",
            {"command": "svn merge src/source@10 src/other@20"},
        )
        mixed_two_source_implicit_current_directory = self.decision(
            "Bash",
            {"command": "svn merge ^/trunk@10 src/feature/source@20"},
        )
        self.assertEqual(outside["decision"], "ask")
        self.assertIn("Scope", outside["reason"])
        self.assertEqual(implicit_current_directory["decision"], "ask")
        self.assertIn("Scope", implicit_current_directory["reason"])
        self.assertEqual(cherrypick_implicit_current_directory["decision"], "ask")
        self.assertIn("Scope", cherrypick_implicit_current_directory["reason"])
        self.assertEqual(two_source_implicit_current_directory["decision"], "ask")
        self.assertIn("Scope", two_source_implicit_current_directory["reason"])
        self.assertEqual(
            mixed_two_source_implicit_current_directory["decision"],
            "ask",
        )
        self.assertIn(
            "Scope",
            mixed_two_source_implicit_current_directory["reason"],
        )

    def test_local_svn_property_and_mkdir_operations_are_not_remote_writes(self) -> None:
        commands = (
            "svn mkdir src/feature/new-dir",
            "svn propset feature-enabled yes src/feature/app.py",
            "svn propset feature-enabled -F property.txt src/feature/app.py",
            "svn propdel feature-enabled src/feature/app.py",
            "svn propedit --encoding UTF-8 feature-enabled src/feature/app.py",
            "svn update --cl ready src/feature/app.py",
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.decision("Bash", {"command": command})
                self.assertEqual(result["decision"], "allow")

        for command in (
            "svn mkdir ^/branches/new -m 'new branch'",
            "svn propset feature-enabled yes https://svn.example.test/trunk/app.py",
            "svn propset release approved --revprop -r 12 src/feature/app.py",
            "svn propdel release --revprop -r 12 src/feature/app.py",
            "svn propedit release --revprop -r 12 src/feature/app.py",
        ):
            with self.subTest(command=command):
                result = self.decision("Bash", {"command": command})
                self.assertEqual(result["decision"], "ask")
                self.assertIn("外部", result["reason"])

    def test_explicit_shell_file_writes_obey_scope_and_control_plane(self) -> None:
        self.assertEqual(
            self.decision("Bash", {"command": "touch src/feature/new.py"})["decision"],
            "allow",
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
        self.assertEqual(self.decision("Skill", {"skill": "external:example"})["decision"], "allow")
        self.assertEqual(self.decision("Agent", {"description": "delegate"})["decision"], "allow")

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
        self.assertIn("SubagentStart", settings["hooks"])
        self.assertIn("SubagentStop", settings["hooks"])


if __name__ == "__main__":
    unittest.main()
