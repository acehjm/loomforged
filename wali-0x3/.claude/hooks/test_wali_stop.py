from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("wali_stop.py")
SPEC = importlib.util.spec_from_file_location("wali_stop", MODULE_PATH)
assert SPEC and SPEC.loader
wali_stop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wali_stop)


class WaliStopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.state / name).write_text(content, encoding="utf-8")

    def seed(
        self,
        *,
        status: str = "active",
        waiting_for: str = "none",
        waiting_detail: str = "",
        blocked_reason: str = "",
        automatic_status: str = "verified",
        human_status: str = "pending",
        task_owner: str = "developer",
        task_status: str = "done",
        task_verifier: str = "tester",
        issue_status: str = "closed",
        issue_fixer: str = "developer",
        issue_verifier: str = "tester",
        issue_validation: str = "regression pass",
    ) -> None:
        self.write(
            "goal.md",
            f"""---
status: {status}
waiting_for: {waiting_for}
waiting_detail: "{waiting_detail}"
blocked_reason: "{blocked_reason}"
---
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动条件 | {automatic_status} | test exit 0 |
| AC-02 | human | 用户验收 | {human_status} | {'用户确认通过' if human_status == 'verified' else '待用户验收'} |
""",
        )
        self.write(
            "todo.md",
            f"""| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现 | {task_owner} | required | {task_status} | 无 | src | 测试通过 | test exit 0 | {task_verifier} |
""",
        )
        self.write(
            "issues.md",
            f"""| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-001 | tester | T-001 | AC-01 | blocker | {issue_status} | 示例 | {issue_fixer} | repro | {issue_verifier} | {issue_validation} |
""",
        )
        self.write("progress.md", "# 交接快照\n")

    def test_inactive_goal_does_not_gate(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_active_goal_reports_incomplete_automatic_work(self) -> None:
        self.seed(automatic_status="pending", task_status="review", issue_status="open")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("AC-01" in reason for reason in reasons))
        self.assertTrue(any("T-001" in reason for reason in reasons))
        self.assertTrue(any("I-001" in reason for reason in reasons))

    def test_completed_automatic_work_requires_waiting_user_transition(self) -> None:
        self.seed()
        reasons = wali_stop.evaluate_project(self.root)
        self.assertEqual(len(reasons), 1)
        self.assertIn("waiting_user", reasons[0])

    def test_verified_human_acceptance_requires_done_transition(self) -> None:
        self.seed(human_status="verified")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertEqual(len(reasons), 1)
        self.assertIn("done", reasons[0])

    def test_contract_state_aliases_are_rejected(self) -> None:
        self.seed(
            automatic_status="pass",
            human_status="pass",
            task_status="完成",
            issue_status="已关闭",
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("AC-01" in reason for reason in reasons))
        self.assertTrue(any("T-001" in reason for reason in reasons))
        self.assertTrue(any("I-001" in reason for reason in reasons))

    def test_closed_blocker_requires_independent_validation_evidence(self) -> None:
        self.seed(issue_validation="待验证")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("I-001" in reason and "验证结果" in reason for reason in reasons))

    def test_developer_self_check_cannot_complete_required_task(self) -> None:
        self.seed(task_verifier="developer")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("T-001" in reason and "独立验证者" in reason for reason in reasons))

    def test_developer_cannot_self_close_an_issue(self) -> None:
        self.seed(issue_verifier="developer")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("I-001" in reason and "验证者" in reason for reason in reasons))

    def test_tester_cannot_verify_its_own_required_task(self) -> None:
        self.seed(task_owner="tester", task_verifier="tester")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("T-001" in reason and "负责人不同" in reason for reason in reasons))

    def test_reviewer_cannot_verify_its_own_issue_fix(self) -> None:
        self.seed(issue_fixer="reviewer", issue_verifier="reviewer")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("I-001" in reason and "修复负责人不同" in reason for reason in reasons))

    def test_escaped_pipe_in_issue_cell_does_not_hide_blocker(self) -> None:
        self.seed(issue_status="open")
        issues = (self.state / "issues.md").read_text(encoding="utf-8")
        (self.state / "issues.md").write_text(
            issues.replace("示例", r"bad \| impact"), encoding="utf-8"
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("I-001" in reason for reason in reasons))

    def test_pipe_inside_inline_code_does_not_hide_blocker(self) -> None:
        self.seed(issue_status="open")
        issues = (self.state / "issues.md").read_text(encoding="utf-8")
        (self.state / "issues.md").write_text(
            issues.replace("示例", "`left | right`"), encoding="utf-8"
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("I-001" in reason for reason in reasons))

    def test_waiting_for_direction_requires_a_recorded_question(self) -> None:
        self.seed(status="waiting_user", task_status="working")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("waiting_for" in reason for reason in reasons))

    def test_valid_direction_wait_allows_an_incomplete_increment_to_stop(self) -> None:
        self.seed(
            status="waiting_user",
            waiting_for="direction",
            waiting_detail="请用户选择兼容方案 A 或 B",
            automatic_status="pending",
            task_status="working",
        )
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_acceptance_wait_still_enforces_automatic_gates(self) -> None:
        self.seed(
            status="waiting_user",
            waiting_for="acceptance",
            waiting_detail="请执行业务回测",
            automatic_status="pending",
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("AC-01" in reason for reason in reasons))

    def test_valid_acceptance_wait_allows_pending_human_criterion(self) -> None:
        self.seed(
            status="waiting_user",
            waiting_for="acceptance",
            waiting_detail="请执行业务回测",
        )
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_blocked_goal_requires_a_recorded_reason(self) -> None:
        self.seed(status="blocked", task_status="blocked")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("blocked_reason" in reason for reason in reasons))

    def test_recorded_block_allows_stopping_without_claiming_completion(self) -> None:
        self.seed(
            status="blocked",
            blocked_reason="缺少外部系统访问权限",
            task_status="blocked",
        )
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_malformed_table_row_is_reported_instead_of_dropped(self) -> None:
        self.seed(issue_status="open")
        issues = (self.state / "issues.md").read_text(encoding="utf-8")
        (self.state / "issues.md").write_text(
            issues.replace("示例", "bad | unescaped"), encoding="utf-8"
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("issues.md" in reason and "列数错误" in reason for reason in reasons))

    def test_done_goal_still_enforces_completion_gates(self) -> None:
        self.seed(status="done", automatic_status="pending", issue_status="open")
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("AC-01" in reason for reason in reasons))
        self.assertTrue(any("I-001" in reason for reason in reasons))

    def test_done_goal_with_complete_evidence_passes(self) -> None:
        self.seed(status="done", human_status="verified")
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_recursive_stop_hook_is_allowed(self) -> None:
        self.seed(automatic_status="pending")
        stdout = io.StringIO()
        payload = io.StringIO(json.dumps({"stop_hook_active": True}))
        with patch("sys.stdin", payload), redirect_stdout(stdout):
            exit_code = wali_stop._run_hook(self.root)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_hook_returns_structured_block_decision(self) -> None:
        self.seed(automatic_status="pending")
        stdout = io.StringIO()
        payload = io.StringIO(json.dumps({"stop_hook_active": False}))
        with patch("sys.stdin", payload), redirect_stdout(stdout):
            exit_code = wali_stop._run_hook(self.root)
        result = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["decision"], "block")
        self.assertIn("AC-01", result["reason"])


if __name__ == "__main__":
    unittest.main()
