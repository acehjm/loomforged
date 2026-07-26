"""Black-box and contract tests for WALI agent supervision hooks."""

from __future__ import annotations

import importlib.util
import errno
import io
import json
import os
import sys
import tempfile
import time
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


class FakeMsvcrt:
    LK_NBLCK = 1
    LK_UNLCK = 2

    def __init__(self, acquire_errno: int | None = None) -> None:
        self.acquire_errno = acquire_errno
        self.calls: list[tuple[int, int]] = []

    def locking(self, _descriptor: int, mode: int, byte_count: int) -> None:
        self.calls.append((mode, byte_count))
        if mode == self.LK_NBLCK and self.acquire_errno is not None:
            raise OSError(self.acquire_errno, "simulated Windows lock result")


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

    def acquire_external_lock(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        if wali_supervision.fcntl is not None:
            wali_supervision.fcntl.flock(
                handle.fileno(),
                wali_supervision.fcntl.LOCK_EX
                | wali_supervision.fcntl.LOCK_NB,
            )
            return handle
        if wali_supervision.msvcrt is not None:
            handle.seek(0)
            wali_supervision.msvcrt.locking(
                handle.fileno(), wali_supervision.msvcrt.LK_NBLCK, 1
            )
            return handle
        handle.close()
        self.skipTest("当前测试平台没有可用的文件锁后端")

    def release_external_lock(self, handle) -> None:
        if wali_supervision.fcntl is not None:
            wali_supervision.fcntl.flock(
                handle.fileno(), wali_supervision.fcntl.LOCK_UN
            )
        elif wali_supervision.msvcrt is not None:
            handle.seek(0)
            wali_supervision.msvcrt.locking(
                handle.fileno(), wali_supervision.msvcrt.LK_UNLCK, 1
            )
        handle.close()

    def seed_task(
        self,
        *,
        phase: str = "implementing",
        active_task: str = "T-001",
        task_status: str = "working",
        owner: str = "developer",
        evidence: str = "待补充",
    ) -> None:
        profiles = {
            "clarifying": {
                "status": "draft",
                "confirmation": "pending",
                "confirmation_evidence": '""',
                "definition_digest": "",
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_goal_draft",
                    "update_spec_draft",
                    "update_handoff",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/spec.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
            "implementing": {
                "status": "active",
                "confirmation": "confirmed",
                "confirmation_evidence": "用户确认 Goal 与 Spec",
                "definition_digest": "0" * 64,
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_todo",
                    "update_issues",
                    "update_handoff",
                    "transition_phase",
                    "modify_implementation",
                    "manage_svn_schedule",
                    "sync_svn_working_copy",
                    "run_project_commands",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/todo.md",
                    "docs/wali-0x3/issues.md",
                    "docs/wali-0x3/handoff.md",
                    "@active_task",
                ),
                "flags": (True, True, False, False),
            },
            "inspecting": {
                "status": "active",
                "confirmation": "confirmed",
                "confirmation_evidence": "用户确认 Goal 与 Spec",
                "definition_digest": "0" * 64,
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_todo",
                    "update_issues",
                    "update_handoff",
                    "transition_phase",
                    "run_checks",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/todo.md",
                    "docs/wali-0x3/issues.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
        }
        profile = profiles[phase]
        effects = "\n".join(
            f"  - {effect}" for effect in profile["effects"]
        )
        scopes = "\n".join(
            f"  - {scope}" for scope in profile["scopes"]
        )
        (
            allow_new_artifacts,
            allow_implementation_changes,
            allow_external_writes,
            allow_svn_commit,
        ) = profile["flags"]
        self.write(
            "goal.md",
            f"""---
wali_schema: 1
goal_id: G-001
status: {profile["status"]}
phase: {phase}
active_task: {active_task}
goal_confirmation: {profile["confirmation"]}
goal_confirmation_evidence: {profile["confirmation_evidence"]}
goal_definition_digest: "{profile["definition_digest"]}"
allowed_effects:
{effects}
allowed_capabilities:
write_scope:
{scopes}
preexisting_changes:
carry_epoch: 0
carried_history:
carried_changes:
stop_intent: continue
waiting_for: none
waiting_detail: ""
blocked_reason: ""
exit_outcome: none
exit_reason: ""
exit_evidence: ""
exit_change_disposition: none
superseded_by: none
allow_new_artifacts: {str(allow_new_artifacts).lower()}
allow_implementation_changes: {str(allow_implementation_changes).lower()}
allow_external_writes: {str(allow_external_writes).lower()}
allow_svn_commit: {str(allow_svn_commit).lower()}
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

    def test_task_completed_rejects_a_missing_wali_schema(self) -> None:
        self.seed_task(
            phase="inspecting",
            task_status="review",
            evidence="python3 -m unittest: exit 0",
        )
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "wali_schema: 1\n", "", 1
            ),
            encoding="utf-8",
        )

        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TaskCompleted",
                "task_subject": "[T-001] 实现功能",
                "teammate_name": "developer",
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("wali_schema", decision.message)

    def test_task_completed_rejects_an_unknown_wali_schema(self) -> None:
        self.seed_task(
            phase="inspecting",
            task_status="review",
            evidence="python3 -m unittest: exit 0",
        )
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "wali_schema: 1", "wali_schema: 2", 1
            ),
            encoding="utf-8",
        )

        decision = wali_supervision.evaluate_event(
            self.root,
            {
                "hook_event_name": "TaskCompleted",
                "task_subject": "[T-001] 实现功能",
                "teammate_name": "developer",
            },
        )

        self.assertFalse(decision.allowed)
        self.assertIn("不支持的 wali_schema", decision.message)

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
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(wali_supervision, "is_verified_working_copy_root", return_value=True),
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

    def test_record_event_succeeds_after_previous_holder_releases_lock(
        self,
    ) -> None:
        metadata = self.root / ".svn" / "wali-policy"
        lock_path = metadata / "supervision.lock"
        metadata.mkdir(parents=True)
        lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "token": "previous-owner",
                    "acquired_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        previous_holder = self.acquire_external_lock(lock_path)
        self.release_external_lock(previous_holder)

        with (
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(wali_supervision, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_supervision.time, "sleep", return_value=None),
        ):
            recorded = wali_supervision.record_event(
                self.root,
                {
                    "event_id": "event-released-lock",
                    "runtime_state": "failed",
                    "wali_task_id": "T-001",
                },
            )

        self.assertTrue(recorded)
        self.assertTrue(lock_path.is_file())
        registry = json.loads(
            (metadata / "supervision.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            registry["events"][-1]["event_id"], "event-released-lock"
        )

    def test_record_event_reuses_an_old_empty_lock_file(self) -> None:
        metadata = self.root / ".svn" / "wali-policy"
        lock_path = metadata / "supervision.lock"
        metadata.mkdir(parents=True)
        lock_path.touch()
        old = time.time() - 120
        os.utime(lock_path, (old, old))

        with (
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(wali_supervision, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_supervision.time, "sleep", return_value=None),
        ):
            recorded = wali_supervision.record_event(
                self.root,
                {
                    "event_id": "event-ownerless-lock",
                    "runtime_state": "idle",
                },
            )

        self.assertTrue(recorded)
        self.assertTrue(lock_path.is_file())

    def test_record_event_preserves_a_lock_held_by_a_live_process(self) -> None:
        metadata = self.root / ".svn" / "wali-policy"
        lock_path = metadata / "supervision.lock"
        metadata.mkdir(parents=True)
        lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "token": "live-owner",
                    "acquired_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        live_holder = self.acquire_external_lock(lock_path)

        try:
            with (
                patch.object(
                    wali_supervision,
                    "discover_working_copy_root",
                    return_value=self.root.resolve(),
                ),
                patch.object(
                    wali_supervision,
                    "is_verified_working_copy_root",
                    return_value=True,
                ),
                patch.object(
                    wali_supervision.time, "sleep", return_value=None
                ),
            ):
                with self.assertRaises(wali_supervision.SupervisionError):
                    wali_supervision.record_event(
                        self.root,
                        {
                            "event_id": "event-live-lock",
                            "runtime_state": "idle",
                        },
                    )
        finally:
            self.release_external_lock(live_holder)

        self.assertTrue(lock_path.is_file())
        owner = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(owner["token"], "live-owner")

    def test_record_event_reuses_the_same_persistent_lock_file(self) -> None:
        with (
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_supervision,
                "is_verified_working_copy_root",
                return_value=True,
            ),
        ):
            self.assertTrue(
                wali_supervision.record_event(
                    self.root,
                    {"event_id": "event-first", "runtime_state": "idle"},
                )
            )
            lock_path = (
                self.root / ".svn" / "wali-policy" / "supervision.lock"
            )
            first_inode = lock_path.stat().st_ino
            self.assertTrue(
                wali_supervision.record_event(
                    self.root,
                    {"event_id": "event-second", "runtime_state": "idle"},
                )
            )

        self.assertEqual(lock_path.stat().st_ino, first_inode)
        registry = json.loads(
            (
                self.root
                / ".svn"
                / "wali-policy"
                / "supervision.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            [event["event_id"] for event in registry["events"][-2:]],
            ["event-first", "event-second"],
        )

    def test_record_event_recovers_an_unlocked_file_left_by_a_crashed_holder(
        self,
    ) -> None:
        metadata = self.root / ".svn" / "wali-policy"
        metadata.mkdir(parents=True)
        lock_path = metadata / "supervision.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 999_999_999,
                    "token": "crashed-holder",
                    "created_at": time.time() - 120,
                }
            ),
            encoding="utf-8",
        )

        with (
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_supervision,
                "is_verified_working_copy_root",
                return_value=True,
            ),
            patch.object(wali_supervision.time, "sleep", return_value=None),
        ):
            recorded = wali_supervision.record_event(
                self.root,
                {
                    "event_id": "event-crashed-file-holder",
                    "runtime_state": "failed",
                },
            )

        self.assertTrue(recorded)
        self.assertTrue(lock_path.is_file())

    def test_record_event_uses_the_windows_lock_backend(self) -> None:
        backend = FakeMsvcrt()
        with (
            patch.object(wali_supervision, "fcntl", None),
            patch.object(wali_supervision, "msvcrt", backend),
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_supervision,
                "is_verified_working_copy_root",
                return_value=True,
            ),
        ):
            recorded = wali_supervision.record_event(
                self.root,
                {
                    "event_id": "event-windows-lock",
                    "runtime_state": "idle",
                },
            )

        self.assertTrue(recorded)
        self.assertEqual(
            backend.calls,
            [(backend.LK_NBLCK, 1), (backend.LK_UNLCK, 1)],
        )

    def test_record_event_treats_windows_lock_contention_as_busy(self) -> None:
        backend = FakeMsvcrt(errno.EACCES)
        with (
            patch.object(wali_supervision, "fcntl", None),
            patch.object(wali_supervision, "msvcrt", backend),
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_supervision,
                "is_verified_working_copy_root",
                return_value=True,
            ),
            patch.object(wali_supervision.time, "sleep", return_value=None),
        ):
            with self.assertRaisesRegex(
                wali_supervision.SupervisionError,
                "另一个 Hook",
            ):
                wali_supervision.record_event(
                    self.root,
                    {
                        "event_id": "event-windows-busy",
                        "runtime_state": "idle",
                    },
                )

        self.assertEqual(
            backend.calls,
            [(backend.LK_NBLCK, 1)]
            * wali_supervision.LOCK_WAIT_ATTEMPTS,
        )

    def test_record_event_reports_unexpected_windows_lock_errors(self) -> None:
        backend = FakeMsvcrt(errno.EIO)
        with (
            patch.object(wali_supervision, "fcntl", None),
            patch.object(wali_supervision, "msvcrt", backend),
            patch.object(
                wali_supervision,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_supervision,
                "is_verified_working_copy_root",
                return_value=True,
            ),
        ):
            with self.assertRaisesRegex(
                wali_supervision.SupervisionError,
                "无法锁定监督状态",
            ):
                wali_supervision.record_event(
                    self.root,
                    {
                        "event_id": "event-windows-error",
                        "runtime_state": "idle",
                    },
                )

        self.assertEqual(backend.calls, [(backend.LK_NBLCK, 1)])

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
