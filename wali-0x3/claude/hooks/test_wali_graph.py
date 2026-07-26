"""Black-box tests for the Markdown-derived WALI work graph CLI."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wali_graph.py")


class WaliGraphCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        self.seed_valid_graph()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.state / name).write_text(content, encoding="utf-8")

    def seed_valid_graph(self) -> None:
        self.write(
            "goal.md",
            """---
wali_schema: 1
goal_id: G-001
status: active
---
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 用户可以保存草稿 | pending | 待补充 |
| AC-02 | human | 用户确认业务结果 | pending | 待用户验收 |
""",
        )
        self.write(
            "spec.md",
            """---
spec_id: SPEC-G-001
goal_id: G-001
source_mode: pressure_test
---
| ID | 类型 | 规范要求 | 来源 | 关联 AC |
| --- | --- | --- | --- | --- |
| R-001 | functional | 系统必须允许用户保存草稿 | 用户需求 | AC-01 |
| R-002 | acceptance | 业务结果必须由用户最终确认 | WALI 约束 | AC-02 |

| AC ID | 判定规则 | 验证方法 |
| --- | --- | --- |
| AC-01 | 保存后可重新读取相同草稿 | 自动测试 |
| AC-02 | 用户确认结果符合业务预期 | 用户回测 |
""",
        )
        self.write(
            "todo.md",
            """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 建立保存路径 | developer | required | done | 无 | `src/api/**` | 接口可保存 | test exit 0 | tester |
