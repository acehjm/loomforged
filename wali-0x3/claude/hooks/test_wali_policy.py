"""Black-box tests for the WALI phase/effect policy hook."""

from __future__ import annotations

import io
import json
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import wali_policy
import wali_svn


MODULE_PATH = Path(__file__).with_name("wali_policy.py")


class WaliPolicyCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "docs" / "wali-0x3"
        self.state.mkdir(parents=True)
        self.write_spec()
        self.write_contract()
        (self.state / "handoff.md").write_text("# 可恢复交接\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_spec(self) -> None:
        (self.state / "spec.md").write_text(
            """---
spec_id: SPEC-G-001
goal_id: G-001
source_mode: pressure_test
---
# 规格说明书

## 1. 输入与形成方式

- 输入：用户需求。
- 形成方式：规格压力测试。

## 2. 规范需求

| ID | 类型 | 规范要求 | 来源 | 关联 AC |
| --- | --- | --- | --- | --- |
| R-001 | functional | 系统必须交付可自动验证的结果 | 用户需求 | AC-01 |
| R-002 | acceptance | 最终业务结果必须由用户确认 | WALI 约束 | AC-02 |

## 3. 行为与边界

- 正常路径、失败路径与边界条件均按 Goal 范围处理。

## 4. 接口、数据与错误

- 不适用：当前测试夹具不引入外部接口。

## 5. 质量属性与兼容性

- 保持现有兼容性，自动检查必须通过。

## 6. 验收判定规则

| AC ID | 判定规则 | 验证方法 |
| --- | --- | --- |
| AC-01 | 自动检查退出码为 0 | 运行 Goal 声明的检查命令 |
| AC-02 | 用户明确确认业务结果 | 用户回测 |
""",
            encoding="utf-8",
        )

    def write_contract(self, *, extra: str = "") -> None:
        (self.state / "goal.md").write_text(
            f"""---
wali_schema: 1
goal_id: G-001
status: draft
phase: clarifying
active_task: none
goal_confirmation: pending
goal_confirmation_evidence: ""
goal_definition_digest: ""
allowed_effects:
  - read_workspace
  - ask_user
  - update_goal_draft
  - update_spec_draft
  - update_handoff
allowed_capabilities:
  - Skill:wali-start
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/spec.md
  - docs/wali-0x3/handoff.md
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
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
{extra}---

# 目标契约
""",
            encoding="utf-8",
        )

    def test_contract_requires_the_current_wali_schema(self) -> None:
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "wali_schema: 1\n", "", 1
            ),
            encoding="utf-8",
        )

        reasons = wali_policy.validate_contract(
            wali_policy.load_contract(self.root)
        )

        self.assertTrue(
            any("wali_schema" in reason for reason in reasons),
            reasons,
        )

    def test_contract_rejects_an_unsupported_wali_schema(self) -> None:
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "wali_schema: 1", "wali_schema: 2", 1
            ),
            encoding="utf-8",
        )

        reasons = wali_policy.validate_contract(
            wali_policy.load_contract(self.root)
        )

        self.assertTrue(
            any("不支持的 wali_schema" in reason for reason in reasons),
            reasons,
        )

    def seal_goal(self) -> None:
        result = self.run_policy("digest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        digest = result.stdout.strip()
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            __import__("re").sub(
                r'goal_definition_digest: "[0-9a-f]*"',
                f'goal_definition_digest: "{digest}"',
                goal_path.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )

    def add_capability(self, kind: str, name: str, *, unsafe: str = "") -> None:
        if kind == "Skill":
            path = self.root / "claude" / "skills" / name / "SKILL.md"
        else:
            path = self.root / "claude" / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        disable_shell = "disable-model-invocation: true\n" if kind == "Skill" else ""
        path.write_text(
            f"---\nname: {name}\n{disable_shell}---\n# Identity\n{unsafe}\n",
            encoding="utf-8",
        )

    def write_implementing_contract(self) -> None:
        (self.state / "goal.md").write_text(
            """---
wali_schema: 1
goal_id: G-001
status: active
phase: implementing
active_task: T-001
goal_confirmation: confirmed
goal_confirmation_evidence: "用户在会话中确认 Goal G-001"
goal_definition_digest: ""
allowed_effects:
  - read_workspace
  - ask_user
  - update_todo
  - update_issues
  - update_handoff
  - transition_phase
  - modify_implementation
  - manage_svn_schedule
  - sync_svn_working_copy
  - run_project_commands
allowed_capabilities:
  - Agent:developer
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/todo.md
  - docs/wali-0x3/issues.md
  - docs/wali-0x3/handoff.md
  - "@active_task"
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
allow_new_artifacts: true
allow_implementation_changes: true
allow_external_writes: false
allow_svn_commit: false
---

# 目标契约

## 2. 已确认事实

- 用户需要一个可验证的功能。

## 3. 高影响未知项

无未解决问题。

## 4. 决策记录

- 使用现有项目结构。

## 5. 目标与背景

### 目标

交付可由自动检查和用户回测验证的功能。

### 背景

现有功能缺失。

## 6. 范围与约束

- 范围：`src/feature/**`。
- 不在范围：其他模块。
- 约束：保持兼容。

## 7. 验收标准

| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 策略测试通过 | pending | 待验证 |
| AC-02 | human | 用户回测通过 | pending | 待用户验收 |

## 检查方式

| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
| 策略测试 | `python3 -m unittest -v` | 退出码 0 |
""",
            encoding="utf-8",
        )
        (self.state / "todo.md").write_text(
            """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现功能 | developer | required | working | 无 | `src/feature/**` | 测试通过 | 待补充 | 待分配 |
""",
            encoding="utf-8",
        )
        (self.state / "issues.md").write_text("# 问题清单\n", encoding="utf-8")
        self.seal_goal()

    def write_delivering_contract(self) -> None:
        service = self.root / "src" / "feature" / "service.py"
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("implemented\n", encoding="utf-8")
        fingerprint = hashlib.sha256(b"file\0implemented\n").hexdigest()
        (self.state / "goal.md").write_text(
            f"""---
wali_schema: 1
goal_id: G-001
status: done
phase: delivering
active_task: none
goal_confirmation: confirmed
goal_confirmation_evidence: "用户确认 Goal G-001"
goal_definition_digest: ""
allowed_effects:
  - read_workspace
  - update_handoff
  - transition_phase
allowed_capabilities:
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/handoff.md
  - "@svn_commit"
svn_commit_paths:
  - src/feature/service.py
svn_commit_evidence: "用户授权提交 src/feature/service.py"
preexisting_changes:
carry_epoch: 1
carried_history:
carried_changes:
  - "src/feature/service.py::{fingerprint}"
stop_intent: continue
waiting_for: none
waiting_detail: ""
blocked_reason: ""
exit_outcome: completed
exit_reason: "用户已验收，进入 SVN 精确交付"
exit_evidence: "AC-01 自动检查和 AC-02 用户验收均已通过"
exit_change_disposition: none
superseded_by: none
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: true
---
# Goal

## 2. 已确认事实
- 功能已经实现并验证。
## 3. 高影响未知项
- 无。
## 4. 决策记录
- 提交精确文件。
## 5. 目标与背景
- 目标：交付已验证功能。
## 6. 范围与约束
- 范围：`src/feature/service.py`；不包含其他路径。
## 7. 验收标准
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动检查通过 | verified | exit 0 |
| AC-02 | human | 用户验收通过 | verified | 用户确认 |
## 8. 检查方式
| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
| 单元测试 | `python3 -m unittest -v` | 退出码 0 |
""",
            encoding="utf-8",
        )
        (self.state / "todo.md").write_text(
            """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现功能 | developer | required | done | 无 | `src/feature/**` | 测试通过 | test exit 0 | tester |
""",
            encoding="utf-8",
        )
        (self.state / "issues.md").write_text(
            """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
            encoding="utf-8",
        )
        self.seal_goal()

    def clarifying_from_delivery(
        self, delivery: str, *, next_goal_id: str = "G-001", reset_carry: bool = False
    ) -> str:
        prospective = delivery.replace("goal_id: G-001", f"goal_id: {next_goal_id}", 1)
        prospective = prospective.replace("status: done", "status: draft", 1)
        prospective = prospective.replace("phase: delivering", "phase: clarifying", 1)
        prospective = prospective.replace(
            "goal_confirmation: confirmed", "goal_confirmation: pending", 1
        )
        prospective = prospective.replace(
            'goal_confirmation_evidence: "用户确认 Goal G-001"',
            'goal_confirmation_evidence: ""',
            1,
        )
        prospective = re.sub(
            r'(?m)^goal_definition_digest:\s*".*"$',
            'goal_definition_digest: ""',
            prospective,
            count=1,
        )
        prospective = prospective.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal_draft\n"
            "  - update_spec_draft\n"
            "  - update_handoff",
            1,
        )
        prospective = prospective.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md\n"
            "  - \"@svn_commit\"\n"
            "svn_commit_paths:\n"
            "  - src/feature/service.py\n"
            "svn_commit_evidence: \"用户授权提交 src/feature/service.py\"\n",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/spec.md\n"
            "  - docs/wali-0x3/handoff.md\n",
            1,
        )
        prospective = prospective.replace("exit_outcome: completed", "exit_outcome: none", 1)
        prospective = prospective.replace(
            'exit_reason: "用户已验收，进入 SVN 精确交付"',
            'exit_reason: ""',
            1,
        )
        prospective = prospective.replace(
            'exit_evidence: "AC-01 自动检查和 AC-02 用户验收均已通过"',
            'exit_evidence: ""',
            1,
        )
        prospective = prospective.replace("allow_svn_commit: true", "allow_svn_commit: false", 1)
        if reset_carry:
            prospective = prospective.replace("carry_epoch: 1", "carry_epoch: 0", 1)
            prospective = re.sub(
                r'(?m)^  - "src/feature/service\.py::[0-9a-f]{64}"\n',
                "",
                prospective,
                count=1,
            )
        return prospective

    def run_policy(
        self, command: str, *, payload: dict[str, object] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                command,
            ],
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True,
            check=False,
            text=True,
        )

    def test_check_accepts_complete_clarifying_contract(self) -> None:
        result = self.run_policy("check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WALI 阶段契约检查通过", result.stdout)

    def test_clarifying_hook_denies_implementation_edit(self) -> None:
        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(self.root / "src" / "app.py"),
                    "old_string": "before",
                    "new_string": "after",
                },
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("src/app.py", decision["permissionDecisionReason"])

    def test_clarifying_question_round_is_limited_to_one_to_three(self) -> None:
        allowed = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "AskUserQuestion",
                "tool_input": {
                    "questions": [
                        {"question": "期望的用户结果是什么？"},
                        {"question": "哪些行为明确不在范围内？"},
                    ]
                },
            },
        )
        denied = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "AskUserQuestion",
                "tool_input": {
                    "questions": [
                        {"question": "Q1"},
                        {"question": "Q2"},
                        {"question": "Q3"},
                        {"question": "Q4"},
                    ]
                },
            },
        )

        self.assertEqual(allowed.stdout, "", allowed.stdout)
        reason = json.loads(denied.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("1–3", reason)

    def test_clarifying_hook_allows_goal_and_handoff_updates(self) -> None:
        for relative_path in (
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
        ):
            with self.subTest(path=relative_path):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Edit",
                        "tool_input": {
                            "file_path": str(self.root / relative_path),
                            "old_string": (
                                "# 目标契约"
                                if relative_path.endswith("goal.md")
                                else "# 可恢复交接"
                            ),
                            "new_string": (
                                "# 目标契约\n"
                                if relative_path.endswith("goal.md")
                                else "# 可恢复交接\n"
                            ),
                        },
                    },
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_clarifying_hook_allows_recreating_fixed_handoff_state_file(self) -> None:
        (self.state / "handoff.md").unlink()

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "handoff.md"),
                    "content": "# 自动生成的交接",
                },
            },
        )

        self.assertEqual(result.stdout, "", result.stdout)

    def test_clarifying_hook_allows_read_only_bash(self) -> None:
        for command in (
            "pwd",
            "svn status",
            "svn status -u",
            "svn info --show-item wc-root",
            "svn diff --internal-diff docs/wali-0x3/goal.md",
            "svn log -l 5",
            "python3 .claude/hooks/wali_policy.py check",
            "python3 .claude/hooks/wali_policy.py --project-root . check",
            "python3 .claude/hooks/wali_policy.py baseline",
            "python3 .claude/hooks/wali_graph.py --project-root . check",
            "python3 .claude/hooks/wali_stop.py --project-root .",
            "python3 .claude/hooks/wali_supervision.py --project-root . status",
        ):
            with self.subTest(command=command):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_read_only_bash_rejects_shell_and_path_escape_tricks(self) -> None:
        link = self.root / "outside-link"
        link.symlink_to(self.root.parent)
        commands = (
            "cat $HOME/.ssh/id_rsa",
            "cat docs/wali-0x3/goal.md",
            "rg -n 'Goal' docs/wali-0x3/goal.md",
            "cat ${HOME}/.ssh/id_rsa",
            "./cat docs/wali-0x3/goal.md",
            "sed --in-place=.bak s/a/b/ docs/wali-0x3/goal.md",
            "sed -n 'w .svn/wali-policy/forged.json' docs/wali-0x3/goal.md",
            "find . -print",
            "rg --pre touch Goal docs/wali-0x3/goal.md",
            "rg --hostname-bin=touch Goal docs/wali-0x3/goal.md",
            "rg -z Goal docs/wali-0x3/goal.md",
            "rg Goal --ignore-file=/etc/passwd docs/wali-0x3/goal.md",
            "rg -f../memory-distill/storage.md Goal CLAUDE.md",
            "grep -f../memory-distill/storage.md CLAUDE.md",
            "file -m../memory-distill/storage.md CLAUDE.md",
            "file --compile -m docs/wali-0x3/goal.md",
            "svn diff --diff-cmd touch docs/wali-0x3/goal.md",
            "svn diff --config-dir claude/fixtures/svn-config docs/wali-0x3/goal.md",
            "svn diff --config-dir=claude/fixtures/svn-config docs/wali-0x3/goal.md",
            "svn diff --config-option config:helpers:diff-cmd=touch docs/wali-0x3/goal.md",
            "svn diff docs/wali-0x3/goal.md",
            "svn cat ^/secret",
            "cat docs/wali-0x3/goal.md & touch context.md",
            "cat outside-link/secret.txt",
            "python3 .claude/hooks/wali_policy.py --project-root=outside-link check",
            "python3 .claude/hooks/wali_policy.py audit --status-xml=outside-link/status.xml",
            "cat {../memory-distill/SKILL.md,CLAUDE.md}",
            "rg foo {--pre=rm,../memory-distill/SKILL.md}",
            "grep -R secret .",
            "ls -LR .",
        )
        for command in commands:
            with self.subTest(command=command):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                )
                self.assertNotEqual(result.stdout, "")
                self.assertEqual(
                    json.loads(result.stdout)["hookSpecificOutput"][
                        "permissionDecision"
                    ],
                    "deny",
                )

    def test_read_workspace_does_not_authorize_reads_outside_project(self) -> None:
        outside = self.root.parent / "outside-secret.txt"
        for tool_name, tool_input in (
            ("Read", {"file_path": str(outside)}),
            ("Glob", {"path": str(self.root.parent), "pattern": "*"}),
            ("Grep", {"path": "../", "pattern": "secret"}),
            ("Bash", {"command": "cat ../outside-secret.txt"}),
        ):
            with self.subTest(tool=tool_name):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    },
                )

                reason = json.loads(result.stdout)["hookSpecificOutput"][
                    "permissionDecisionReason"
                ]
                self.assertIn("工作区", reason)

    def test_hook_denies_svn_commit_when_contract_forbids_it(self) -> None:
        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "svn commit -m 'premature'"},
            },
        )

        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("allow_svn_commit", reason)

    def test_implementing_hook_only_allows_active_task_scope(self) -> None:
        self.write_implementing_contract()
        allowed_path = self.root / "src" / "feature" / "service.py"
        denied_path = self.root / "src" / "unrelated.py"
        allowed_path.parent.mkdir(parents=True)
        allowed_path.write_text("before\n", encoding="utf-8")
        denied_path.write_text("before\n", encoding="utf-8")

        allowed = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(allowed_path)},
            },
        )
        denied = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(denied_path)},
            },
        )

        self.assertEqual(allowed.stdout, "", allowed.stdout)
        output = json.loads(denied.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("write_scope", reason)
        self.assertIn("src/unrelated.py", reason)

    def test_svn_metadata_is_never_an_active_task_write_scope(self) -> None:
        self.write_implementing_contract()
        todo_path = self.state / "todo.md"
        todo_path.write_text(
            todo_path.read_text(encoding="utf-8").replace(
                "`src/feature/**`", "`.svn/wali-policy/**`"
            ),
            encoding="utf-8",
        )
        contract = wali_policy.load_contract(self.root)
        receipt = self.root / ".svn" / "wali-policy" / "delivery-G-001.json"
        decision = wali_policy.decide_tool(
            self.root,
            contract,
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(receipt),
                    "content": "forged",
                },
            },
        )
        validation = wali_policy.validate_project_contract(self.root, contract)

        self.assertFalse(decision.allowed)
        self.assertTrue(any("控制面" in reason for reason in validation))

    def test_implementing_contract_requires_confirmed_goal_with_evidence(self) -> None:
        self.write_implementing_contract()
        goal = (self.state / "goal.md").read_text(encoding="utf-8")
        goal = goal.replace(
            "goal_confirmation: confirmed",
            "goal_confirmation: pending",
        ).replace(
            'goal_confirmation_evidence: "用户在会话中确认 Goal G-001"',
            'goal_confirmation_evidence: ""',
        )
        (self.state / "goal.md").write_text(goal, encoding="utf-8")

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("goal_confirmation", result.stdout)
        self.assertIn("goal_confirmation_evidence", result.stdout)

    def test_goal_confirmation_transition_requires_live_user_confirmation(self) -> None:
        body = """# 目标契约

## 2. 已确认事实
- 用户需要可验证结果。
## 3. 高影响未知项
- 无。
## 4. 决策记录
- 复用现有结构。
## 5. 目标与背景
- 交付可观察结果。
## 6. 范围与约束
- 只修改明确范围。
## 7. 验收标准
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| AC-01 | automatic | 自动检查通过 | pending | 待验证 |
| AC-02 | human | 用户回测通过 | pending | 待用户验收 |
## 8. 检查方式
| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
| 策略测试 | `python3 -m unittest -v` | 退出码 0 |
"""
        prospective = f"""---
wali_schema: 1
goal_id: G-001
status: active
phase: planning
active_task: none
goal_confirmation: confirmed
goal_confirmation_evidence: "用户确认当前 Goal 包"
goal_definition_digest: ""
allowed_effects:
  - read_workspace
  - ask_user
  - update_goal
  - update_todo
  - update_issues
  - update_handoff
allowed_capabilities:
  - Skill:wali-start
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/todo.md
  - docs/wali-0x3/issues.md
  - docs/wali-0x3/handoff.md
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
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
---

{body}"""
        prospective_contract = dict(wali_policy.parse_frontmatter(prospective))
        digest = wali_policy._goal_definition_digest_from_text(
            prospective,
            prospective_contract,
            (self.state / "spec.md").read_text(encoding="utf-8"),
        )
        prospective = prospective.replace(
            'goal_definition_digest: ""', f'goal_definition_digest: "{digest}"'
        )

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "goal.md"),
                    "content": prospective,
                },
            },
        )

        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "ask")
        self.assertIn("Goal 与 Spec", output["permissionDecisionReason"])

    def test_phase_transition_cannot_skip_independent_inspection(self) -> None:
        self.write_implementing_contract()
        goal = (self.state / "goal.md").read_text(encoding="utf-8")
        prospective = goal.replace("status: active", "status: done").replace(
            "phase: implementing", "phase: closed"
        ).replace("active_task: T-001", "active_task: none")
        prospective = prospective.replace("exit_outcome: none", "exit_outcome: completed")
        prospective = prospective.replace('exit_reason: ""', 'exit_reason: "用户已验收"')
        prospective = prospective.replace(
            'exit_evidence: ""', 'exit_evidence: "自动检查和用户验收已通过"'
        )
        prospective = prospective.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_todo\n"
            "  - update_issues\n"
            "  - update_handoff\n"
            "  - transition_phase\n"
            "  - modify_implementation\n"
            "  - manage_svn_schedule\n"
            "  - sync_svn_working_copy\n"
            "  - run_project_commands",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
        ).replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/todo.md\n"
            "  - docs/wali-0x3/issues.md\n"
            "  - docs/wali-0x3/handoff.md\n"
            "  - \"@active_task\"",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md",
        ).replace("allow_new_artifacts: true", "allow_new_artifacts: false").replace(
            "allow_implementation_changes: true",
            "allow_implementation_changes: false",
        )

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "goal.md"),
                    "content": prospective,
                },
            },
        )

        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("阶段闭环", output["permissionDecisionReason"])

    def test_confirmed_goal_definition_is_bound_to_digest(self) -> None:
        self.write_implementing_contract()
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "其他模块", "其他模块和数据迁移"
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("用户确认后变化", result.stdout)

    def test_confirmed_goal_definition_digest_binds_the_complete_spec(self) -> None:
        self.write_implementing_contract()
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "保持现有兼容性", "保持现有兼容性并限制响应时间"
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("用户确认后变化", result.stdout)

    def test_confirmed_goal_requires_a_complete_spec_oracle(self) -> None:
        self.write_implementing_contract()
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "| AC-02 | 用户明确确认业务结果 | 用户回测 |\n", ""
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-02 缺少规格判定规则", result.stdout)

    def test_confirmed_goal_requires_explicit_spec_behavior_and_boundaries(self) -> None:
        self.write_implementing_contract()
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "- 正常路径、失败路径与边界条件均按 Goal 范围处理。",
                "- 待补充。",
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("行为、场景与边界", result.stdout)

    def test_spec_is_writable_only_while_clarifying(self) -> None:
        clarifying = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "spec.md"),
                    "content": (self.state / "spec.md").read_text(encoding="utf-8"),
                },
            },
        )
        self.assertEqual(clarifying.stdout, "", clarifying.stdout)

        self.write_implementing_contract()
        implementing = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.state / "spec.md"),
                    "content": (self.state / "spec.md").read_text(encoding="utf-8"),
                },
            },
        )
        reason = json.loads(implementing.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("update_spec_draft", reason)

    def test_non_terminal_phase_cannot_claim_an_exit_outcome(self) -> None:
        contract = wali_policy.load_contract(self.root)
        contract["exit_outcome"] = "cancelled"
        contract["exit_reason"] = "用户取消"
        contract["exit_evidence"] = "用户明确要求停止"
        contract["exit_change_disposition"] = "preserve"

        reasons = wali_policy.validate_contract(contract)

        self.assertTrue(any("非退出阶段" in reason for reason in reasons))

    def test_terminated_phase_requires_a_typed_reasoned_exit(self) -> None:
        contract = wali_policy.load_contract(self.root)
        contract.update(
            {
                "status": "cancelled",
                "phase": "terminated",
                "allowed_effects": (
                    "read_workspace",
                    "update_handoff",
                    "transition_phase",
                ),
                "write_scope": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "exit_outcome": "cancelled",
                "exit_reason": "用户明确取消当前 Goal",
                "exit_evidence": "会话消息：停止当前工作",
                "exit_change_disposition": "preserve",
            }
        )

        self.assertEqual(wali_policy.validate_contract(contract), [])

        contract["exit_reason"] = ""
        reasons = wali_policy.validate_contract(contract)
        self.assertTrue(any("exit_reason" in reason for reason in reasons))

    def test_entering_terminated_requires_live_user_confirmation(self) -> None:
        goal_path = self.state / "goal.md"
        prospective = goal_path.read_text(encoding="utf-8")
        prospective = prospective.replace("status: draft", "status: cancelled")
        prospective = prospective.replace("phase: clarifying", "phase: terminated")
        prospective = prospective.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal_draft\n"
            "  - update_spec_draft\n"
            "  - update_handoff",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
        )
        prospective = prospective.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/spec.md\n"
            "  - docs/wali-0x3/handoff.md",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md",
        )
        prospective = prospective.replace("exit_outcome: none", "exit_outcome: cancelled")
        prospective = prospective.replace('exit_reason: ""', 'exit_reason: "用户明确取消"')
        prospective = prospective.replace(
            'exit_evidence: ""', 'exit_evidence: "会话消息：停止当前工作"'
        )
        prospective = prospective.replace(
            "exit_change_disposition: none", "exit_change_disposition: preserve"
        )

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(goal_path),
                    "content": prospective,
                },
            },
        )

        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "ask")
        self.assertIn("退出", output["permissionDecisionReason"])

    def test_entering_terminated_requires_current_implementation_diffs_to_be_frozen(self) -> None:
        self.write_implementing_contract()
        (self.root / ".svn").mkdir()
        goal_path = self.state / "goal.md"
        prospective = goal_path.read_text(encoding="utf-8")
        prospective = prospective.replace("status: active", "status: cancelled")
        prospective = prospective.replace("phase: implementing", "phase: terminated")
        prospective = prospective.replace("active_task: T-001", "active_task: none")
        prospective = prospective.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_todo\n"
            "  - update_issues\n"
            "  - update_handoff\n"
            "  - transition_phase\n"
            "  - modify_implementation\n"
            "  - manage_svn_schedule\n"
            "  - sync_svn_working_copy\n"
            "  - run_project_commands",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
        )
        prospective = prospective.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/todo.md\n"
            "  - docs/wali-0x3/issues.md\n"
            "  - docs/wali-0x3/handoff.md\n"
            "  - \"@active_task\"",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md",
        )
        prospective = prospective.replace("exit_outcome: none", "exit_outcome: cancelled")
        prospective = prospective.replace('exit_reason: ""', 'exit_reason: "用户取消"')
        prospective = prospective.replace(
            'exit_evidence: ""', 'exit_evidence: "会话消息：停止当前工作"'
        )
        prospective = prospective.replace(
            "exit_change_disposition: none", "exit_change_disposition: preserve"
        )
        prospective = prospective.replace("allow_new_artifacts: true", "allow_new_artifacts: false")
        prospective = prospective.replace(
            "allow_implementation_changes: true",
            "allow_implementation_changes: false",
        )
        status_xml = """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>"""
        contract = wali_policy.load_contract(self.root)

        with patch.object(
            wali_policy, "_status_xml_from_svn", return_value=status_xml
        ), patch.object(
            wali_policy, "_svn_working_copy_root", return_value=self.root.resolve()
        ):
            decision = wali_policy.decide_tool(
                self.root,
                contract,
                {
                    "tool_name": "Write",
                    "tool_input": {
                        "file_path": str(goal_path),
                        "content": prospective,
                    },
                },
            )

        self.assertFalse(decision.allowed)
        self.assertIn("退出前必须先冻结", decision.reason)

    def test_terminated_can_only_start_a_different_goal_with_confirmation(self) -> None:
        goal_path = self.state / "goal.md"
        terminated = goal_path.read_text(encoding="utf-8")
        terminated = terminated.replace("status: draft", "status: cancelled")
        terminated = terminated.replace("phase: clarifying", "phase: terminated")
        terminated = terminated.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal_draft\n"
            "  - update_spec_draft\n"
            "  - update_handoff",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
        )
        terminated = terminated.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/spec.md\n"
            "  - docs/wali-0x3/handoff.md",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md",
        )
        terminated = terminated.replace("exit_outcome: none", "exit_outcome: cancelled")
        terminated = terminated.replace('exit_reason: ""', 'exit_reason: "用户取消"')
        terminated = terminated.replace(
            'exit_evidence: ""', 'exit_evidence: "会话消息：停止当前工作"'
        )
        terminated = terminated.replace(
            "exit_change_disposition: none", "exit_change_disposition: preserve"
        )
        goal_path.write_text(terminated, encoding="utf-8")
        contract = wali_policy.load_contract(self.root)

        next_goal = terminated.replace("goal_id: G-001", "goal_id: G-002")
        next_goal = next_goal.replace("status: cancelled", "status: draft")
        next_goal = next_goal.replace("phase: terminated", "phase: clarifying")
        next_goal = next_goal.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - update_handoff\n"
            "  - transition_phase",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal_draft\n"
            "  - update_spec_draft\n"
            "  - update_handoff",
        )
        next_goal = next_goal.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/handoff.md",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/spec.md\n"
            "  - docs/wali-0x3/handoff.md",
        )
        next_goal = next_goal.replace("exit_outcome: cancelled", "exit_outcome: none")
        next_goal = next_goal.replace('exit_reason: "用户取消"', 'exit_reason: ""')
        next_goal = next_goal.replace(
            'exit_evidence: "会话消息：停止当前工作"', 'exit_evidence: ""'
        )
        next_goal = next_goal.replace(
            "exit_change_disposition: preserve", "exit_change_disposition: none"
        )
        next_goal = next_goal.replace("  - Skill:wali-start\n", "")
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(goal_path),
                "content": next_goal,
            },
        }

        decision = wali_policy.decide_tool(self.root, contract, payload)
        self.assertTrue(decision.allowed, decision.reason)
        self.assertTrue(decision.requires_user_confirmation)

        inherited_carry = next_goal.replace("carry_epoch: 0", "carry_epoch: 7")
        inherited_carry = inherited_carry.replace(
            "carried_history:\ncarried_changes:",
            'carried_history:\n  - "1::src/old.py::missing"\n'
            'carried_changes:\n  - "src/old.py::missing"',
        )
        payload["tool_input"]["content"] = inherited_carry
        denied_inherited_carry = wali_policy.decide_tool(
            self.root, contract, payload
        )
        self.assertFalse(denied_inherited_carry.allowed)
        self.assertIn("全新治理代次", denied_inherited_carry.reason)

        inherited_baseline = next_goal.replace(
            "preexisting_changes:\n",
            'preexisting_changes:\n  - "src/user-change.py::missing"\n',
            1,
        )
        payload["tool_input"]["content"] = inherited_baseline
        denied_inherited_baseline = wali_policy.decide_tool(
            self.root, contract, payload
        )
        self.assertFalse(denied_inherited_baseline.allowed)
        self.assertIn("保护基线", denied_inherited_baseline.reason)

        same_goal = next_goal.replace("goal_id: G-002", "goal_id: G-001")
        payload["tool_input"]["content"] = same_goal
        denied = wali_policy.decide_tool(self.root, contract, payload)
        self.assertFalse(denied.allowed)
        self.assertIn("不同的 Goal ID", denied.reason)

    def test_completed_delivery_is_frozen_but_precommit_delivery_can_return_with_confirmation(self) -> None:
        self.write_delivering_contract()
        goal_path = self.state / "goal.md"
        delivery = goal_path.read_text(encoding="utf-8")
        contract = wali_policy.load_contract(self.root)
        same_goal = self.clarifying_from_delivery(delivery)
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(goal_path),
                "content": same_goal,
            },
        }

        with patch.object(
            wali_policy, "_delivery_transition_state", return_value="completed"
        ):
            frozen = wali_policy.decide_tool(self.root, contract, payload)
        self.assertFalse(frozen.allowed)
        self.assertIn("不同的 Goal ID", frozen.reason)

        new_goal = self.clarifying_from_delivery(
            delivery, next_goal_id="G-002", reset_carry=True
        )
        payload["tool_input"]["content"] = new_goal
        with patch.object(
            wali_policy, "_delivery_transition_state", return_value="completed"
        ):
            reset = wali_policy.decide_tool(self.root, contract, payload)
        self.assertTrue(reset.allowed, reset.reason)
        self.assertTrue(reset.requires_user_confirmation)

        payload["tool_input"]["content"] = same_goal
        with patch.object(
            wali_policy, "_delivery_transition_state", return_value="precommit"
        ):
            correction = wali_policy.decide_tool(self.root, contract, payload)
        self.assertTrue(correction.allowed, correction.reason)
        self.assertTrue(correction.requires_user_confirmation)
        self.assertIn("撤销", correction.reason)

    def test_accepting_cannot_enter_success_until_the_complete_graph_is_valid(self) -> None:
        self.write_delivering_contract()
        goal_path = self.state / "goal.md"
        delivery = goal_path.read_text(encoding="utf-8")
        digest = re.search(
            r'(?m)^goal_definition_digest:\s*"([0-9a-f]{64})"$',
            delivery,
        )
        self.assertIsNotNone(digest)
        accepting = self.clarifying_from_delivery(delivery)
        accepting = accepting.replace("status: draft", "status: waiting_user", 1)
        accepting = accepting.replace("phase: clarifying", "phase: accepting", 1)
        accepting = accepting.replace(
            "goal_confirmation: pending", "goal_confirmation: confirmed", 1
        )
        accepting = accepting.replace(
            'goal_confirmation_evidence: ""',
            'goal_confirmation_evidence: "用户确认 Goal G-001"',
            1,
        )
        accepting = accepting.replace(
            'goal_definition_digest: ""',
            f'goal_definition_digest: "{digest.group(1)}"',
            1,
        )
        accepting = accepting.replace(
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal_draft\n"
            "  - update_spec_draft\n"
            "  - update_handoff",
            "allowed_effects:\n"
            "  - read_workspace\n"
            "  - ask_user\n"
            "  - update_goal\n"
            "  - update_issues\n"
            "  - update_handoff",
            1,
        )
        accepting = accepting.replace(
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/spec.md\n"
            "  - docs/wali-0x3/handoff.md",
            "write_scope:\n"
            "  - docs/wali-0x3/goal.md\n"
            "  - docs/wali-0x3/issues.md\n"
            "  - docs/wali-0x3/handoff.md",
            1,
        )
        accepting = accepting.replace("waiting_for: none", "waiting_for: acceptance", 1)
        accepting = accepting.replace(
            'waiting_detail: ""',
            'waiting_detail: "请用户完成业务回测"',
            1,
        )
        goal_path.write_text(accepting, encoding="utf-8")
        contract = wali_policy.load_contract(self.root)
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(goal_path),
                "content": delivery,
            },
        }

        allowed = wali_policy.decide_tool(self.root, contract, payload)

        self.assertTrue(allowed.allowed, allowed.reason)
        self.assertTrue(allowed.requires_user_confirmation)
        self.assertIn("业务验收", allowed.reason)

        todo_path = self.state / "todo.md"
        todo_path.write_text(
            todo_path.read_text(encoding="utf-8").replace(
                "| required | done |", "| required | pending |"
            ),
            encoding="utf-8",
        )
        denied = wali_policy.decide_tool(self.root, contract, payload)

        self.assertFalse(denied.allowed)
        self.assertIn("成功收尾条件未满足", denied.reason)
        self.assertIn("required 任务 T-001 尚未 done", denied.reason)

    def test_spec_identity_must_match_goal_even_while_clarifying(self) -> None:
        spec_path = self.state / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8").replace(
                "goal_id: G-001", "goal_id: G-002"
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("spec.md 的 goal_id 必须与 goal.md 一致", result.stdout)

    def test_terminated_status_must_equal_typed_exit_outcome(self) -> None:
        contract = wali_policy.load_contract(self.root)
        contract.update(
            {
                "status": "cancelled",
                "phase": "terminated",
                "allowed_effects": (
                    "read_workspace",
                    "update_handoff",
                    "transition_phase",
                ),
                "write_scope": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "exit_outcome": "aborted",
                "exit_reason": "策略无法安全继续",
                "exit_evidence": "安全检查失败",
                "exit_change_disposition": "preserve",
            }
        )

        reasons = wali_policy.validate_contract(contract)

        self.assertTrue(any("status 必须与 exit_outcome 一致" in reason for reason in reasons))

    def test_mutating_hook_rejects_a_nested_svn_working_copy_directory(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "svn status"},
        }
        stdout = io.StringIO()

        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch.object(
                wali_policy,
                "_svn_working_copy_root",
                return_value=self.root.parent.resolve(),
            ),
            redirect_stdout(stdout),
        ):
            result = wali_policy._run_hook(self.root)

        output = json.loads(stdout.getvalue())["hookSpecificOutput"]
        self.assertEqual(result, 0)
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("普通子目录", output["permissionDecisionReason"])

    def test_confirmed_goal_edit_cannot_rewrite_definition_and_digest_together(self) -> None:
        self.write_implementing_contract()
        goal_path = self.state / "goal.md"
        current = goal_path.read_text(encoding="utf-8")
        changed = current.replace("其他模块", "其他模块和数据迁移")
        digest_result = self.run_policy("digest")
        self.assertEqual(digest_result.returncode, 0)
        # The current digest command deliberately reports the on-disk definition;
        # simulate an attempted atomic rewrite by deriving the prospective hash.
        import importlib.util

        spec = importlib.util.spec_from_file_location("policy_under_test", MODULE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        prospective_contract = dict(module.parse_frontmatter(changed))
        prospective_digest = module._goal_definition_digest_from_text(
            changed,
            prospective_contract,
            (self.state / "spec.md").read_text(encoding="utf-8"),
        )
        changed = __import__("re").sub(
            r'goal_definition_digest: "[0-9a-f]+"',
            f'goal_definition_digest: "{prospective_digest}"',
            changed,
        )

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(goal_path),
                    "content": changed,
                },
            },
        )

        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("稳定定义不得", reason)

    def test_capabilities_require_explicit_allowlist_and_declarative_definition(self) -> None:
        self.add_capability("Skill", "wali-start")
        allowed = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"name": "wali-start"},
            },
        )
        self.assertEqual(allowed.stdout, "", allowed.stdout)

        for tool_name in ("Skill", "Agent"):
            with self.subTest(tool=tool_name):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": tool_name,
                        "tool_input": {"name": "any-future-capability"},
                    },
                )
                reason = json.loads(result.stdout)["hookSpecificOutput"][
                    "permissionDecisionReason"
                ]
                self.assertIn("allowed_capabilities", reason)

        denied_write = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(self.root / "context.md"),
                    "content": "generated by a capability",
                },
            },
        )
        reason = json.loads(denied_write.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("context.md", reason)

    def test_skill_dynamic_shell_is_denied_even_when_allowlisted(self) -> None:
        self.add_capability("Skill", "wali-start", unsafe="!`touch context.md`")
        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"name": "wali-start"},
            },
        )
        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("动态 shell", reason)

    def test_skill_fenced_shell_is_denied_even_when_allowlisted(self) -> None:
        self.add_capability(
            "Skill", "wali-start", unsafe="```!\ntouch context.md\n```"
        )
        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"name": "wali-start"},
            },
        )
        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("动态 shell", reason)

    def test_agent_preloaded_capabilities_are_denied_even_when_allowlisted(self) -> None:
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "  - Skill:wali-start", "  - Skill:wali-start\n  - Agent:developer"
            ),
            encoding="utf-8",
        )
        path = self.root / "claude" / "agents" / "developer.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        for unsafe_key in ("skills", "mcpServers", "memory"):
            with self.subTest(key=unsafe_key):
                path.write_text(
                    f"---\nname: developer\n{unsafe_key}: unsafe-preload\n---\n",
                    encoding="utf-8",
                )
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Agent",
                        "tool_input": {"name": "developer"},
                    },
                )
                reason = json.loads(result.stdout)["hookSpecificOutput"][
                    "permissionDecisionReason"
                ]
                self.assertIn("绕过权限", reason)

    def test_agent_effort_accepts_only_supported_frontmatter_levels(self) -> None:
        path = self.root / "claude" / "agents" / "developer.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                path.write_text(
                    "---\n"
                    "name: developer\n"
                    "description: Implements one scoped increment\n"
                    "tools: Read, Glob, Grep\n"
                    "model: sonnet\n"
                    f"effort: {effort}\n"
                    "---\n"
                    "# Identity\n",
                    encoding="utf-8",
                )
                self.assertTrue(
                    wali_policy._capability_is_declarative(path, "Agent")
                )

        for effort in ("auto", "ultracode", "extreme"):
            with self.subTest(effort=effort):
                path.write_text(
                    "---\n"
                    "name: developer\n"
                    "description: Implements one scoped increment\n"
                    "model: sonnet\n"
                    f"effort: {effort}\n"
                    "---\n",
                    encoding="utf-8",
                )
                self.assertFalse(
                    wali_policy._capability_is_declarative(path, "Agent")
                )

    def test_project_agents_define_role_appropriate_model_and_effort(self) -> None:
        expected = {
            "coordinator": ("opus", "high"),
            "architect": ("opus", "xhigh"),
            "reviewer": ("opus", "high"),
            "developer": ("sonnet", "high"),
            "tester": ("sonnet", "high"),
        }
        agents_root = MODULE_PATH.parents[1] / "agents"

        for name, (model, effort) in expected.items():
            with self.subTest(agent=name):
                path = agents_root / f"{name}.md"
                metadata = wali_policy.parse_frontmatter(
                    path.read_text(encoding="utf-8")
                )
                self.assertEqual(metadata.get("model"), model)
                self.assertEqual(metadata.get("effort"), effort)
                self.assertTrue(
                    wali_policy._capability_is_declarative(path, "Agent")
                )

        settings = json.loads(
            (MODULE_PATH.parents[1] / "settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(settings.get("model"), "opus")
        self.assertEqual(settings.get("effortLevel"), "high")

    def test_external_tools_are_denied_without_external_write_authority(self) -> None:
        for tool_name in ("WebSearch", "WebFetch", "mcp__tracker__create_issue"):
            with self.subTest(tool=tool_name):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": tool_name,
                        "tool_input": {},
                    },
                )
                reason = json.loads(result.stdout)["hookSpecificOutput"][
                    "permissionDecisionReason"
                ]
                self.assertIn("未授权工具", reason)

    def test_implementing_allows_only_declared_project_command(self) -> None:
        self.write_implementing_contract()

        allowed = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python3 -m unittest -v"},
            },
        )
        denied = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python3 release.py"},
            },
        )

        self.assertEqual(allowed.stdout, "", allowed.stdout)
        reason = json.loads(denied.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("未在 goal.md 声明", reason)

    def test_implementing_allows_exact_svn_schedule_and_sync_in_active_scope(self) -> None:
        self.write_implementing_contract()
        new_file = self.root / "src" / "feature" / "new.py"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("new\n", encoding="utf-8")
        (self.root / "src" / "feature" / "service.py").write_text(
            "existing\n", encoding="utf-8"
        )
        unrelated = self.root / "src" / "unrelated.py"
        unrelated.write_text("outside\n", encoding="utf-8")
        cases = {
            "svn add -- src/feature/new.py": True,
            "svn delete -- src/feature/new.py": True,
            "svn copy -- src/feature/new.py src/feature/copied.py": True,
            "svn move -- src/feature/new.py src/feature/moved.py": True,
            "svn update -- src/feature/service.py": True,
            "svn resolve --accept working -- src/feature/service.py": True,
            "svn resolve --accept theirs-full -- src/feature/service.py": False,
            "svn add -- src/unrelated.py": False,
            "svn add -- src/feature": False,
            "svn update -- src/unrelated.py": False,
            "svn update -- https://example.test/repo/file.py": False,
            f"svn add -- {new_file}": False,
        }
        for command, allowed in cases.items():
            with self.subTest(command=command):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                )
                if allowed:
                    self.assertEqual(result.stdout, "", result.stdout)
                else:
                    self.assertNotEqual(result.stdout, "")

    def test_declared_external_write_is_still_denied(self) -> None:
        self.write_implementing_contract()
        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8").replace(
            "| 策略测试 | `python3 -m unittest -v` | 退出码 0 |",
            "| 策略测试 | `curl -X POST https://example.test/deploy` | 发布成功 |",
        )
        goal_path.write_text(goal, encoding="utf-8")
        self.seal_goal()

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "curl -X POST https://example.test/deploy"},
            },
        )

        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("allow_external_writes=false", reason)

    def test_phase_profiles_reject_weakened_contracts(self) -> None:
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "allow_svn_commit: false", "allow_svn_commit: true"
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("allow_svn_commit 必须是 false", result.stdout)

    def test_duplicate_frontmatter_keys_are_rejected(self) -> None:
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "allow_svn_commit: false",
                "allow_svn_commit: false\nallow_svn_commit: true",
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("重复字段", result.stdout)

    def test_all_non_implementation_phase_profiles_are_executable_contracts(self) -> None:
        profiles = {
            "planning": {
                "status": "active",
                "active": "none",
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_goal",
                    "update_todo",
                    "update_issues",
                    "update_handoff",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/todo.md",
                    "docs/wali-0x3/issues.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
            "inspecting": {
                "status": "active",
                "active": "T-001",
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
            "accepting": {
                "status": "waiting_user",
                "active": "none",
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_goal",
                    "update_issues",
                    "update_handoff",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/issues.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
            "awaiting_direction": {
                "status": "waiting_user",
                "active": "none",
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_goal",
                    "update_handoff",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
            "blocked": {
                "status": "blocked",
                "active": "none",
                "effects": (
                    "read_workspace",
                    "ask_user",
                    "update_goal",
                    "update_handoff",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
            "delivering": {
                "status": "done",
                "active": "none",
                "effects": (
                    "read_workspace",
                    "update_handoff",
                    "transition_phase",
                ),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                    "@svn_commit",
                ),
                "flags": (False, False, False, True),
            },
            "closed": {
                "status": "done",
                "active": "none",
                "effects": ("read_workspace", "update_handoff", "transition_phase"),
                "scopes": (
                    "docs/wali-0x3/goal.md",
                    "docs/wali-0x3/handoff.md",
                ),
                "flags": (False, False, False, False),
            },
        }
        flag_names = (
            "allow_new_artifacts",
            "allow_implementation_changes",
            "allow_external_writes",
            "allow_svn_commit",
        )

        for phase, profile in profiles.items():
            with self.subTest(phase=phase):
                effects = "\n".join(
                    f"  - {effect}" for effect in profile["effects"]
                )
                scopes = "\n".join(
                    f"  - {scope}" for scope in profile["scopes"]
                )
                flags = "\n".join(
                    f"{name}: {str(value).lower()}"
                    for name, value in zip(flag_names, profile["flags"])
                )
                commit_evidence = (
                    'svn_commit_paths:\n  - src/feature/service.py\n'
                    'svn_commit_evidence: "用户授权提交 src/feature/service.py"\n'
                    'carried_changes:\n  - "src/feature/service.py::missing"\n'
                    if phase == "delivering"
                    else "carried_changes:\n"
                )
                waiting_for = (
                    "acceptance"
                    if phase == "accepting"
                    else "direction"
                    if phase == "awaiting_direction"
                    else "none"
                )
                waiting_detail = (
                    "请用户回测"
                    if phase == "accepting"
                    else "请用户选择方向"
                    if phase == "awaiting_direction"
                    else ""
                )
                blocked_reason = "外部依赖不可用" if phase == "blocked" else ""
                (self.state / "goal.md").write_text(
                    f"""---
wali_schema: 1
goal_id: G-001
status: {profile['status']}
phase: {phase}
active_task: {profile['active']}
goal_confirmation: confirmed
goal_confirmation_evidence: "用户确认 Goal G-001"
goal_definition_digest: ""
allowed_effects:
{effects}
allowed_capabilities:
write_scope:
{scopes}
preexisting_changes:
carry_epoch: {1 if phase == "delivering" else 0}
carried_history:
{flags}
{commit_evidence}
waiting_for: {waiting_for}
waiting_detail: "{waiting_detail}"
blocked_reason: "{blocked_reason}"
exit_outcome: {'completed' if phase in {'delivering', 'closed'} else 'none'}
exit_reason: "{'用户已验收' if phase in {'delivering', 'closed'} else ''}"
exit_evidence: "{'自动检查和用户验收已通过' if phase in {'delivering', 'closed'} else ''}"
exit_change_disposition: none
superseded_by: none
stop_intent: continue
---
# Goal

## 2. 已确认事实
- 已确认事实。
## 3. 高影响未知项
- 无。
## 4. 决策记录
- 已确认决策。
## 5. 目标与背景
- 交付用户可观察结果。
## 6. 范围与约束
- 范围明确且不扩大。
## 7. 验收标准
| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
                | AC-01 | automatic | 自动检查通过 | {'verified' if phase in {'delivering', 'closed'} else 'pending'} | {'test exit 0' if phase in {'delivering', 'closed'} else '待验证'} |
                | AC-02 | human | 用户回测通过 | {'verified' if phase in {'delivering', 'closed'} else 'pending'} | {'用户确认通过' if phase in {'delivering', 'closed'} else '待用户验收'} |
## 8. 检查方式
| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
| 单元测试 | `python3 -m unittest -v` | 退出码 0 |
""",
                    encoding="utf-8",
                )
                if phase == "inspecting":
                    (self.state / "todo.md").write_text(
                        """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 检查功能 | developer | required | review | 无 | `src/feature/**` | 检查通过 | 待验证 | reviewer |
""",
                        encoding="utf-8",
                    )
                    (self.state / "issues.md").write_text(
                        "# 问题清单\n", encoding="utf-8"
                    )
                elif phase in {"delivering", "closed"}:
                    (self.state / "todo.md").write_text(
                        """| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | AC-01 | 实现功能 | developer | required | done | 无 | `src/feature/**` | 测试通过 | test exit 0 | tester |
""",
                        encoding="utf-8",
                    )
                    (self.state / "issues.md").write_text(
                        """| ID | 来源 | 关联任务 | 关联 AC | 严重程度 | 状态 | 问题描述 | 修复负责人 | 复现/证据 | 验证者 | 验证结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
                        encoding="utf-8",
                    )
                self.seal_goal()

                result = self.run_policy("check")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_delivering_requires_explicit_svn_commit_paths(self) -> None:
        self.write_delivering_contract()
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8").replace(
                "svn_commit_paths:\n  - src/feature/service.py\n", ""
            ),
            encoding="utf-8",
        )

        result = self.run_policy("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("svn_commit_paths", result.stdout)

    def test_delivering_allows_only_exact_explicit_svn_commit_targets(self) -> None:
        self.write_delivering_contract()
        commands = {
            "svn commit -m 'approved' -- src/feature/service.py": "deny",
            "svn commit -m 'approved'": "deny",
            "svn commit -m 'approved' -- src/feature/service.py src/unrelated.py": "deny",
            "svn commit --targets targets.txt -m approved -- src/feature/service.py": "deny",
            "svn commit --editor-cmd touch -m approved -- src/feature/service.py": "deny",
            "svn commit --include-externals -m approved -- src/feature/service.py": "deny",
            f"svn commit -m approved -- {self.root / 'src/feature/service.py'}": "deny",
        }

        for command, expected_decision in commands.items():
            with self.subTest(command=command):
                result = self.run_policy(
                    "hook",
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                )
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], expected_decision)
                if command == "svn commit -m 'approved' -- src/feature/service.py":
                    self.assertIn("工作副本根", output["permissionDecisionReason"])
                elif expected_decision == "deny":
                    reason = output["permissionDecisionReason"]
                    self.assertIn("svn_commit_paths", reason)
                else:
                    self.assertIn("明确确认", output["permissionDecisionReason"])

    def test_delivering_rejects_a_noop_commit_and_requires_leaf_metadata(self) -> None:
        self.write_delivering_contract()
        (self.root / ".svn").mkdir()
        contract = wali_policy.load_contract(self.root)
        payload = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "svn commit -m approved -- src/feature/service.py"
            },
        }
        clean = '<?xml version="1.0"?><status><target path="."></target></status>'
        pending = """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>"""

        with (
            patch.object(wali_policy, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_policy, "_status_xml_from_svn", return_value=clean),
            patch.object(wali_policy, "_svn_node_kind", return_value="file"),
        ):
            noop = wali_policy.decide_tool(self.root, contract, payload)
        with (
            patch.object(wali_policy, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_policy, "_status_xml_from_svn", return_value=pending),
            patch.object(wali_policy, "_svn_node_kind", return_value="dir"),
        ):
            directory = wali_policy.decide_tool(self.root, contract, payload)
        with (
            patch.object(wali_policy, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_policy, "_status_xml_from_svn", return_value=pending),
            patch.object(wali_policy, "_svn_node_kind", return_value="file"),
        ):
            changed_leaf = wali_policy.decide_tool(self.root, contract, payload)

        self.assertFalse(noop.allowed)
        self.assertIn("空提交", noop.reason)
        self.assertFalse(directory.allowed)
        self.assertIn("leaf", directory.reason)
        self.assertTrue(changed_leaf.allowed, changed_leaf.reason)
        self.assertTrue(changed_leaf.requires_user_confirmation)

    def test_delivering_rejects_a_nested_or_unverified_working_copy(self) -> None:
        self.write_delivering_contract()
        contract = wali_policy.load_contract(self.root)
        payload = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "svn commit -m approved -- src/feature/service.py"
            },
        }

        with patch.object(wali_policy, "is_verified_working_copy_root", return_value=False):
            decision = wali_policy.decide_tool(self.root, contract, payload)

        self.assertFalse(decision.allowed)
        self.assertIn("工作副本根", decision.reason)

    def test_svn_root_verification_rejects_a_nested_working_copy_directory(self) -> None:
        (self.root / ".svn").mkdir()
        nested_result = subprocess.CompletedProcess(
            args=["svn", "info"],
            returncode=0,
            stdout=str(self.root.parent) + "\n",
            stderr="",
        )
        root_result = subprocess.CompletedProcess(
            args=["svn", "info"],
            returncode=0,
            stdout=str(self.root) + "\n",
            stderr="",
        )

        with patch.object(wali_svn.subprocess, "run", return_value=nested_result):
            nested = wali_svn.is_verified_working_copy_root(self.root)
        with patch.object(wali_svn.subprocess, "run", return_value=root_result):
            verified = wali_svn.is_verified_working_copy_root(self.root)

        self.assertFalse(nested)
        self.assertTrue(verified)

    def test_svn_discovery_fails_closed_when_cli_is_missing_in_a_nested_copy(
        self,
    ) -> None:
        (self.root / ".svn").mkdir()
        nested = self.root / "src" / "feature"
        nested.mkdir(parents=True)

        with patch.object(
            wali_svn.subprocess,
            "run",
            side_effect=FileNotFoundError("svn"),
        ):
            with self.assertRaisesRegex(
                wali_svn.SvnBoundaryError,
                "存在 .svn 但无法执行 svn info",
            ):
                wali_svn.discover_working_copy_root(nested)

    def test_live_svn_status_commands_reject_a_nested_working_copy_directory(
        self,
    ) -> None:
        stdout = io.StringIO()
        with patch.object(
            wali_policy,
            "_svn_working_copy_root",
            return_value=self.root.parent.resolve(),
        ), redirect_stdout(stdout):
            result = wali_policy._run_audit(self.root, None)

        self.assertEqual(result, 1)
        self.assertIn("工作副本根", stdout.getvalue())

    def test_pre_hook_denies_before_execution_when_snapshot_cannot_be_saved(self) -> None:
        (self.root / ".svn").mkdir()
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_use_id": "snapshot-failure",
            "tool_name": "Bash",
            "tool_input": {"command": "svn status"},
        }
        stdout = io.StringIO()

        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch.object(
                wali_policy,
                "_svn_working_copy_root",
                return_value=self.root.resolve(),
            ),
            patch.object(wali_policy, "is_verified_working_copy_root", return_value=True),
            patch.object(wali_policy, "_save_action_snapshot", return_value=False),
            redirect_stdout(stdout),
        ):
            result = wali_policy._run_hook(self.root)

        output = json.loads(stdout.getvalue())["hookSpecificOutput"]
        self.assertEqual(result, 0)
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("动作前快照", output["permissionDecisionReason"])

    def test_delivering_cannot_run_project_commands(self) -> None:
        self.write_delivering_contract()

        result = self.run_policy(
            "hook",
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python3 -m unittest -v"},
            },
        )

        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("delivering phase 禁止", output["permissionDecisionReason"])

    def test_delivering_audit_allows_only_authorized_commit_diffs(self) -> None:
        self.write_delivering_contract()
        authorized = self.root / "authorized.xml"
        authorized.write_text(
            """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="added" props="none" revision="-1"/></entry>
</target></status>
""",
            encoding="utf-8",
        )
        extra = self.root / "extra.xml"
        extra.write_text(
            authorized.read_text(encoding="utf-8").replace(
                "</target>",
                '<entry path="src/unrelated.py"><wc-status item="modified" props="none" revision="1"/></entry></target>',
            ),
            encoding="utf-8",
        )

        allowed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(authorized),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        denied = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(extra),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(allowed.returncode, 0, allowed.stdout)
        self.assertEqual(denied.returncode, 1)
        self.assertIn("src/unrelated.py", denied.stdout)

    def test_audit_rejects_out_of_scope_and_new_artifacts(self) -> None:
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<status>
  <target path=".">
    <entry path="docs/wali-0x3/goal.md"><wc-status item="modified" props="none" revision="1"/></entry>
    <entry path="src/app.py"><wc-status item="modified" props="none" revision="1"/></entry>
    <entry path="context.md"><wc-status item="unversioned" props="none"/></entry>
  </target>
