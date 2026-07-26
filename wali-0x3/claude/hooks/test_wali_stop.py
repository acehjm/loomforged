"""State-transition tests for the WALI Stop hook."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import wali_policy


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

    def refresh_handoff_digest(self, status_xml: str | None = None) -> None:
        handoff_path = self.state / "handoff.md"
        contract = wali_policy.load_contract(self.root)
        digest = wali_policy.handoff_state_digest(self.root, contract, status_xml)
        handoff = handoff_path.read_text(encoding="utf-8")
        handoff = re.sub(
            r'(?m)^state_digest:\s*.*$',
            f'state_digest: "{digest}"',
            handoff,
        )
        handoff_path.write_text(handoff, encoding="utf-8")

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
        if status == "draft":
            phase = "clarifying"
            confirmation = "pending"
            evidence = ""
            effects = (
                "read_workspace",
                "ask_user",
                "update_goal_draft",
                "update_spec_draft",
                "update_handoff",
            )
            scopes = (
                "docs/wali-0x3/goal.md",
                "docs/wali-0x3/spec.md",
                "docs/wali-0x3/handoff.md",
            )
        elif status == "waiting_user" and waiting_for == "direction":
            phase = "awaiting_direction"
            confirmation = "confirmed"
            evidence = "用户确认 Goal G-001"
            effects = (
                "read_workspace",
                "ask_user",
                "update_goal",
                "update_handoff",
            )
            scopes = ("docs/wali-0x3/goal.md", "docs/wali-0x3/handoff.md")
        elif status == "waiting_user":
            phase = "accepting"
            confirmation = "confirmed"
            evidence = "用户确认 Goal G-001"
            effects = (
                "read_workspace",
                "ask_user",
                "update_goal",
                "update_issues",
                "update_handoff",
            )
            scopes = (
                "docs/wali-0x3/goal.md",
                "docs/wali-0x3/issues.md",
                "docs/wali-0x3/handoff.md",
            )
        elif status == "blocked":
            phase = "blocked"
            confirmation = "confirmed"
            evidence = "用户确认 Goal G-001"
            effects = (
                "read_workspace",
                "ask_user",
                "update_goal",
                "update_handoff",
            )
            scopes = ("docs/wali-0x3/goal.md", "docs/wali-0x3/handoff.md")
        elif status == "done":
            phase = "closed"
            confirmation = "confirmed"
            evidence = "用户确认 Goal G-001"
            effects = ("read_workspace", "update_handoff", "transition_phase")
            scopes = (
                "docs/wali-0x3/goal.md",
                "docs/wali-0x3/handoff.md",
            )
        elif status == "cancelled":
            phase = "terminated"
            confirmation = "pending"
            evidence = ""
            effects = ("read_workspace", "update_handoff", "transition_phase")
            scopes = (
                "docs/wali-0x3/goal.md",
                "docs/wali-0x3/handoff.md",
            )
        else:
            phase = "planning"
            confirmation = "confirmed"
            evidence = "用户确认 Goal G-001"
            effects = (
                "read_workspace",
                "ask_user",
                "update_goal",
                "update_todo",
                "update_issues",
                "update_handoff",
            )
            scopes = (
                "docs/wali-0x3/goal.md",
                "docs/wali-0x3/todo.md",
                "docs/wali-0x3/issues.md",
                "docs/wali-0x3/handoff.md",
            )
        effects_yaml = "\n".join(f"  - {effect}" for effect in effects)
        scopes_yaml = "\n".join(f"  - {scope}" for scope in scopes)
        exit_outcome = (
            "completed"
            if status == "done"
            else "cancelled"
            if status == "cancelled"
            else "none"
        )
        exit_reason = (
            "用户验收完成"
            if status == "done"
            else "用户明确取消当前 Goal"
            if status == "cancelled"
            else ""
        )
        exit_evidence = (
            "自动检查和用户验收均已通过"
            if status == "done"
            else "会话消息：停止当前工作"
            if status == "cancelled"
            else ""
        )
        exit_disposition = "preserve" if status == "cancelled" else "none"
        self.write(
            "goal.md",
            f"""---