| T-002 | AC-01 | 接入保存界面 | developer | required | pending | T-001 | `src/ui/**` | 页面可保存 | 待补充 | 待分配 |
""",
        )
        self.write(
            "issues.md",
            """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
        )
        self.write("handoff.md", "# 可恢复交接\n")

    def run_graph(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                command,
            ],
            capture_output=True,
            check=False,
            text=True,
        )

    def test_check_accepts_a_consistent_traceability_graph(self) -> None:
        result = self.run_graph("check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WALI 工作图检查通过", result.stdout)

    def test_task_skill_must_be_goal_authorized_and_appears_in_the_graph(self) -> None:
        goal = (self.state / "goal.md").read_text(encoding="utf-8")
        self.write(
            "goal.md",
            goal.replace(
                "status: active\n",
                "status: active\nallowed_capabilities:\n  - Skill:compliance-review\n",
            ),
        )
        self.write(
            "todo.md",
            """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 所用 Skill | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 建立保存路径 | developer | required | done | 无 | `src/api/**` | Skill:compliance-review | 接口可保存 | test exit 0 | tester |
| T-002 | AC-01 | 接入保存界面 | developer | required | pending | T-001 | `src/ui/**` | 无 | 页面可保存 | 待补充 | 待分配 |
""",
        )

        allowed = self.run_graph("check")
        rendered = self.run_graph("mermaid")
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        self.assertIn("Skill:compliance-review", rendered.stdout)

        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo.replace("Skill:compliance-review", "Skill:unknown-review"),
        )
        denied = self.run_graph("check")
        self.assertEqual(denied.returncode, 1)
        self.assertIn("未获 Goal 授权", denied.stdout)

    def test_check_requires_the_fixed_spec_artifact(self) -> None:
        (self.state / "spec.md").unlink()

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("spec.md", result.stdout)

    def test_check_rejects_duplicate_spec_frontmatter_keys(self) -> None:
        spec = (self.state / "spec.md").read_text(encoding="utf-8")
        self.write(
            "spec.md",
            spec.replace(
                "spec_id: SPEC-G-001\n",
                "spec_id: SPEC-G-001\nspec_id: SPEC-G-999\n",
            ),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("spec.md frontmatter 含重复字段：spec_id", result.stdout)

    def test_check_rejects_a_requirement_that_references_an_unknown_acceptance_criterion(self) -> None:
        spec = (self.state / "spec.md").read_text(encoding="utf-8")
        self.write("spec.md", spec.replace("| R-001 | functional | 系统必须允许用户保存草稿 | 用户需求 | AC-01 |", "| R-001 | functional | 系统必须允许用户保存草稿 | 用户需求 | AC-99 |"))

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("R-001 引用了不存在的验收条件 AC-99", result.stdout)

    def test_check_rejects_an_acceptance_criterion_without_a_requirement(self) -> None:
        spec = (self.state / "spec.md").read_text(encoding="utf-8")
        self.write(
            "spec.md",
            spec.replace(
                "| R-002 | acceptance | 业务结果必须由用户最终确认 | WALI 约束 | AC-02 |\n",
                "",
            ),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-02 没有任何关联需求", result.stdout)

    def test_check_rejects_an_acceptance_criterion_without_a_spec_oracle(self) -> None:
        spec = (self.state / "spec.md").read_text(encoding="utf-8")
        self.write(
            "spec.md",
            spec.replace(
                "| AC-02 | 用户确认结果符合业务预期 | 用户回测 |\n",
                "",
            ),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-02 缺少规格判定规则", result.stdout)

    def test_check_rejects_a_task_that_references_an_unknown_acceptance_criterion(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write("todo.md", todo.replace("| T-002 | AC-01 |", "| T-002 | AC-99 |"))

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("T-002 引用了不存在的验收条件 AC-99", result.stdout)

    def test_check_rejects_done_tasks_without_evidence_or_independent_verifier(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo.replace("| developer | required | done |", "| tester | required | done |")
            .replace("| test exit 0 | tester |", "| 待补充 | tester |"),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("T-001 已标记 done，但缺少执行结果/证据", result.stdout)
        self.assertIn("独立验证者必须与负责人不同", result.stdout)

    def test_check_rejects_verified_acceptance_without_evidence_and_completed_required_task(self) -> None:
        goal = (self.state / "goal.md").read_text(encoding="utf-8")
        self.write(
            "goal.md",
            goal.replace(
                "| AC-01 | automatic | 用户可以保存草稿 | pending | 待补充 |",
                "| AC-01 | automatic | 用户可以保存草稿 | verified | 待补充 |",
            ),
        )
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo.replace(
                "| T-001 | AC-01 | 建立保存路径 | developer | required | done |",
                "| T-001 | AC-01 | 建立保存路径 | developer | optional | done |",
            ),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-01 已标记 verified，但缺少证据", result.stdout)
        self.assertIn("没有关联已完成的 required 任务", result.stdout)

    def test_check_reports_malformed_node_ids_and_relation_tokens(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write("todo.md", todo.replace("| T-002 |", "| TASK-002 |"))

        malformed_id = self.run_graph("check")

        self.assertEqual(malformed_id.returncode, 1)
        self.assertIn("任务 ID 格式无效：TASK-002", malformed_id.stdout)

        self.seed_valid_graph()
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo.replace("| T-002 | AC-01 |", "| T-002 | AC-01, AC-OOPS |"),
        )

        malformed_relation = self.run_graph("check")

        self.assertEqual(malformed_relation.returncode, 1)
        self.assertIn("T-002 的关联 AC 含无效内容：AC-OOPS", malformed_relation.stdout)

    def test_check_rejects_a_cycle_in_task_dependencies(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo.replace(
                "| T-001 | AC-01 | 建立保存路径 | developer | required | done | 无 |",
                "| T-001 | AC-01 | 建立保存路径 | developer | required | done | T-002 |",
            ),
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("任务依赖存在环：T-001 → T-002 → T-001", result.stdout)

    def test_frontier_lists_pending_tasks_whose_dependencies_are_done(self) -> None:
        result = self.run_graph("frontier")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-002 接入保存界面", result.stdout)
        self.assertNotIn("T-001 建立保存路径", result.stdout)

    def test_frontier_refuses_to_schedule_an_invalid_graph(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write("todo.md", todo.replace("| T-002 | AC-01 |", "| T-002 | AC-99 |"))

        result = self.run_graph("frontier")

        self.assertEqual(result.returncode, 1)
        self.assertIn("T-002 引用了不存在的验收条件 AC-99", result.stdout)

    def test_frontier_excludes_a_task_with_an_open_blocker(self) -> None:
        self.write(
            "issues.md",
            """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-001 | reviewer | T-002 | AC-01 | blocker | open | 保存协议未确定 | coordinator | 规格冲突 | 待分配 | 待验证 |
""",
        )

        result = self.run_graph("frontier")

        self.assertEqual(result.returncode, 0)
        self.assertIn("当前没有可执行任务", result.stdout)

    def test_parallel_lists_frontier_tasks_with_disjoint_file_scopes(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo
            + "| T-003 | AC-01 | 补充使用说明 | developer | required | pending | 无 | `docs/**` | 文档完整 | 待补充 | 待分配 |\n",
        )

        result = self.run_graph("parallel")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("T-002 + T-003", result.stdout)

    def test_parallel_rejects_tasks_with_overlapping_file_scopes(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo
            + "| T-003 | AC-01 | 调整保存提示 | developer | required | pending | 无 | `src/ui/components/**` | 提示正确 | 待补充 | 待分配 |\n",
        )

        result = self.run_graph("parallel")

        self.assertEqual(result.returncode, 0)
        self.assertIn("当前没有可安全并行的任务组合", result.stdout)

    def test_parallel_treats_ambiguous_or_aliasing_scopes_as_overlapping(self) -> None:
        cases = (
            ("`src/a*.py`", "`src/ab*.py`"),
            ("待确定", "另行确认"),
            ("前端相关文件", "后端相关文件"),
            ("`src/a/../ui/**`", "`src/ui/**`"),
        )
        for left_scope, right_scope in cases:
            with self.subTest(left_scope=left_scope, right_scope=right_scope):
                self.seed_valid_graph()
                todo = (self.state / "todo.md").read_text(encoding="utf-8")
                todo = todo.replace("`src/ui/**`", left_scope)
                self.write(
                    "todo.md",
                    todo
                    + f"| T-003 | AC-01 | 并行候选 | developer | required | pending | 无 | {right_scope} | 完成 | 待补充 | 待分配 |\n",
                )

                result = self.run_graph("parallel")

                if left_scope in {"待确定", "前端相关文件"}:
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("允许修改范围过宽或无效", result.stdout)
                else:
                    self.assertEqual(result.returncode, 0)
                    self.assertIn("当前没有可安全并行的任务组合", result.stdout)

    def test_check_rejects_project_root_and_control_plane_scopes(self) -> None:
        for scope in (
            "`**`",
            "`.claude/**`",
            "`claude/**`",
            "`.svn/wali-policy/**`",
            "`CLAUDE.md`",
        ):
            with self.subTest(scope=scope):
                self.seed_valid_graph()
                todo = (self.state / "todo.md").read_text(encoding="utf-8")
                self.write("todo.md", todo.replace("`src/ui/**`", scope))

                result = self.run_graph("check")

                self.assertEqual(result.returncode, 1)
                self.assertIn("允许修改范围", result.stdout)

    def test_mermaid_renders_goal_work_coordination_and_evidence_edges(self) -> None:
        result = self.run_graph("mermaid")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("flowchart LR", result.stdout)
        self.assertIn('G_001["G-001"] -->|包含需求| R_001', result.stdout)
        self.assertIn("R_001 -->|定义验收| AC_01", result.stdout)
        self.assertIn("T_001 -->|阻塞| T_002", result.stdout)
        self.assertIn("AGENT_DEVELOPER -->|负责| T_001", result.stdout)
        self.assertIn("T_001 -->|证据| E_T_001", result.stdout)

    def test_check_rejects_an_automatic_criterion_without_a_task(self) -> None:
        goal = (self.state / "goal.md").read_text(encoding="utf-8")
        self.write(
            "goal.md",
            goal
            + "| AC-03 | automatic | 保存失败时显示错误 | pending | 待补充 |\n",
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-03 没有任何关联任务", result.stdout)

    def test_check_rejects_working_tasks_with_overlapping_file_scopes(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        todo = todo.replace("| T-002 | AC-01 | 接入保存界面 | developer | required | pending |", "| T-002 | AC-01 | 接入保存界面 | developer | required | working |")
        self.write(
            "todo.md",
            todo
            + "| T-003 | AC-01 | 调整保存提示 | developer | required | working | T-001 | `src/ui/components/**` | 提示正确 | 待补充 | 待分配 |\n",
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("working 任务 T-002 与 T-003 的允许修改范围重叠", result.stdout)

    def test_check_rejects_duplicate_node_ids(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo
            + "| T-002 | AC-01 | 重复任务 | developer | required | pending | T-001 | `src/other/**` | 不应存在 | 待补充 | 待分配 |\n",
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("任务 ID 重复：T-002", result.stdout)

    def test_check_rejects_a_main_table_row_with_an_empty_id(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        self.write(
            "todo.md",
            todo
            + "|  | AC-01 | 遗漏编号的任务 | developer | required | pending | 无 | "
            "`src/other/**` | 不应被忽略 | 待补充 | 待分配 |\n",
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("任务 ID 格式无效", result.stdout)

    def test_check_rejects_an_issue_without_a_stable_relation(self) -> None:
        self.write(
            "issues.md",
            """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-001 | reviewer | 无 | 无 | high | open | 无法追踪的问题 | developer | repro | 待分配 | 待验证 |
""",
        )

        result = self.run_graph("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("I-001 没有关联任何任务或验收条件", result.stdout)


if __name__ == "__main__":
    unittest.main()