</status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("src/app.py", result.stdout)
        self.assertIn("context.md", result.stdout)
        self.assertIn("新产物", result.stdout)

    def test_audit_excludes_native_ignored_local_artifacts(self) -> None:
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<status><target path=".">
  <entry path="target"><wc-status item="ignored" props="none"/></entry>
  <entry path="context.md"><wc-status item="unversioned" props="none"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("target", result.stdout)
        self.assertIn("context.md", result.stdout)

    def test_modified_native_ignore_property_remains_auditable(self) -> None:
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<status><target path=".">
  <entry path="target"><wc-status item="ignored" props="none"/></entry>
  <entry path="."><wc-status item="normal" props="modified"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("properties-modified", result.stdout)
        self.assertIn("target", result.stdout)

    def test_handoff_digest_excludes_native_ignored_local_artifact_contents(
        self,
    ) -> None:
        target = self.root / "target"
        target.mkdir()
        artifact = target / "cache.bin"
        artifact.write_bytes(b"first")
        status_xml = """<?xml version="1.0" encoding="UTF-8"?>
<status><target path=".">
  <entry path="target"><wc-status item="ignored" props="none"/></entry>
</target></status>
"""
        contract = wali_policy.load_contract(self.root)

        first = wali_policy.handoff_state_digest(
            self.root,
            contract,
            status_xml,
        )
        artifact.write_bytes(b"second")
        second = wali_policy.handoff_state_digest(
            self.root,
            contract,
            status_xml,
        )

        self.assertEqual(first, second)

    def test_audit_allows_implementing_changes_inside_active_task_scope(self) -> None:
        self.write_implementing_contract()
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<status><target path=".">
  <entry path="src/feature/service.py"><wc-status item="added" props="none" revision="-1"/></entry>
  <entry path="docs/wali-0x3/todo.md"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SVN 差异审计通过", result.stdout)

    def test_carried_changes_freeze_implementation_across_inspection(self) -> None:
        self.write_implementing_contract()
        service = self.root / "src" / "feature" / "service.py"
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("implemented\n", encoding="utf-8")
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="added" props="none" revision="-1"/></entry>
</target></status>
""",
            encoding="utf-8",
        )
        carry = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "carry",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(carry.returncode, 0, carry.stdout)
        carried_entry = next(
            line.strip()[2:].strip()
            for line in carry.stdout.splitlines()
            if line.strip().startswith("- ")
        )

        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8")
        replacements = {
            "phase: implementing": "phase: inspecting",
            "  - modify_implementation\n  - manage_svn_schedule\n  - sync_svn_working_copy\n  - run_project_commands": "  - run_checks",
            '  - "@active_task"': "",
            "carried_changes:\n": f"carried_changes:\n  - {carried_entry}\n",
            "carry_epoch: 0": "carry_epoch: 1",
            "allow_new_artifacts: true": "allow_new_artifacts: false",
            "allow_implementation_changes: true": "allow_implementation_changes: false",
        }
        for old, new in replacements.items():
            goal = goal.replace(old, new)
        goal_path.write_text(goal, encoding="utf-8")
        todo_path = self.state / "todo.md"
        todo_path.write_text(
            todo_path.read_text(encoding="utf-8").replace(" working ", " review "),
            encoding="utf-8",
        )

        unchanged = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        service.write_text("changed during review\n", encoding="utf-8")
        changed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(unchanged.returncode, 0, unchanged.stdout)
        self.assertEqual(changed.returncode, 1)
        self.assertIn("记录后发生变化", changed.stdout)

    def test_second_fix_cycle_creates_a_new_carry_epoch_and_keeps_history(self) -> None:
        self.write_implementing_contract()
        service = self.root / "src" / "feature" / "service.py"
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("first reviewed version\n", encoding="utf-8")
        first_fingerprint = wali_policy._path_fingerprint(
            self.root, "src/feature/service.py"
        )
        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8")
        goal = goal.replace("carry_epoch: 0", "carry_epoch: 1")
        goal = goal.replace(
            "carried_changes:\n",
            f'carried_changes:\n  - "src/feature/service.py::{first_fingerprint}"\n',
        )
        goal_path.write_text(goal, encoding="utf-8")
        contract = wali_policy.load_contract(self.root)

        service.write_text("fixed after review\n", encoding="utf-8")
        second_fingerprint = wali_policy._path_fingerprint(
            self.root, "src/feature/service.py"
        )
        status_xml = """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>"""
        prospective = goal.replace("carry_epoch: 1", "carry_epoch: 2").replace(
            first_fingerprint, second_fingerprint, 1
        )
        prospective = prospective.replace(
            "carried_history:\n",
            "carried_history:\n"
            f'  - "1::src/feature/service.py::{first_fingerprint}"\n',
        )
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(goal_path),
                "content": prospective,
            },
        }

        with patch.object(
            wali_policy, "_status_xml_from_svn", return_value=status_xml
        ):
            allowed = wali_policy.decide_tool(self.root, contract, payload)
        without_history = re.sub(
            r'carried_history:\n  - "1::[^\n]+"', "carried_history:", prospective
        )
        payload["tool_input"]["content"] = without_history
        with patch.object(
            wali_policy, "_status_xml_from_svn", return_value=status_xml
        ):
            denied = wali_policy.decide_tool(self.root, contract, payload)

        self.assertTrue(allowed.allowed, allowed.reason)
        self.assertFalse(denied.allowed)
        self.assertIn("history", denied.reason)

    def test_audit_preserves_unchanged_preexisting_user_change(self) -> None:
        protected = self.root / "src" / "user_work.py"
        protected.parent.mkdir(parents=True)
        protected.write_text("user change\n", encoding="utf-8")
        fingerprint = hashlib.sha256(b"file\0" + protected.read_bytes()).hexdigest()
        goal_path = self.state / "goal.md"
        goal = goal_path.read_text(encoding="utf-8").replace(
            "preexisting_changes:\n",
            f"""preexisting_changes:
  - "src/user_work.py::{fingerprint}"