wali_schema: 1
goal_id: G-001
status: {status}
phase: {phase}
active_task: none
goal_confirmation: {confirmation}
goal_confirmation_evidence: "{evidence}"
goal_definition_digest: ""
allowed_effects:
{effects_yaml}
allowed_capabilities:
write_scope:
{scopes_yaml}
preexisting_changes:
carry_epoch: 0
carried_history:
carried_changes:
stop_intent: continue
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
waiting_for: {waiting_for}
waiting_detail: "{waiting_detail}"
blocked_reason: "{blocked_reason}"
exit_outcome: {exit_outcome}
exit_reason: "{exit_reason}"
exit_evidence: "{exit_evidence}"
exit_change_disposition: {exit_disposition}
superseded_by: none
---
## 2. 已确认事实
- 需要交付可验证功能。
## 3. 高影响未知项
- 无。
## 4. 决策记录
- 使用现有结构。
## 5. 目标与背景
- 交付用户可观察结果。
## 6. 范围与约束
- 范围为 `src/**`，不包含其他模块。
## 7. 验收标准
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动条件 | {automatic_status} | test exit 0 |
| AC-02 | human | 用户验收 | {human_status} | {'用户确认通过' if human_status == 'verified' else '待用户验收'} |
## 8. 检查方式
| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
| 单元测试 | `python3 -m unittest -v` | 退出码 0 |
""",
        )
        self.write(
            "spec.md",
            """---
spec_id: SPEC-G-001
goal_id: G-001
source_mode: pressure_test
---
# 规格说明书

## 1. 输入与形成方式
- 输入：测试需求。

## 2. 规范需求
| ID | 类型 | 规范要求 | 来源 | 关联 AC |
| --- | --- | --- | --- | --- |
| R-001 | functional | 必须交付可自动验证的功能 | 用户需求 | AC-01 |
| R-002 | acceptance | 必须由用户确认业务结果 | WALI 约束 | AC-02 |

## 3. 行为与边界
- 覆盖正常与失败路径。

## 4. 接口、数据与错误
- 不适用：测试夹具无外部接口。

## 5. 质量属性与兼容性
- 保持兼容。

## 6. 验收判定规则
| AC ID | 判定规则 | 验证方法 |
| --- | --- | --- |
| AC-01 | 自动检查退出码为 0 | 运行测试 |
| AC-02 | 用户明确确认业务结果 | 用户回测 |
""",
        )
        if confirmation == "confirmed":
            goal_path = self.state / "goal.md"
            contract = wali_policy.load_contract(self.root)
            digest = wali_policy.goal_definition_digest(self.root, contract)
            goal_path.write_text(
                goal_path.read_text(encoding="utf-8").replace(
                    'goal_definition_digest: ""',
                    f'goal_definition_digest: "{digest}"',
                ),
                encoding="utf-8",
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
        self.write(
            "handoff.md",
            f"""---
updated: 2026-07-22T12:00:00+08:00
goal_id: G-001
phase: {phase}
active_task: none
goal_confirmation: {confirmation}
state_digest: ""
---
# 可恢复交接
""",
        )
        self.refresh_handoff_digest()

    def make_delivering(self, status_xml: str) -> None:
        self.seed(status="done", human_status="verified")
        service = self.root / "src" / "feature" / "service.py"
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("implemented\n", encoding="utf-8")
        (self.root / ".svn").mkdir(exist_ok=True)
        fingerprint = wali_policy._path_fingerprint(
            self.root, "src/feature/service.py"
        )
        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8")
        goal = goal.replace("phase: closed", "phase: delivering")
        goal = goal.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase\n"
            "allowed_capabilities:",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase\n"
            "allowed_capabilities:",
        )
        goal = goal.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md\n"
            "preexisting_changes:",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md\n"
            "  - \"@svn_commit\"\n"
            "svn_commit_paths:\n"
            "  - src/feature/service.py\n"
            "svn_commit_evidence: \"用户明确授权精确提交 service.py\"\n"
            "preexisting_changes:",
        )
        goal = goal.replace(
            "carried_changes:\nstop_intent:",
            f'carried_changes:\n  - "src/feature/service.py::{fingerprint}"\nstop_intent:',
        )
        goal = goal.replace("carry_epoch: 0", "carry_epoch: 1")
        goal = goal.replace("allow_svn_commit: false", "allow_svn_commit: true")
        goal_path.write_text(goal, encoding="utf-8")
        handoff_path = self.state / "handoff.md"
        handoff_path.write_text(
            handoff_path.read_text(encoding="utf-8").replace(
                "phase: closed", "phase: delivering"
            ),
            encoding="utf-8",
        )
        self.refresh_handoff_digest(status_xml)

    def add_dependency_cycle(self) -> None:
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        todo = todo.replace(
            "| 无 | src | 测试通过 |",
            "| T-002 | src | 测试通过 |",
        )
        todo += (
            "| T-002 | AC-01 | 补充实现 | developer | required | done | T-001 | "
            "src/other | 测试通过 | test exit 0 | tester |\n"
        )
        self.write("todo.md", todo)

    def test_draft_goal_skips_completion_checks(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_stop_requires_failed_agent_recovery_to_be_in_handoff(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")

        with patch.object(
            wali_stop,
            "recovery_handoff_reasons",
            return_value=["handoff.md 缺少 Agent 异常恢复计划"],
        ):
            reasons = wali_stop.evaluate_project(self.root)

        self.assertIn("handoff.md 缺少 Agent 异常恢复计划", reasons)

    def test_draft_goal_cannot_stop_with_a_spec_owned_by_another_goal(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "goal_id: G-001", "goal_id: G-002"
            ),
            encoding="utf-8",
        )
        self.refresh_handoff_digest()

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(
            any("spec.md 的 goal_id 必须与 goal.md 一致" in reason for reason in reasons)
        )

    def test_every_goal_requires_the_fixed_spec_artifact(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        (self.state / "spec.md").unlink()

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("spec.md" in reason for reason in reasons))

    def test_typed_termination_can_stop_without_claiming_incomplete_work_is_done(self) -> None:
        self.seed(
            status="cancelled",
            automatic_status="pending",
            human_status="pending",
            task_status="pending",
            issue_status="open",
        )

        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_goal_without_phase_contract_cannot_bypass_stop(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace("phase: clarifying\n", ""),
            encoding="utf-8",
        )

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("缺少 phase" in reason for reason in reasons))

    def test_draft_goal_with_phase_contract_must_obey_clarifying_profile(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8").replace(
            "  - ask_user\n  - update_goal_draft",
            "  - modify_implementation",
        )
        goal_path.write_text(goal, encoding="utf-8")

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("clarifying phase" in reason for reason in reasons))

    def test_stop_audits_svn_changes_when_phase_contract_exists(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        (self.root / ".svn").mkdir()
        status_xml = """<?xml version="1.0"?><status><target path=".">
