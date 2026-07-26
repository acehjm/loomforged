#!/usr/bin/env python3
"""Deterministic graph and state checks for WALI goal transitions.

The hook does not claim that project tests passed. It verifies that Markdown
state and transition evidence are internally consistent. Actual project
commands and their evidence remain defined by the goal contract.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from wali_graph import (
    CRITERION_COLUMNS,
    GraphLoadError,
    ISSUE_COLUMNS,
    TASK_COLUMNS,
    TableParseError,
    frontmatter as _frontmatter,
    has_evidence as _has_evidence,
    load_graph,
    normalized as _state,
    read_text as _read,
    table_rows as _table_rows,
    validate_graph,
)
from wali_policy import (
    PolicyError,
    _status_xml_from_svn,
    _svn_working_copy_root,
    _verified_svn_root,
    audit_changes,
    delivery_completion_reasons,
    handoff_state_digest,
    load_contract,
    validate_project_contract,
)
from wali_supervision import recovery_handoff_reasons


STATE_DIR = Path("docs/wali-0x3")
REQUIRED_FILES = ("goal.md", "spec.md", "todo.md", "issues.md", "handoff.md")
GOAL_STATUSES = {
    "draft",
    "active",
    "waiting_user",
    "blocked",
    "done",
    "cancelled",
    "superseded",
    "aborted",
}
WAIT_REASONS = {"none", "direction", "acceptance"}
CRITERION_TYPES = {"automatic", "human"}
CRITERION_STATES = {"pending", "verified"}
TASK_NECESSITIES = {"required", "optional"}
TASK_STATES = {"pending", "working", "review", "blocked", "done"}
ISSUE_SEVERITIES = {"blocker", "high", "medium", "low"}
ISSUE_STATES = {"open", "fixing", "verify", "closed"}
INDEPENDENT_VERIFIERS = {"reviewer", "tester", "user"}


def _completion_state(
    state_root: Path, goal_text: str, require_human: bool
) -> tuple[list[str], list[dict[str, str]]]:
    reasons: list[str] = []
    try:
        goal_rows = [
            row
            for row in _table_rows(goal_text, "goal.md")
            if CRITERION_COLUMNS.issubset(row)
        ]
        todo_rows = [
            row
            for row in _table_rows(_read(state_root / "todo.md"), "todo.md")
            if TASK_COLUMNS.issubset(row)
        ]
        issue_rows = [
            row
            for row in _table_rows(_read(state_root / "issues.md"), "issues.md")
            if ISSUE_COLUMNS.issubset(row)
        ]
    except TableParseError as error:
        return [str(error)], []

    for row in goal_rows:
        criterion_id = row.get("ID", "未知 AC")
        criterion_type = _state(row.get("类型", ""))
        criterion_status = _state(row.get("状态", ""))
        if criterion_type not in CRITERION_TYPES:
            reasons.append(f"{criterion_id} 类型必须是 automatic 或 human")
        if criterion_status not in CRITERION_STATES:
            reasons.append(f"{criterion_id} 状态必须是 pending 或 verified")

    automatic_rows = [row for row in goal_rows if _state(row.get("类型", "")) == "automatic"]
    human_rows = [row for row in goal_rows if _state(row.get("类型", "")) == "human"]
    if not automatic_rows:
        reasons.append("目标至少需要一项 automatic 验收条件")
    if not human_rows:
        reasons.append("目标至少需要一项 human 验收条件以保留用户最终验收权")

    for row in automatic_rows:
        criterion_id = row.get("ID", "未知 AC")
        if _state(row.get("状态", "")) != "verified":
            reasons.append(f"{criterion_id} 尚未 verified")
        elif not _has_evidence(row.get("证据", "")):
            reasons.append(f"{criterion_id} 已标记 verified，但缺少证据")

    if require_human:
        for row in human_rows:
            criterion_id = row.get("ID", "未知 human AC")
            if _state(row.get("状态", "")) != "verified":
                reasons.append(f"{criterion_id} 尚未获得用户验收")
            elif not _has_evidence(row.get("证据", "")):
                reasons.append(f"{criterion_id} 已标记 verified，但缺少用户验收证据")

    for row in todo_rows:
        task_id = row.get("ID", "未知任务")
        necessity = _state(row.get("必要性", ""))
        task_status = _state(row.get("状态", ""))
        if necessity not in TASK_NECESSITIES:
            reasons.append(f"{task_id} 必要性必须是 required 或 optional")
        if task_status not in TASK_STATES:
            reasons.append(f"{task_id} 状态不是允许的任务状态")

    required_rows = [row for row in todo_rows if _state(row.get("必要性", "")) == "required"]
    if not required_rows:
        reasons.append("目标至少需要一项 required 任务")
    for row in required_rows:
        task_id = row.get("ID", "未知任务")
        if _state(row.get("状态", "")) != "done":
            reasons.append(f"required 任务 {task_id} 尚未 done")

    for row in todo_rows:
        task_id = row.get("ID", "未知任务")
        if _state(row.get("状态", "")) != "done":
            continue
        if not _has_evidence(row.get("执行结果/证据", "")):
            reasons.append(f"任务 {task_id} 已标记 done，但缺少执行结果/证据")
        elif _state(row.get("独立验证者", "")) not in INDEPENDENT_VERIFIERS:
            reasons.append(
                f"任务 {task_id} 必须记录 reviewer、tester 或 user 作为独立验证者"
            )
        elif _state(row.get("独立验证者", "")) == _state(row.get("负责人", "")):
            reasons.append(f"任务 {task_id} 的独立验证者必须与负责人不同")

    for row in issue_rows:
        issue_id = row.get("ID", "未知问题")
        severity = _state(row.get("严重程度", ""))
        issue_status = _state(row.get("状态", ""))
        if severity not in ISSUE_SEVERITIES:
            reasons.append(f"{issue_id} 严重程度不是允许值")
        if issue_status not in ISSUE_STATES:
            reasons.append(f"{issue_id} 状态不是允许的问题状态")
        if severity == "blocker" and issue_status != "closed":
            reasons.append(f"存在未关闭的 blocker：{issue_id}")
        if issue_status == "closed":
            if _state(row.get("验证者", "")) not in INDEPENDENT_VERIFIERS:
                reasons.append(
                    f"已关闭问题 {issue_id} 必须记录 reviewer、tester 或 user 作为验证者"
                )
            elif _state(row.get("验证者", "")) == _state(row.get("修复负责人", "")):
                reasons.append(f"已关闭问题 {issue_id} 的验证者必须与修复负责人不同")
            if not _has_evidence(row.get("验证结果", "")):
                reasons.append(f"已关闭问题 {issue_id} 缺少独立验证结果")

    return reasons, human_rows


def _work_graph_reasons(project_root: Path) -> list[str]:
    try:
        return validate_graph(load_graph(project_root))
    except GraphLoadError as error:
        return [str(error)]


def _handoff_reasons(
    project_root: Path,
    contract: dict[str, object],
    status_xml: str | None = None,
) -> list[str]:
    handoff_path = project_root / STATE_DIR / "handoff.md"
    if not handoff_path.exists():
        return ["停止前必须更新 handoff.md，确保任务可恢复"]
    metadata = _frontmatter(_read(handoff_path))
    reasons: list[str] = []
    for key in ("goal_id", "phase", "active_task", "goal_confirmation"):
        expected = str(contract.get(key, ""))
        if metadata.get(key, "") != expected:
            reasons.append(f"handoff.md 的 {key} 必须与 goal.md 一致")
    updated = metadata.get("updated", "")
    if not updated or "YYYY" in updated:
        reasons.append("handoff.md 必须记录真实 updated 时间")
    recorded_digest = metadata.get("state_digest", "")
    try:
        expected_digest = handoff_state_digest(project_root, contract, status_xml)
    except (OSError, PolicyError) as error:
        reasons.append(f"无法校验 handoff.md 状态摘要：{error}")
    else:
        if not recorded_digest:
            reasons.append("handoff.md 必须记录 state_digest")
        elif recorded_digest != expected_digest:
            reasons.append("handoff.md 已过期；state_digest 与当前 Goal、工作图或工作副本不一致")
    reasons.extend(
        recovery_handoff_reasons(
            project_root,
            svn_root_already_verified=status_xml is not None,
        )
    )
    return reasons


def evaluate_project(project_root: Path) -> list[str]:
    """Return reasons that make the current WALI goal state inconsistent."""

    state_root = project_root / STATE_DIR
    goal_path = state_root / "goal.md"
    if not goal_path.exists():
        return []

    goal_text = _read(goal_path)
    metadata = _frontmatter(goal_text)
    goal_status = _state(metadata.get("status", ""))

    if not metadata.get("phase"):
        return ["goal.md 缺少 phase 阶段契约；请使用恢复通道重建 clarifying 契约"]

    policy_reasons: list[str] = []
    contract: dict[str, object] | None = None
    live_status_xml: str | None = None
    try:
        contract = load_contract(project_root)
    except PolicyError as error:
        policy_reasons.append(str(error))
    else:
        try:
            svn_root = _svn_working_copy_root(project_root)
            if svn_root is not None and svn_root != project_root.resolve():
                policy_reasons.append(
                    "WALI Stop 必须从 SVN 工作副本根执行，不允许在普通子目录停止"
                )
            elif svn_root is not None:
                live_status_xml = _status_xml_from_svn(project_root)
                policy_reasons.extend(audit_changes(project_root, contract, live_status_xml))
        except PolicyError as error:
            policy_reasons.append(f"SVN 差异审计失败：{error}")
        policy_reasons.extend(
            validate_project_contract(
                project_root, contract, status_xml=live_status_xml
            )
        )
    if policy_reasons:
        return policy_reasons

    missing = [name for name in REQUIRED_FILES if not (state_root / name).exists()]
    if missing:
        return [f"缺少 WALI 状态文件：{', '.join(missing)}"]

    if goal_status == "draft":
        if contract is not None:
            return _handoff_reasons(project_root, contract, live_status_xml)
        return []
    if goal_status not in GOAL_STATUSES:
        return [
            "goal status 必须是 draft、active、waiting_user、blocked、done、cancelled、superseded 或 aborted"
        ]

    reasons: list[str] = []
    if contract is not None:
        reasons.extend(_handoff_reasons(project_root, contract, live_status_xml))

    if goal_status in {"cancelled", "superseded", "aborted"}:
        if contract is None or str(contract.get("phase", "")) != "terminated":
            reasons.append(f"{goal_status} 目标必须处于 terminated phase")
        return reasons

    reasons.extend(_work_graph_reasons(project_root))

    if contract is not None and str(contract.get("phase", "")) == "delivering":
        if not _verified_svn_root(project_root):
            reasons.append("delivering 必须从可验证且可写的 SVN 工作副本根完成")
        elif live_status_xml is None:
            reasons.append("delivering 必须在可审计的 SVN 工作副本中完成")
        else:
            reasons.extend(
                delivery_completion_reasons(project_root, contract, live_status_xml)
            )

    if contract is not None and str(contract.get("stop_intent", "")) == "handoff":
        return reasons

    if goal_status == "blocked":
        if not _has_evidence(metadata.get("blocked_reason", "")):
            reasons.append("blocked 目标必须在 blocked_reason 记录真实阻断")
        return reasons

    waiting_for = _state(metadata.get("waiting_for", "none"))
    waiting_detail = metadata.get("waiting_detail", "")
    if goal_status == "waiting_user":
        if waiting_for not in {"direction", "acceptance"}:
            reasons.append("waiting_user 目标的 waiting_for 必须是 direction 或 acceptance")
            return reasons
        if not _has_evidence(waiting_detail):
            reasons.append("waiting_user 目标必须在 waiting_detail 记录问题或回测要求")
            return reasons
        if waiting_for == "direction":
            return reasons

        completion_reasons, human_rows = _completion_state(
            state_root, goal_text, require_human=False
        )
        reasons.extend(completion_reasons)
        if reasons:
            return reasons
        if all(_state(row.get("状态", "")) == "verified" for row in human_rows):
            return ["用户验收已有证据；将 goal 状态改为 done 并更新 handoff.md"]
        return []

    if waiting_for != "none":
        reasons.append(f"{goal_status} 目标的 waiting_for 必须是 none")

    completion_reasons, human_rows = _completion_state(
        state_root, goal_text, require_human=goal_status == "done"
    )
    reasons.extend(completion_reasons)
    if reasons or goal_status == "done":
        return reasons

    pending_human = [row for row in human_rows if _state(row.get("状态", "")) != "verified"]
    if pending_human:
        return [
            "自动检查已通过但仍需用户验收；将 goal 状态改为 waiting_user、waiting_for 改为 acceptance，填写 waiting_detail 并请求用户回测"
        ]
    return ["全部验收已有证据；将 goal 状态改为 done 并更新 handoff.md"]


def _run_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        print(json.dumps({"systemMessage": f"WALI Stop Hook 输入无效：{error}"}, ensure_ascii=False))
        return 0

    if payload.get("stop_hook_active"):
        return 0
    if payload.get("background_tasks") or payload.get("session_crons"):
        return 0

    reasons = evaluate_project(project_root)
    if reasons:
        reason = "WALI 状态检查未通过：\n- " + "\n- ".join(reasons)
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", action="store_true", help="read Claude Stop payload from stdin")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if args.hook:
        return _run_hook(project_root)

    reasons = evaluate_project(project_root)
    if reasons:
        print("WALI 检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1

    print("WALI 检查通过：当前状态允许停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
