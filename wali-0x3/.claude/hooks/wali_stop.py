#!/usr/bin/env python3
"""Deterministic state-consistency gate for WALI goal transitions.

The hook does not claim that project tests passed. It verifies that Markdown
state and transition evidence are internally consistent. Actual project
commands and their evidence remain defined by the goal contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


STATE_DIR = Path("docs/wali-0x3")
REQUIRED_FILES = ("goal.md", "todo.md", "issues.md", "progress.md")
GOAL_STATUSES = {"draft", "active", "waiting_user", "blocked", "done"}
WAIT_REASONS = {"none", "direction", "acceptance"}
CRITERION_TYPES = {"automatic", "human"}
CRITERION_STATES = {"pending", "verified"}
TASK_NECESSITIES = {"required", "optional"}
TASK_STATES = {"pending", "working", "review", "blocked", "done"}
ISSUE_SEVERITIES = {"blocker", "high", "medium", "low"}
ISSUE_STATES = {"open", "fixing", "verify", "closed"}
INDEPENDENT_VERIFIERS = {"reviewer", "tester", "user"}
EMPTY_EVIDENCE = {
    "",
    "-",
    "—",
    "待补充",
    "待验证",
    "待用户验收",
    "待记录",
    "pending",
    "n/a",
}


def _without_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


class TableParseError(ValueError):
    """Raised when a WALI state table cannot be parsed without data loss."""


def _cells(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped and code-span pipes."""

    content = line.strip()
    if content.startswith("|"):
        content = content[1:]
    if content.endswith("|"):
        content = content[:-1]

    cells: list[str] = []
    current: list[str] = []
    code_delimiter = 0
    index = 0

    while index < len(content):
        character = content[index]
        if character == "\\" and index + 1 < len(content):
            next_character = content[index + 1]
            if next_character == "|":
                current.append("|")
            else:
                current.extend((character, next_character))
            index += 2
            continue

        if character == "`":
            run_end = index
            while run_end < len(content) and content[run_end] == "`":
                run_end += 1
            run_length = run_end - index
            if code_delimiter == 0:
                code_delimiter = run_length
            elif code_delimiter == run_length:
                code_delimiter = 0
            current.append(content[index:run_end])
            index = run_end
            continue

        if character == "|" and code_delimiter == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1

    cells.append("".join(current).strip())
    return cells


def _is_separator(cells: Iterable[str]) -> bool:
    cells = list(cells)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table_rows(text: str, source: str) -> list[dict[str, str]]:
    """Return Markdown table rows keyed by their header labels."""

    lines = _without_comments(text).splitlines()
    rows: list[dict[str, str]] = []
    index = 0

    while index + 1 < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue

        headers = _cells(lines[index])
        separator = _cells(lines[index + 1])
        if not _is_separator(separator) or len(headers) != len(separator):
            index += 1
            continue

        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            values = _cells(lines[index])
            if len(values) != len(headers):
                raise TableParseError(
                    f"{source}:{index + 1} 表格列数错误：期望 {len(headers)}，实际 {len(values)}"
                )
            rows.append(dict(zip(headers, values)))
            index += 1

    return rows


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _state(value: str) -> str:
    return value.strip().lower()


def _has_evidence(value: str) -> bool:
    return _state(value) not in EMPTY_EVIDENCE


def _completion_state(
    state_root: Path, goal_text: str, require_human: bool
) -> tuple[list[str], list[dict[str, str]]]:
    reasons: list[str] = []
    try:
        goal_rows = [
            row
            for row in _table_rows(goal_text, "goal.md")
            if row.get("ID", "").startswith("AC-")
        ]
        todo_rows = [
            row
            for row in _table_rows(_read(state_root / "todo.md"), "todo.md")
            if row.get("ID", "").startswith("T-")
        ]
        issue_rows = [
            row
            for row in _table_rows(_read(state_root / "issues.md"), "issues.md")
            if row.get("ID", "").startswith("I-")
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
        elif not _has_evidence(row.get("执行结果/证据", "")):
            reasons.append(f"required 任务 {task_id} 已标记 done，但缺少执行结果/证据")
        elif _state(row.get("独立验证者", "")) not in INDEPENDENT_VERIFIERS:
            reasons.append(
                f"required 任务 {task_id} 必须记录 reviewer、tester 或 user 作为独立验证者"
            )

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
            if not _has_evidence(row.get("验证结果", "")):
                reasons.append(f"已关闭问题 {issue_id} 缺少独立验证结果")

    return reasons, human_rows


def evaluate_project(project_root: Path) -> list[str]:
    """Return reasons that make the current WALI goal state inconsistent."""

    state_root = project_root / STATE_DIR
    goal_path = state_root / "goal.md"
    if not goal_path.exists():
        return []

    goal_text = _read(goal_path)
    metadata = _frontmatter(goal_text)
    goal_status = _state(metadata.get("status", ""))
    if goal_status == "draft":
        return []
    if goal_status not in GOAL_STATUSES:
        return ["goal status 必须是 draft、active、waiting_user、blocked 或 done"]

    reasons: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (state_root / name).exists()]
    if missing:
        reasons.append(f"缺少 WALI 状态文件：{', '.join(missing)}")
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
            return []

        completion_reasons, human_rows = _completion_state(
            state_root, goal_text, require_human=False
        )
        if completion_reasons:
            return completion_reasons
        if all(_state(row.get("状态", "")) == "verified" for row in human_rows):
            return ["用户验收已有证据；将 goal 状态改为 done 并更新 progress.md"]
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
            "自动门禁已满足但仍需用户验收；将 goal 状态改为 waiting_user、waiting_for 改为 acceptance，填写 waiting_detail 并请求用户回测"
        ]
    return ["全部验收已有证据；将 goal 状态改为 done 并更新 progress.md"]


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
        reason = "WALI 状态门禁尚未满足：\n- " + "\n- ".join(reasons)
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
