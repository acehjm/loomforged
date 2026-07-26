"""Tests for the read-only WALI polling board."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wali_board.py")
ARCHIVE_ROOT = MODULE_PATH.parents[2]
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("wali_board", MODULE_PATH)
assert SPEC and SPEC.loader
wali_board = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wali_board
SPEC.loader.exec_module(wali_board)


class WaliBoardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_root = self.root / "docs" / "wali-0x3"
        self.state_root.mkdir(parents=True)
        self._seed_state()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, name: str, content: str) -> None:
        (self.state_root / name).write_text(content, encoding="utf-8")

    def _seed_state(self) -> None:
        self._write(
            "goal.md",
            """---
wali_schema: 1
goal_id: G-042
status: active
phase: implementing
active_task: T-007
goal_confirmation: confirmed
---

# 目标契约

### 目标

恢复结账流程，同时保留进行中的订单。

| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 过期令牌可以恢复 | pending | 待补充 |
| AC-02 | human | 用户确认结账结果 | verified | 用户已确认 |
""",
        )
        self._write(
            "spec.md",
            """---
spec_id: SPEC-G-042
goal_id: G-042
source_mode: pressure_test
---

| ID | 类型 | 规范要求 | 来源 | 关联 AC |
| --- | --- | --- | --- | --- |
| R-001 | functional | 系统必须恢复过期会话 | 用户需求 | AC-01 |
| R-002 | acceptance | 用户必须确认结果 | WALI | AC-02 |

| AC ID | 判定规则 | 验证方法 |
| --- | --- | --- |
| AC-01 | 恢复后订单保持不变 | 自动测试 |
| AC-02 | 用户确认结账可用 | 用户回测 |
""",
        )
        self._write(
            "todo.md",
            """# 任务

| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-005 | AC-01 | 建立恢复测试 | tester-1 | required | done | 无 | `tests/recovery/**` | 测试覆盖恢复 | `tests/test_recovery.py` 通过 | reviewer |
| T-007 | AC-01 | 实现恢复流程 | developer-1 | required | working | T-005 | `src/checkout/**` | 恢复结果正确 | 待补充 | tester |
| T-008 | AC-02 | 检查错误处理 | reviewer-1 | optional | review | T-007 | `src/errors/**` | 错误语义清楚 | review note | tester |
""",
        )
        self._write(
            "issues.md",
            """# 问题

| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I-003 | reviewer | T-007 | AC-01 | high | verify | 过期令牌恢复失败 | developer-1 | `src/token.py:12` | reviewer | 待验证 |
| I-004 | tester | T-008 | AC-02 | low | closed | 提示文字错误 | developer-1 | screenshot | tester | 已复验 |
""",
        )
        self._write("handoff.md", "# 可恢复交接\n")

    def _snapshot_files(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def _seed_runtime(self) -> None:
        runtime_root = self.root / ".svn" / "wali-policy"
        runtime_root.mkdir(parents=True)
        (runtime_root / "supervision.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "agents": {
                        "developer-1": {
                            "runtime_state": "working",
                            "last_event_at": "2026-07-26T06:12:00+00:00",
                            "wali_task_id": "T-007",
                            "recovery_required": False,
                        }
                    },
                    "tasks": {},
                    "events": [
                        {
                            "event_id": "evt-1",
                            "timestamp": "2026-07-26T06:11:59+00:00",
                            "hook_event": "TaskCompleted",
                            "teammate_name": "tester-1",
                            "wali_task_id": "T-005",
                            "runtime_state": "completed",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_snapshot_contains_decision_state_without_internal_paths(self) -> None:
        snapshot = wali_board.build_state(self.root)
        serialized = json.dumps(snapshot, ensure_ascii=False)

        self.assertEqual(snapshot["goal"]["id"], "G-042")
        self.assertEqual(snapshot["goal"]["title"], "恢复结账流程，同时保留进行中的订单。")
        self.assertEqual(snapshot["now"]["id"], "T-007")
        self.assertEqual(snapshot["goal"]["openIssueCount"], 1)
        self.assertEqual(snapshot["goal"]["criteriaVerified"], 1)
        self.assertFalse(snapshot["runtime"]["available"])
        self.assertNotIn("src/", serialized)
        self.assertNotIn("tests/", serialized)
        self.assertNotIn("docs/", serialized)
        self.assertNotIn(".svn", serialized)
        self.assertNotIn("test_recovery.py", serialized)
        self.assertNotIn("token.py", serialized)

    def test_runtime_is_optional_and_adds_human_readable_activity(self) -> None:
        without_runtime = wali_board.build_state(self.root)
        self.assertFalse(without_runtime["runtime"]["available"])

        self._seed_runtime()
        with_runtime = wali_board.build_state(self.root)
        developer = next(
            agent
            for agent in with_runtime["agents"]
            if agent["name"] == "developer-1"
        )

        self.assertTrue(with_runtime["runtime"]["available"])
        self.assertEqual(developer["runtimeState"], "working")
        self.assertEqual(
            with_runtime["activity"][0]["message"],
            "tester-1 完成一次运行，关联 T-005",
        )
        self.assertNotIn(
            "TaskCompleted",
            json.dumps(with_runtime["activity"], ensure_ascii=False),
        )

    def test_http_server_exposes_only_known_read_only_routes(self) -> None:
        shutil.copy2(
            ARCHIVE_ROOT / "docs" / "wali-0x3" / "wali-board.html",
            self.state_root / "wali-board.html",
        )
        before = self._snapshot_files()

        server = wali_board.create_server(self.root, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base_url}/api/state") as response:
                state = json.load(response)
            with urllib.request.urlopen(f"{base_url}/") as response:
                html = response.read().decode("utf-8")
            with self.assertRaises(urllib.error.HTTPError) as removed_asset:
                urllib.request.urlopen(f"{base_url}/assets/wali-agent.png")
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(f"{base_url}/not-allowed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        after = self._snapshot_files()
        self.assertTrue(state["ok"])
        self.assertIn("每 1 秒", html)
        self.assertEqual(removed_asset.exception.code, 404)
        self.assertEqual(missing.exception.code, 404)
        self.assertEqual(before, after)

    def test_html_polls_every_second_and_hides_storage_details(self) -> None:
        html = (
            ARCHIVE_ROOT / "docs" / "wali-0x3" / "wali-board.html"
        ).read_text(encoding="utf-8")

        self.assertIn("const POLL_INTERVAL_MS = 1000;", html)
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertNotIn("/assets/wali", html)
        self.assertIn("只读页面，不会修改项目状态", html)
        for hidden_detail in (
            "goal.md",
            "todo.md",
            "issues.md",
            "handoff.md",
            "supervision.json",
            ".svn",
            "Evidence",
        ):
            self.assertNotIn(hidden_detail, html)


if __name__ == "__main__":
    unittest.main()
