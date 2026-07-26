"""Black-box and contract tests for WALI agent supervision hooks."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("wali_supervision.py")
SPEC = importlib.util.spec_from_file_location("wali_supervision", MODULE_PATH)
assert SPEC and SPEC.loader
wali_supervision = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wali_supervision
SPEC.loader.exec_module(wali_supervision)


class WaliSupervisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        self.seed_task()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.state / name).write_text(content, encoding="utf-8")

    def seed_task(
        self,
        *,
        phase: str = "implementing",
        active_task: str = "T-001",
        task_status: str = "working",
        owner: str = "developer",
        evidence: str = "待补充",
    ) -> None:
        self.write(
            "goal.md",
            f"""---
goal_id: G-001
status: active
phase: {phase}
active_task: {active_task}
---
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动条件 | pending | 待补充 |
| AC-02 | human | 用户验收 | pending | 待用户验收 |
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
| R-001 | functional | 必须交付功能 | 用户需求 | AC-01 |
| R-002 | acceptance | 必须由用户验收 | WALI | AC-02 |

| AC ID | 判定规则 | 验证方法 |
| --- | --- | --- |
| AC-01 | 自动条件成立 | 自动测试 |
| AC-02 | 用户确认 | 用户回测 |
""",
        )
        self.write(
            "todo.md",
            f"""| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现功能 | {owner} | required | {task_status} | 无 | `src/**` | 自动测试通过 | {evidence} | 待分配 |
""",
        )
        self.write(
            "issues.md",
            """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
        )
        self.write("handoff.md", "# 可恢复交接\n")

    def test_task_completed_blocks_a_working_wali_task(self) -> None:
        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TaskCompleted",
                "task_id": "native-1",
                "task_subject": "[T-001] 实现功能",
                "teammate_name": "developer",
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("仍是 working", decision.message)

    def test_task_completed_requires_the_active_wali_task_id(self) -> None:
        self.seed_task(task_status="review", evidence="unit tests exit 0")

        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TaskCompleted",
                "task_id": "native-2",
                "task_subject": "[T-999] unrelated",
                "teammate_name": "developer",
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("active_task T-001", decision.message)

    def test_task_completed_allows_review_with_evidence(self) -> None:
        self.seed_task(
            phase="inspecting",
            task_status="review",
            evidence="python3 -m unittest: exit 0",
        )

        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TaskCompleted",
                "task_id": "native-1",
                "task_subject": "[T-001] 实现功能",
                "teammate_name": "developer",
            },
        )

        self.assertTrue(decision.allowed, decision.message)
        self.assertEqual(decision.wali_task_id, "T-001")
        self.assertEqual(decision.runtime_state, "completed")

    def test_matching_teammate_cannot_idle_while_task_is_working(self) -> None:
        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TeammateIdle",
                "teammate_name": "developer-api",
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("不能进入 idle", decision.message)

    def test_unrelated_architect_can_idle_without_owning_the_active_task(self) -> None:
        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TeammateIdle",
                "teammate_name": "architect",
            },
        )

        self.assertTrue(decision.allowed, decision.message)
        self.assertEqual(decision.runtime_state, "idle")

    def test_stop_failure_is_recorded_but_never_claims_decision_control(self) -> None:
        payload = {
            "hook_event_name": "StopFailure",
            "session_id": "session-1",
            "transcript_path": "/private/transcript.jsonl",
            "error": "rate_limit",
            "last_assistant_message": "sensitive model output",
        }
        captured: list[dict[str, object]] = []

        with patch.object(
            wali_supervision,
            "record_event",
            side_effect=lambda _root, event: captured.append(event),
        ):
            result = wali_supervision.run_hook(self.root, payload)

        self.assertEqual(result, 0)
        self.assertEqual(captured[0]["runtime_state"], "failed")
        self.assertTrue(captured[0]["recovery_required"])
        self.assertNotIn("sensitive model output", json.dumps(captured[0]))
        self.assertIn("message_digest", captured[0])

    def test_stop_failure_without_an_active_task_is_informational(self) -> None:
        self.seed_task(
            phase="clarifying",
            active_task="none",
            task_status="pending",
        )

        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "StopFailure",
                "session_id": "coordinator-session",
                "error": "rate_limit",
            },
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.runtime_state, "failed")
        self.assertEqual(decision.wali_task_id, "")
        self.assertFalse(decision.recovery_required)

    def test_blocking_hook_returns_exit_two_and_feedback(self) -> None:
        stderr = io.StringIO()
        payload = {
            "hook_event_name": "TaskCompleted",
            "task_id": "native-1",
            "task_subject": "[T-001] 实现功能",
            "teammate_name": "developer",
        }

        with redirect_stderr(stderr):
            result = wali_supervision.run_hook(self.root, payload)

        self.assertEqual(result, 2)
        self.assertIn("仍是 working", stderr.getvalue())

    def test_local_registry_marks_failure_recovered_after_valid_completion(self) -> None:
        (self.root / ".svn").mkdir()
        failure = {
            "hook_event_name": "StopFailure",
            "session_id": "session-1",
            "teammate_name": "developer",
            "transcript_path": "/private/transcript.jsonl",
            "error": "rate_limit",
            "last_assistant_message": "do not persist this text",
        }
        completion = {
            "hook_event_name": "TaskCompleted",
            "session_id": "session-2",
            "task_id": "native-1",
            "task_subject": "[T-001] 实现功能",
            "teammate_name": "developer-replacement",
        }

        with (
            patch.object(
                wali_supervision,
                "_svn_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(wali_supervision, "_verified_svn_root", return_value=True),
        ):
            self.assertEqual(wali_supervision.run_hook(self.root, failure), 0)
            registry_path = (
                self.root / ".svn" / "wali-policy" / "supervision.json"
            )
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            failure_event_id = registry["tasks"]["T-001"]["event_id"]
            missing_handoff = wali_supervision.recovery_handoff_reasons(self.root)
            self.assertTrue(any("supervision_event" in reason for reason in missing_handoff))

            self.write(
                "handoff.md",
                f"""---
supervision_event: {failure_event_id}
recovery_action: replace
recovery_evidence: "Coordinator 已审计差异并将 T-001 交给 developer-replacement"
---
# 可恢复交接
""",
            )
            self.assertEqual(
                wali_supervision.recovery_handoff_reasons(self.root),
                [],
            )

            self.seed_task(
                phase="inspecting",
                task_status="review",
                evidence="python3 -m unittest: exit 0",
            )
            self.assertEqual(wali_supervision.run_hook(self.root, completion), 0)

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(len(registry["events"]), 2)
        self.assertFalse(registry["tasks"]["T-001"]["recovery_required"])
        self.assertEqual(
            registry["tasks"]["T-001"]["runtime_state"], "completed"
        )
        self.assertNotIn(
            "do not persist this text",
            registry_path.read_text(encoding="utf-8"),
        )

    def test_settings_register_all_three_supervision_hooks(self) -> None:
        settings_path = MODULE_PATH.parents[1] / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

        for event_name in ("TeammateIdle", "TaskCompleted", "StopFailure"):
            hooks = settings["hooks"].get(event_name, [])
            self.assertTrue(hooks, event_name)
            command = hooks[0]["hooks"][0]
            self.assertIn("wali_supervision.py", " ".join(command["args"]))


if __name__ == "__main__":
    unittest.main()