""",
        )
        goal_path.write_text(goal, encoding="utf-8")
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0"?><status><target path=".">
<entry path="src/user_work.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        unchanged = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        protected.write_text("agent changed it\n", encoding="utf-8")
        changed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "audit",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(unchanged.returncode, 0, unchanged.stdout)
        self.assertEqual(changed.returncode, 1)
        self.assertIn("基线后发生变化", changed.stdout)

    def test_baseline_outputs_content_fingerprints_for_current_svn_changes(self) -> None:
        protected = self.root / "src" / "user_work.py"
        protected.parent.mkdir(parents=True)
        protected.write_text("user change\n", encoding="utf-8")
        expected = hashlib.sha256(b"file\0" + protected.read_bytes()).hexdigest()
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0"?><status><target path=".">
<entry path="src/user_work.py"><wc-status item="modified" props="none" revision="1"/></entry>
<entry path="docs/wali-0x3/goal.md"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "baseline",
                "--status-xml",
                str(status_xml),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"src/user_work.py::{expected}", result.stdout)
        self.assertNotIn("docs/wali-0x3/goal.md::", result.stdout)

    def test_post_hook_blocks_when_svn_audit_finds_generated_artifact(self) -> None:
        status_xml = self.root / "status.xml"
        status_xml.write_text(
            """<?xml version="1.0"?><status><target path=".">
