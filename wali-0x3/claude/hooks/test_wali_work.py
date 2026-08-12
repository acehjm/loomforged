"""Black-box tests for wali-0x3 work-state checkpoints."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_wali_liveness import GOAL, SPEC, WORK


SCRIPT = Path(__file__).with_name("wali_work.py")


class WaliWorkCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        self.write("goal.md", GOAL)
        self.write("spec.md", SPEC)
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

    def write_parallel_state(
        self,
        *,
        active_task: str = "T-001, T-002",
        second_scope: str = "`src/frontend/**`",
        second_owner: str = "frontend-dev",
        third_task: bool = False,
    ) -> None:
        design_areas = "`src/feature/**`, `src/frontend/**`"
        if third_task:
            design_areas += ", `src/third/**`"
        self.write(
            "spec.md",
            SPEC.replace(
                "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | `src/feature/**` |",
                "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | "
                f"{design_areas} |",
            ),
        )
        tasks = (
            "| T-001 | AC-001 | 实现后端 | working | none | `src/feature/**` | none | backend-dev | none |\n"
            f"| T-002 | AC-001 | 实现前端 | working | none | {second_scope} | none | {second_owner} | none |"
        )
        if third_task:
            tasks += (
                "\n| T-003 | AC-001 | 实现第三任务 | working | none | `src/third/**` | "
                "none | backend-dev | none |"
            )
        work = WORK.replace("active_task: T-001", f"active_task: {active_task}").replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | backend-dev | none |",
            tasks,
        )
        self.write("work.md", work)

    def test_check_accepts_consistent_goal_and_work_state(self) -> None:
        result = self.run_cli("check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("状态检查通过", result.stdout)

    def test_work_checkpoint_requires_an_implementation_ready_spec(self) -> None:
        (self.state / "spec.md").unlink()
        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("spec.md", result.stdout)
        self.assertIn("implementation-ready", result.stdout)

    def test_work_checkpoint_rejects_a_shallow_or_unresolved_spec(self) -> None:
        shallow = SPEC.replace(
            "- Entry points: `src/feature/`\n- Existing behavior: 目标功能尚未实现。\n- Constraints: 保持现有 feature 接口兼容。\n- Evidence: `src/feature/` 与 `python3 -m unittest -v`。",
            "pending",
        ).replace("- none", "- 需要用户决定接口语义")
        self.write("spec.md", shallow)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Current System", result.stdout)
        self.assertIn("Open Questions", result.stdout)

    def test_work_checkpoint_requires_design_and_verification_coverage(self) -> None:
        uncovered = SPEC.replace("| D-001 | R-001 |", "| D-001 | R-999 |").replace(
            "| AC-001 | `src/feature/` 现有集成测试接口 |",
            "| AC-999 | `src/feature/` 现有集成测试接口 |",
        )
        self.write("spec.md", uncovered)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("R-001 没有 Design Mapping", result.stdout)
        self.assertIn("AC-001 没有 Verification Mapping", result.stdout)

    def test_work_checkpoint_requires_concrete_current_and_target_behavior(self) -> None:
        incomplete = SPEC.replace(
            "- Evidence: `src/feature/` 与 `python3 -m unittest -v`。",
            "- Evidence: pending",
        ).replace(
            "- Errors and edges: 非法输入返回明确错误，既有行为不回归。",
            "- Errors and edges: pending",
        )
        self.write("spec.md", incomplete)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Current System", result.stdout)
        self.assertIn("Target Behavior", result.stdout)

    def test_work_checkpoint_requires_behavior_scenarios_covering_every_ac(self) -> None:
        without_scenarios = SPEC.replace(
            "## Behavior Scenarios\n\n"
            "| Scenario | Given | When | Then | Acceptance |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 正常交付 | 有效输入且满足现有前置条件 | 调用方执行目标功能 | "
            "功能产生可观察结果且保持兼容 | AC-001 |\n\n",
            "",
        )
        self.write("spec.md", without_scenarios)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Behavior Scenarios", result.stdout)
        self.assertIn("AC-001", result.stdout)

    def test_work_checkpoint_rejects_hollow_or_unlinked_behavior_scenarios(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace(
                "| 正常交付 | 有效输入且满足现有前置条件 | 调用方执行目标功能 | "
                "功能产生可观察结果且保持兼容 | AC-001 |",
                "| 正常 | pending | 执行 | 完成 | AC-999 |",
            ),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Given/When/Then", result.stdout)
        self.assertIn("引用不存在的 AC-999", result.stdout)
        self.assertIn("AC-001 没有 Behavior Scenario", result.stdout)

    def test_work_checkpoint_requires_a_concrete_verification_seam(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace(
                "| AC-001 | `src/feature/` 现有集成测试接口 | integration 正常交付 |",
                "| AC-001 | 现有最高的集成测试接口 | integration 正常交付 |",
            ),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Verification Mapping", result.stdout)
        self.assertIn("Seam", result.stdout)

    def test_work_checkpoint_rejects_untraceable_evidence_and_vague_design(self) -> None:
        vague = SPEC.replace(
            "- Evidence: `src/feature/` 与 `python3 -m unittest -v`。",
            "- Evidence: `看过`",
        ).replace(
            "在现有 feature 接口后实现最小完整行为。",
            "改代码",
        )
        self.write("spec.md", vague)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("可定位 Evidence", result.stdout)
        self.assertIn("实现设计过于含糊", result.stdout)

    def test_work_checkpoint_rejects_hollow_behavior_and_autonomy_contract(self) -> None:
        hollow = (
            SPEC.replace("目标功能尚未实现。", "正常")
            .replace("保持现有 feature 接口兼容。", "兼容")
            .replace("实现用户要求的功能并保持现有接口兼容。", "正常")
            .replace("非法输入返回明确错误，既有行为不回归。", "处理")
            .replace("保持既有调用方和测试通过。", "兼容")
            .replace("不修改无关模块。", "无")
            .replace(
                "可逆、低影响并遵循现有接口和项目约定的实现细节、局部重构与测试组织。",
                "自行",
            )
            .replace(
                "用户可见语义变化、验收冲突、不可逆数据迁移、重大安全风险或新的外部副作用。",
                "必要时",
            )
            .replace(
                "扩大业务范围、弱化测试、覆盖用户修改或把假设伪装成事实。",
                "别乱来",
            )
            .replace(
                "先用代码、测试和文档消除不确定性；仅携带选项、证据和建议询问一个阻塞问题。",
                "先看看",
            )
        )
        self.write("spec.md", hollow)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Current System", result.stdout)
        self.assertIn("Target Behavior", result.stdout)
        self.assertIn("Autonomous Decision Contract", result.stdout)

    def test_work_checkpoint_requires_verification_to_preserve_the_ac_oracle(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace(
                "`python3 -m unittest -v` |",
                "`printf pass # python3 -m unittest -v` |",
            ),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-001", result.stdout)
        self.assertIn("oracle", result.stdout)

    def test_work_checkpoint_links_every_ac_and_design_area_to_work(self) -> None:
        uncovered_goal = GOAL.replace(
            "| R-001 | 功能可以工作 | AC-001 |",
            "| R-001 | 功能可以工作 | AC-001 |\n| R-002 | 相邻功能可以工作 | AC-002 |",
        ).replace(
            "| AC-001 | 自动检查通过 | `python3 -m unittest -v` |",
            "| AC-001 | 自动检查通过 | `python3 -m unittest -v` |\n| AC-002 | 相邻检查通过 | `python3 -m unittest -v` |",
        )
        uncovered_spec = SPEC.replace(
            "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | `src/feature/**` |",
            "| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | `src/feature/**` |\n| D-002 | R-002 | 在相邻接口后实现完整行为并处理失败。 | `src/other/**` |",
        ).replace(
            "| AC-001 | `src/feature/` 现有集成测试接口 | integration 正常交付 | `python3 -m unittest -v` |",
            "| AC-001 | `src/feature/` 现有集成测试接口 | integration 正常交付 | `python3 -m unittest -v` |\n"
            "| AC-002 | `src/other/` 现有集成测试接口 | integration 相邻功能 | `python3 -m unittest -v` |",
        )
        uncovered_work = WORK.replace(
            "| AC-001 | pending | none | none |",
            "| AC-001 | pending | none | none |\n| AC-002 | pending | none | none |",
        ).replace("`src/feature/**`", "`src/unrelated/**`")
        self.write("goal.md", uncovered_goal)
        self.write("spec.md", uncovered_spec)
        self.write("work.md", uncovered_work)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-002 没有 Task", result.stdout)
        self.assertIn("D-001", result.stdout)
        self.assertIn("Task Scope", result.stdout)

    def test_work_checkpoint_rejects_task_scope_not_authorized_by_design(self) -> None:
        self.write(
            "work.md",
            WORK.replace("`src/feature/**`", "`src/feature/**`, `src/unrelated/**`"),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("src/unrelated/**", result.stdout)
        self.assertIn("Design", result.stdout)

    def test_work_checkpoint_rejects_same_prefix_but_different_globs(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace("`src/feature/**` |", "`src/feature/*.py` |"),
        )
        self.write(
            "work.md",
            WORK.replace("`src/feature/**`", "`src/feature/*.js`"),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("src/feature/*.js", result.stdout)
        self.assertIn("Design", result.stdout)

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
            "\n| T-002 | AC-001 | 补充功能 | pending | T-001 | `src/other/**` | none | backend-dev | none |\n\n## Issues",
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
        self.write(
            "spec.md",
            SPEC.replace("`src/feature/**` |", "`src/feature/**`, `src/other/**` |"),
        )
        work = WORK.replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | backend-dev | none |",
            "| T-001 | AC-001 | 实现功能 | done | none | `src/feature/**` | test exit 0 | backend-dev | tester |",
        ).replace("active_task: T-001", "active_task: none")
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 补充功能 | pending | T-001 | `src/other/**` | none | backend-dev | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("frontier")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-002", result.stdout)
        self.assertNotIn("T-001\t", result.stdout)

    def test_parallel_reports_only_disjoint_frontier_tasks(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace("`src/feature/**` |", "`src/feature/**`, `src/other/**` |"),
        )
        work = WORK.replace("| T-001 | AC-001 | 实现功能 | working |", "| T-001 | AC-001 | 实现功能 | pending |").replace(
            "active_task: T-001", "active_task: none"
        )
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 补充功能 | pending | none | `src/other/**` | none | backend-dev | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("parallel")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-001\tT-002", result.stdout)

    def test_work_checkpoint_allows_two_disjoint_active_implementation_tasks(self) -> None:
        self.write_parallel_state()

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_work_checkpoint_rejects_coordinator_in_a_dual_active_set(self) -> None:
        self.write_parallel_state(second_owner="coordinator")

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("双 active Task", result.stdout)
        self.assertIn("实现 Agent", result.stdout)

    def test_parallel_never_reports_a_coordinator_task(self) -> None:
        self.write(
            "spec.md",
            SPEC.replace(
                "`src/feature/**` |",
                "`src/feature/**`, `src/integration/**` |",
            ),
        )
        work = WORK.replace(
            "| T-001 | AC-001 | 实现功能 | working |",
            "| T-001 | AC-001 | 实现功能 | pending |",
        ).replace("active_task: T-001", "active_task: none")
        work = work.replace(
            "\n## Issues",
            "\n| T-002 | AC-001 | 串行集成 | pending | none | `src/integration/**` | "
            "none | coordinator | none |\n\n## Issues",
        )
        self.write("work.md", work)

        result = self.run_cli("parallel")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_work_checkpoint_rejects_overlapping_or_more_than_two_active_tasks(self) -> None:
        self.write_parallel_state(second_scope="`src/feature/ui/**`")
        overlapping = self.run_cli("check", "--checkpoint", "work")
        self.assertEqual(overlapping.returncode, 1)
        self.assertIn("Scope 重叠", overlapping.stdout)

        self.write_parallel_state(active_task="T-001, T-002, T-003", third_task=True)
        too_many = self.run_cli("check", "--checkpoint", "work")
        self.assertEqual(too_many.returncode, 1)
        self.assertIn("最多两个 active Task", too_many.stdout)

    def test_active_task_requires_exact_unique_comma_separated_ids(self) -> None:
        for invalid in ("garbage T-001 trailing", "T-001, T-001", "none, T-001"):
            with self.subTest(invalid=invalid):
                self.write("work.md", WORK.replace("active_task: T-001", f"active_task: {invalid}"))
                result = self.run_cli("check")
                self.assertEqual(result.returncode, 1)
                self.assertIn("active_task", result.stdout)

    def test_task_owner_must_name_a_deployable_implementation_role(self) -> None:
        self.write(
            "work.md",
            WORK.replace("| backend-dev | none |", "| developer | none |"),
        )

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Owner 必须是", result.stdout)

    def test_work_checkpoint_requires_every_working_task_to_be_active(self) -> None:
        self.write_parallel_state(active_task="T-001")

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("T-002", result.stdout)
        self.assertIn("active_task", result.stdout)

    def test_work_checkpoint_requires_working_task_dependencies_to_be_done(self) -> None:
        self.write_parallel_state()
        work = (self.state / "work.md").read_text(encoding="utf-8").replace(
            "| T-002 | AC-001 | 实现前端 | working | none |",
            "| T-002 | AC-001 | 实现前端 | working | T-001 |",
        )
        self.write("work.md", work)

        result = self.run_cli("check", "--checkpoint", "work")

        self.assertEqual(result.returncode, 1)
        self.assertIn("依赖尚未 done", result.stdout)

    def test_verify_checkpoint_requires_review_state_and_implementation_evidence(self) -> None:
        self.write("work.md", WORK.replace("phase: work", "phase: verify"))

        red = self.run_cli("check", "--checkpoint", "verify")
        self.assertEqual(red.returncode, 1)
        self.assertIn("active_task 必须处于 review", red.stdout)

        work = WORK.replace("phase: work", "phase: verify").replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | backend-dev | none |",
            "| T-001 | AC-001 | 实现功能 | review | none | `src/feature/**` | test exit 0 | backend-dev | none |",
        )
        self.write("work.md", work)
        green = self.run_cli("check", "--checkpoint", "verify")
        self.assertEqual(green.returncode, 0, green.stdout + green.stderr)

    def test_done_checkpoint_requires_all_acceptance_and_independent_verification(self) -> None:
        work = WORK.replace("phase: work", "phase: done").replace("active_task: T-001", "active_task: none").replace("outcome: none", "outcome: completed").replace(
            "| AC-001 | pending | none | none |",
            "| AC-001 | verified | user acceptance | user |",
        ).replace(
            "| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | backend-dev | none |",
            "| T-001 | AC-001 | 实现功能 | done | none | `src/feature/**` | test exit 0 | backend-dev | tester |",
        )
        self.write("work.md", work)

        result = self.run_cli("check", "--checkpoint", "done")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
