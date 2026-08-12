"""Black-box liveness tests for the lightweight wali-0x3 control plane."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOKS = Path(__file__).parent
POLICY = HOOKS / "wali_policy.py"
STOP = HOOKS / "wali_stop.py"


GOAL = """---
agent: wali-0x3
goal_id: G-001
confirmed: true
---

# Goal

交付一个可验证的小功能。

## Scope

- In: `src/feature/**`
- Out: 其他目录

## Requirements

| ID | Requirement | Acceptance |
| --- | --- | --- |
| R-001 | 功能可以工作 | AC-001 |

## Acceptance Criteria

| ID | Criterion | Method |
| --- | --- | --- |
| AC-001 | 自动检查通过 | `python3 -m unittest -v` |
"""


SPEC = """---
agent: wali-0x3
goal_id: G-001
status: implementation-ready
---

# Implementation-Ready Spec

## Current System

- Entry points: `src/feature/`
- Existing behavior: 目标功能尚未实现。
- Constraints: 保持现有 feature 接口兼容。
- Evidence: `src/feature/` 与 `python3 -m unittest -v`。

## Target Behavior

- Normal flow: 实现用户要求的功能并保持现有接口兼容。
- Errors and edges: 非法输入返回明确错误，既有行为不回归。
- Compatibility: 保持既有调用方和测试通过。
- Non-goals: 不修改无关模块。

## Design Mapping

| ID | Requirement | Design | Affected Areas |
| --- | --- | --- | --- |
| D-001 | R-001 | 在现有 feature 接口后实现最小完整行为。 | `src/feature/**` |

## Verification Mapping

| Acceptance | Coverage | Method |
| --- | --- | --- |
| AC-001 | integration | `python3 -m unittest -v` |

## Autonomous Decision Contract

- May decide: 可逆、低影响并遵循现有接口和项目约定的实现细节、局部重构与测试组织。
- Must ask: 用户可见语义变化、验收冲突、不可逆数据迁移、重大安全风险或新的外部副作用。
- Must not: 扩大业务范围、弱化测试、覆盖用户修改或把假设伪装成事实。
- If blocked: 先用代码、测试和文档消除不确定性；仅携带选项、证据和建议询问一个阻塞问题。

## Open Questions

- none
"""


WORK = """---
goal_id: G-001
phase: work
active_task: T-001
stop_intent: continue
waiting_for: none
outcome: none
updated: 2026-08-11T12:00:00+08:00
---

# Work

## Acceptance

| ID | Status | Evidence | Verifier |
| --- | --- | --- | --- |
| AC-001 | pending | none | none |

## Tasks

| ID | Acceptance | Task | Status | Depends On | Scope | Evidence | Owner | Verifier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-001 | 实现功能 | working | none | `src/feature/**` | none | developer | none |

## Issues

| ID | Task | Acceptance | Severity | Status | Description | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
"""


class WaliLivenessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        (self.state / "goal.md").write_text(GOAL, encoding="utf-8")
        (self.state / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.state / "work.md").write_text(WORK, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_hook(
        self,
        script: Path,
        payload: dict[str, object],
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--project-root",
                str(self.root),
                *arguments,
            ],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            check=False,
            text=True,
        )

    def policy(self, payload: dict[str, object], command: str = "hook") -> subprocess.CompletedProcess[str]:
        return self.run_hook(POLICY, payload, command)

    def test_common_git_bash_and_svn_read_commands_do_not_require_registration(self) -> None:
        commands = (
            "pwd && rg --files",
            "ls -la && find . -maxdepth 2 -type f",
            "awk '{print $1}' input.txt | sort -u",
            "svn status && svn diff --internal-diff",
            "svn info && svn log -l 1",
            "bash -lc 'pwd && rg -n Goal docs/wali-0x3/goal.md'",
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.policy(
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    }
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_missing_control_state_does_not_block_local_diagnostics(self) -> None:
        (self.state / "goal.md").unlink()
        (self.state / "work.md").unlink()

        result = self.policy(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "pwd && rg --files"},
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_work_file_can_be_created_through_the_repair_channel(self) -> None:
        (self.state / "work.md").unlink()

        result = self.policy(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "work.md"),
                    "content": WORK,
                },
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_spec_file_can_be_created_through_the_repair_channel(self) -> None:
        spec_path = self.state / "spec.md"
        spec_path.unlink()

        result = self.policy(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(spec_path),
                    "content": SPEC,
                },
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_post_hook_warning_never_closes_the_state_repair_channel(self) -> None:
        work_path = self.state / "work.md"
        partial_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(work_path),
                "old_string": "| T-001 | AC-001 | 实现功能 | working |",
                "new_string": "| T-001 | AC-001 | 实现功能 | done |",
            },
        }
        pre = self.policy(partial_payload)
        self.assertEqual(pre.stdout, "", pre.stdout)

        work_path.write_text(
            work_path.read_text(encoding="utf-8").replace(
                "| T-001 | AC-001 | 实现功能 | working |",
                "| T-001 | AC-001 | 实现功能 | done |",
                1,
            ),
            encoding="utf-8",
        )
        post_payload = dict(partial_payload, hook_event_name="PostToolUse")
        post = self.policy(post_payload, "post-hook")
        post_output = json.loads(post.stdout)
        self.assertNotIn("decision", post_output)
        self.assertIn("需要修复", post_output["systemMessage"])

        repair = self.policy(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(work_path),
                    "old_string": "| none | developer | none |",
                    "new_string": "| test exit 0 | developer | tester |",
                },
            }
        )
        self.assertEqual(repair.stdout, "", repair.stdout)

    def test_normal_stop_does_not_require_a_handoff_or_completed_work(self) -> None:
        result = self.run_hook(
            STOP,
            {
                "hook_event_name": "Stop",
                "stop_hook_active": False,
            },
            "--hook",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_explicit_handoff_requires_a_recoverable_cursor(self) -> None:
        work_path = self.state / "work.md"
        work_path.write_text(
            work_path.read_text(encoding="utf-8").replace(
                "stop_intent: continue",
                "stop_intent: handoff",
            ),
            encoding="utf-8",
        )

        result = self.run_hook(
            STOP,
            {
                "hook_event_name": "Stop",
                "stop_hook_active": False,
            },
            "--hook",
        )

        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("handoff.md", output["reason"])

    def test_explicit_handoff_allows_a_matching_cursor(self) -> None:
        work_path = self.state / "work.md"
        work_path.write_text(
            work_path.read_text(encoding="utf-8").replace(
                "stop_intent: continue",
                "stop_intent: handoff",
            ),
            encoding="utf-8",
        )
        (self.state / "handoff.md").write_text(
            """---
goal_id: G-001
phase: work
active_task: T-001
updated: 2026-08-11T12:30:00+08:00
---

# Handoff

## Current State

- 自动检查已通过，当前任务仍在实现。

## Next Step

- 完成 T-001 并记录证据。
""",
            encoding="utf-8",
        )

        result = self.run_hook(
            STOP,
            {"hook_event_name": "Stop", "stop_hook_active": False},
            "--hook",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