<entry path="context.md"><wc-status item="unversioned" props="none"/></entry>
</target></status>"""

        with (
            patch.object(wali_stop, "read_status_xml", return_value=status_xml),
            patch.object(
                wali_stop,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
        ):
            reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("context.md" in reason for reason in reasons))

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

    def test_acceptance_wait_still_enforces_automatic_checks(self) -> None:
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
            automatic_status="pending",
            task_status="blocked",
        )
        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_explicit_handoff_intent_allows_recoverable_incomplete_stop(self) -> None:
        self.seed(automatic_status="pending", task_status="working")
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "stop_intent: continue", "stop_intent: handoff"
            ),
            encoding="utf-8",
        )

        self.assertEqual(wali_stop.evaluate_project(self.root), [])

    def test_handoff_intent_requires_a_current_mirrored_handoff(self) -> None:
        self.seed(automatic_status="pending", task_status="working")
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "stop_intent: continue", "stop_intent: handoff"
            ),
            encoding="utf-8",
        )
        (self.state / "handoff.md").write_text(
            "---\nupdated: YYYY-MM-DD\ngoal_id: G-999\n---\n",
            encoding="utf-8",
        )

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("handoff.md" in reason for reason in reasons))

    def test_handoff_intent_rejects_a_stale_state_digest(self) -> None:
        self.seed(automatic_status="pending", task_status="working")
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "stop_intent: continue", "stop_intent: handoff"
            ),
            encoding="utf-8",
        )
        todo_path = self.state / "todo.md"
        todo_path.write_text(
            todo_path.read_text(encoding="utf-8").replace("实现", "实现并记录上下文"),
            encoding="utf-8",
        )

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("state_digest" in reason for reason in reasons))

    def test_handoff_digest_tracks_acceptance_evidence_and_handoff_body(self) -> None:
        self.seed(automatic_status="pending", task_status="working")
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8")
            .replace("stop_intent: continue", "stop_intent: handoff")
            .replace("| AC-01 | automatic | 自动条件 | pending |", "| AC-01 | automatic | 自动条件 | verified |"),
            encoding="utf-8",
        )

        evidence_reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("state_digest" in reason for reason in evidence_reasons))

        self.refresh_handoff_digest()
        handoff_path = self.state / "handoff.md"
        handoff_path.write_text(
            handoff_path.read_text(encoding="utf-8")
            + "\n## 下一步\n继续验证边界条件。\n",
            encoding="utf-8",
        )
        body_reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("state_digest" in reason for reason in body_reasons))

    def test_handoff_digest_tracks_the_normalized_spec(self) -> None:
        self.seed(status="draft", task_status="pending", issue_status="open")
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "保持兼容", "保持兼容并限制响应时间"
            ),
            encoding="utf-8",
        )

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("state_digest" in reason for reason in reasons))

    def test_delivering_cannot_stop_while_commit_paths_still_differ(self) -> None:
        pending = """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>"""
        self.make_delivering(pending)

        with (
            patch.object(wali_stop, "read_status_xml", return_value=pending),
            patch.object(wali_stop, "is_verified_working_copy_root", return_value=True),
            patch.object(
                wali_stop,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
        ):
            reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("尚未提交成功" in reason for reason in reasons))

    def test_delivering_cannot_stop_without_a_success_receipt(self) -> None:
        clean = "<?xml version=\"1.0\"?><status><target path=\".\"></target></status>"
        self.make_delivering(clean)

        with (
            patch.object(wali_stop, "read_status_xml", return_value=clean),
            patch.object(wali_stop, "is_verified_working_copy_root", return_value=True),
            patch.object(
                wali_stop,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
        ):
            reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("交付回执" in reason for reason in reasons))

    def test_delivering_stops_after_clean_exact_commit_with_receipt(self) -> None:
        clean = "<?xml version=\"1.0\"?><status><target path=\".\"></target></status>"
        self.make_delivering(clean)
        receipt_path = self.root / ".svn" / "wali-policy" / "delivery-G-001.json"
        receipt_path.parent.mkdir(parents=True)
        contract = wali_policy.load_contract(self.root)
        fingerprint = wali_policy._path_fingerprint(
            self.root, "src/feature/service.py"
        )
        receipt_path.write_text(
            json.dumps(
                {
                    "goal_id": "G-001",
                    "paths": ["src/feature/service.py"],
                    "authorization_digest": wali_policy._delivery_authorization_digest(
                        contract
                    ),
                    "commit_revision": "42",
                    "precommit": {
                        "src/feature/service.py": {
                            "item": "modified",
                            "fingerprint": fingerprint,
                            "kind": "file",
                        }
                    },
                    "fingerprints": {"src/feature/service.py": fingerprint},
                    "revisions": {"src/feature/service.py": "42"},
                    "recorded_at": "2026-07-22T12:30:00+08:00",
                }
            ),
            encoding="utf-8",
        )

        with (
            patch.object(wali_stop, "read_status_xml", return_value=clean),
            patch.object(wali_stop, "is_verified_working_copy_root", return_value=True),
            patch.object(
                wali_stop,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_policy,
                "_svn_last_changed_revisions",
                return_value={"src/feature/service.py": "42"},
            ),
        ):
            reasons = wali_stop.evaluate_project(self.root)

        self.assertEqual(reasons, [])

        with (
            patch.object(wali_stop, "read_status_xml", return_value=clean),
            patch.object(wali_stop, "is_verified_working_copy_root", return_value=True),
            patch.object(
                wali_stop,
                "discover_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(
                wali_policy,
                "_svn_last_changed_revisions",
                return_value={"src/feature/service.py": "43"},
            ),
        ):
            stale_reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("修订号" in reason for reason in stale_reasons))

    def test_recorded_block_still_enforces_work_graph_consistency(self) -> None:
        self.seed(
            status="blocked",
            blocked_reason="缺少外部系统访问权限",
            task_status="blocked",
        )
        self.add_dependency_cycle()

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("任务依赖存在环" in reason for reason in reasons))

    def test_direction_wait_still_enforces_work_graph_consistency(self) -> None:
        self.seed(
            status="waiting_user",
            waiting_for="direction",
            waiting_detail="请用户选择兼容方案 A 或 B",
            automatic_status="pending",
            task_status="working",
        )
        self.add_dependency_cycle()

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("任务依赖存在环" in reason for reason in reasons))

    def test_malformed_table_row_is_reported_instead_of_dropped(self) -> None:
        self.seed(issue_status="open")
        issues = (self.state / "issues.md").read_text(encoding="utf-8")
        (self.state / "issues.md").write_text(
            issues.replace("示例", "bad | unescaped"), encoding="utf-8"
        )
        reasons = wali_stop.evaluate_project(self.root)
        self.assertTrue(any("issues.md" in reason and "列数错误" in reason for reason in reasons))

    def test_main_table_row_with_an_empty_id_is_not_dropped(self) -> None:
        self.seed()
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        todo += (
            "|  | AC-01 | 遗漏编号的任务 | developer | required | pending | 无 | src/other | "
            "不应被忽略 | 待补充 | 待分配 |\n"
        )
        self.write("todo.md", todo)

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("任务 ID 格式无效" in reason for reason in reasons))

    def test_active_goal_rejects_a_cyclic_work_graph(self) -> None:
        self.seed()
        self.add_dependency_cycle()

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("任务依赖存在环" in reason for reason in reasons))

    def test_optional_done_task_also_requires_independent_evidence(self) -> None:
        self.seed()
        todo = (self.state / "todo.md").read_text(encoding="utf-8")
        todo += (
            "| T-002 | AC-01 | 可选整理 | developer | optional | done | T-001 | docs | "
            "文档清晰 | 待补充 | developer |\n"
        )
        self.write("todo.md", todo)

        reasons = wali_stop.evaluate_project(self.root)

        self.assertTrue(any("T-002" in reason and "证据" in reason for reason in reasons))

    def test_done_goal_still_enforces_completion_checks(self) -> None:
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
