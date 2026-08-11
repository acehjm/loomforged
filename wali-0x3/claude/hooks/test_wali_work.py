"""Black-box tests for wali-0x3 work-state checkpoints."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_wali_liveness import GOAL, WORK


SCRIPT = Path(__file__).with_name("wali_work.py")


class WaliWorkCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        self.write("goal.md", GOAL)
        self.write("work.md", WORK)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.state / name).write_text(content, encoding="utf-8")

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(self.root), *arguments],
            capture_output=True,
            check=False,
            text=True,
        )

    def test_check_accepts_consistent_goal_and_work_state(self) -> None:
        result = self.run_cli("check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("状态检查通过", result.stdout)

    def test_runtime_fields_live_in_work_not_the_stable_goal(self) -> None:
        goal_metadata = GOAL.split("---", 2)[1]
        work_metadata = WORK.split("---", 2)[1]

        for field in ("phase:", "active_task:", "stop_intent:", "waiting_for:", "outcome:"):
            self.assertNotIn(field, goal_metadata)
            self.assertIn(field, work_metadata)

        self.write("goal.md", GOAL.replace("confirmed: true", "confirmed: true\nphase: work"))
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("运行字段", result.stdout)

    def test_check_reports_a_task_dependency_cycle(self) -> None:
        work = WORK.replace(
            "| T-001 | AC-001 | 实现功能 | working | none |",
            "| T-001 | AC-001 | 实现功能 | pending | T-002 |",
        )
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 补充功能 | pending | T-001 | `src/other/**` | none | developer | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("T-001 → T-002 → T-001", result.stdout)

    def test_work_phase_requires_one_real_active_task(self) -> None:
        self.write("work.md", WORK.replace("active_task: T-001", "active_task: T-999"))

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("active_task", result.stdout)

    def test_phase_runtime_fields_are_cross_validated(self) -> None:
        self.write("work.md", WORK.replace("outcome: none", "outcome: completed"))
        outcome = self.run_cli("check")
        self.assertEqual(outcome.returncode, 1)
        self.assertIn("outcome", outcome.stdout)

        paused = WORK.replace("phase: work", "phase: paused").replace(
            "active_task: T-001",
            "active_task: T-999",
        )
        self.write("work.md", paused)
        waiting = self.run_cli("check")
        self.assertEqual(waiting.returncode, 1)
        self.assertIn("waiting_for", waiting.stdout)
        self.assertIn("active_task", waiting.stdout)

    def test_frontier_uses_task_dependencies_without_a_persistent_graph(self) -> None:
        work = WORK.replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | developer | none |",
            "| T-001 | AC-001 | 实现功能 | done | none | `src/feature/**` | test exit 0 | developer | tester |",
        )
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 补充功能 | pending | T-001 | `src/other/**` | none | developer | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("frontier")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-002", result.stdout)
        self.assertNotIn("T-001\t", result.stdout)

    def test_parallel_reports_only_disjoint_frontier_tasks(self) -> None:
        work = WORK.replace("| T-001 | AC-001 | 实现功能 | working |", "| T-001 | AC-001 | 实现功能 | pending |")
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 补充功能 | pending | none | `src/other/**` | none | developer | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("parallel")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-001\tT-002", result.stdout)

    def test_verify_checkpoint_requires_review_state_and_implementation_evidence(self) -> None:
        self.write("work.md", WORK.replace("phase: work", "phase: verify"))

        red = self.run_cli("check", "--checkpoint", "verify")
        self.assertEqual(red.returncode, 1)
        self.assertIn("active_task 必须处于 review", red.stdout)

        work = WORK.replace("phase: work", "phase: verify").replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | developer | none |",
            "| T-001 | AC-001 | 实现功能 | review | none | `src/feature/**` | test exit 0 | developer | none |",
        )
        self.write("work.md", work)
        green = self.run_cli("check", "--checkpoint", "verify")
        self.assertEqual(green.returncode, 0, green.stdout + green.stderr)

    def test_done_checkpoint_requires_all_acceptance_and_independent_verification(self) -> None:
        work = WORK.replace("phase: work", "phase: done").replace("active_task: T-001", "active_task: none").replace("outcome: none", "outcome: completed").replace(
            "| AC-001 | pending | none | none |",
            "| AC-001 | verified | user acceptance | user |",
        ).replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | developer | none |",
            "| T-001 | AC-001 | 实现功能 | done | none | `src/feature/**` | test exit 0 | developer | tester |",
        )
        self.write("work.md", work)

        result = self.run_cli("check", "--checkpoint", "done")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
