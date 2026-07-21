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
        automatic_status: str = "verified",
        human_status: str = "pending",
        task_status: str = "done",
        issue_status: str = "closed",
    ) -> None:
        self.write(
            "goal.md",
            f"""---
status: {status}
---
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动条件 | {automatic_status} | test exit 0 |
| AC-02 | human | 用户验收 | {human_status} | {'用户确认通过' if human_status == 'verified' else '待用户验收'} |
""",
        )
        self.write(
            "todo.md",
            f"""| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现 | developer | required | {task_status} | 无 | src | 测试通过 | test exit 0 |
""",
        )
        self.write(
            "issues.md",
            f"""| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-001 | tester | T-001 | AC-01 | blocker | {issue_status} | 示例 | developer | repro | regression pass |
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