<entry path="context.md"><wc-status item="unversioned" props="none"/></entry>
</target></status>
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "post-hook",
                "--status-xml",
                str(status_xml),
            ],
            input=json.dumps(
                {"hook_event_name": "PostToolUse", "tool_name": "Bash"}
            ),
            capture_output=True,
            check=False,
            text=True,
        )

        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("context.md", output["reason"])

    def test_post_hook_detects_bash_tampering_with_wali_state(self) -> None:
        (self.root / ".svn").mkdir()
        tool_id = "tool-123"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_use_id": tool_id,
            "tool_name": "Bash",
            "tool_input": {"command": "svn status"},
        }
        self.assertTrue(
            wali_policy._save_action_snapshot(
                self.root, payload, wali_policy.load_contract(self.root)
            )
        )
        (self.state / "handoff.md").write_text(
            "# tampered by declared command\n", encoding="utf-8"
        )
        clean_status = self.root / "clean.xml"
        clean_status.write_text(
            '<?xml version="1.0"?><status><target path="."></target></status>',
            encoding="utf-8",
        )
        post = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "post-hook",
                "--status-xml",
                str(clean_status),
            ],
            input=json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_use_id": tool_id,
                    "tool_name": "Bash",
                    "tool_input": {"command": "svn status"},
                }
            ),
            capture_output=True,
            check=False,
            text=True,
        )

        output = json.loads(post.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("handoff.md", output["reason"])

    def test_post_hook_detects_bash_tampering_with_delivery_receipt(self) -> None:
        (self.root / ".svn").mkdir()
        tool_id = "tool-receipt-tamper"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_use_id": tool_id,
            "tool_name": "Bash",
            "tool_input": {"command": "svn status"},
        }
        self.assertTrue(
            wali_policy._save_action_snapshot(
                self.root, payload, wali_policy.load_contract(self.root)
            )
        )
        receipt = self.root / ".svn" / "wali-policy" / "delivery-G-001.json"
        receipt.write_text("{}", encoding="utf-8")
        clean_status = self.root / "clean-receipt.xml"
        clean_status.write_text(
            '<?xml version="1.0"?><status><target path="."></target></status>',
            encoding="utf-8",
        )
        post = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--project-root",
                str(self.root),
                "post-hook",
                "--status-xml",
                str(clean_status),
            ],
            input=json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_use_id": tool_id,
                    "tool_name": "Bash",
                    "tool_input": {"command": "svn status"},
                }
            ),
            capture_output=True,
            check=False,
            text=True,
        )

        output = json.loads(post.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("delivery-G-001.json", output["reason"])

    def test_post_hook_records_a_receipt_after_a_clean_exact_commit(self) -> None:
        self.write_delivering_contract()
        clean_status = self.root / "clean.xml"
        clean_status.write_text(
            '<?xml version="1.0"?><status><target path="."></target></status>',
            encoding="utf-8",
        )
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_use_id": "commit-42",
            "tool_name": "Bash",
            "tool_input": {
                "command": "svn commit -m 'approved' -- src/feature/service.py"
            },
            "tool_response": {
                "stdout": "Sending src/feature/service.py\nCommitted revision 42.\n",
                "stderr": "",
                "interrupted": False,
            },
        }
        (self.root / ".svn").mkdir()
        pending = """<?xml version="1.0"?><status><target path=".">
<entry path="src/feature/service.py"><wc-status item="modified" props="none" revision="1"/></entry>
</target></status>"""
        contract = wali_policy.load_contract(self.root)
        with (
            patch.object(wali_policy, "_status_xml_from_svn", return_value=pending),
            patch.object(wali_policy, "_svn_node_kind", return_value="file"),
        ):
            wali_policy._save_action_snapshot(self.root, payload, contract)
        stdout = io.StringIO()
        with (
            patch.object(wali_policy, "is_verified_working_copy_root", return_value=True),
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch.object(
                wali_policy,
                "_svn_last_changed_revisions",
                return_value={"src/feature/service.py": "42"},
            ),
            redirect_stdout(stdout),
        ):
            result = wali_policy._run_post_hook(self.root, clean_status)

        receipt_path = (
            self.root / ".svn" / "wali-policy" / "delivery-G-001.json"
        )
        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["paths"], ["src/feature/service.py"])
        self.assertEqual(receipt["revisions"]["src/feature/service.py"], "42")

    def test_delivery_receipt_supports_an_exact_committed_deletion(self) -> None:
        self.write_delivering_contract()
        goal_path = self.state / "goal.md"
        goal_path.write_text(
            __import__("re").sub(
                r'carried_changes:\n  - "src/feature/service.py::[0-9a-f]+"',
                'carried_changes:\n  - "src/feature/service.py::missing"',
                goal_path.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )
        (self.root / "src" / "feature" / "service.py").unlink()
        contract = wali_policy.load_contract(self.root)
        clean = '<?xml version="1.0"?><status><target path="."></target></status>'
        precommit = {
            "src/feature/service.py": {
                "item": "deleted",
                "fingerprint": "missing",
                "kind": "file",
            }
        }

        record_reasons = wali_policy._record_delivery_receipt(
            self.root,
            contract,
            ("src/feature/service.py",),
            clean,
            precommit,
            "42",
        )
        completion_reasons = wali_policy.delivery_completion_reasons(
            self.root, contract, clean
        )

        self.assertEqual(record_reasons, [])
        self.assertEqual(completion_reasons, [])
        receipt = json.loads(
            (
                self.root / ".svn" / "wali-policy" / "delivery-G-001.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["commit_revision"], "42")
        self.assertEqual(receipt["revisions"]["src/feature/service.py"], "42")
        self.assertEqual(receipt["fingerprints"]["src/feature/service.py"], "missing")


if __name__ == "__main__":
    unittest.main()
