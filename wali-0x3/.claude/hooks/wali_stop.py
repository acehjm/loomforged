#!/usr/bin/env python3
"""Deterministic state-consistency gate for active WALI goals.

The hook does not claim that project tests passed. It verifies that an active
goal's Markdown state is internally complete enough for Claude to stop. Actual
project commands and their evidence remain defined by the goal contract.
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
VERIFIED_STATES = {"verified", "已验证", "pass", "passed"}
DONE_STATES = {"done", "完成"}
CLOSED_STATES = {"closed", "已关闭"}
AUTOMATIC_TYPES = {"automatic", "auto", "自动"}
HUMAN_TYPES = {"human", "人工", "用户"}
REQUIRED_VALUES = {"required", "必要", "true", "yes"}
BLOCKER_VALUES = {"blocker", "阻断"}
EMPTY_EVIDENCE = {"", "-", "—", "待补充", "待验证", "pending", "n/a"}


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


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: Iterable[str]) -> bool:
    cells = list(cells)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table_rows(text: str) -> list[dict[str, str]]:
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
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
            index += 1

    return rows


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _state(value: str) -> str:
    return value.strip().lower()


def _has_evidence(value: str) -> bool:
    return _state(value) not in EMPTY_EVIDENCE


def evaluate_project(project_root: Path) -> list[str]:
    """Return blocking reasons for an active goal; return [] when not active."""

    state_root = project_root / STATE_DIR
    goal_path = state_root / "goal.md"
    if not goal_path.exists():
        return []

    goal_text = _read(goal_path)
    goal_status = _state(_frontmatter(goal_text).get("status", ""))
    if goal_status != "active":
        return []

    reasons: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (state_root / name).exists()]
    if missing:
        reasons.append(f"缺少 WALI 状态文件：{', '.join(missing)}")
        return reasons

    goal_rows = [row for row in _table_rows(goal_text) if row.get("ID", "").startswith("AC-")]
    automatic_rows = [
        row for row in goal_rows if _state(row.get("类型", "")) in AUTOMATIC_TYPES
    ]
    human_rows = [row for row in goal_rows if _state(row.get("类型", "")) in HUMAN_TYPES]

    if not automatic_rows:
        reasons.append("active 目标至少需要一项 automatic 验收条件")
    if not human_rows:
        reasons.append("目标至少需要一项 human 验收条件以保留用户最终验收权")

    for row in automatic_rows:
        criterion_id = row.get("ID", "未知 AC")
        if _state(row.get("状态", "")) not in VERIFIED_STATES:
            reasons.append(f"{criterion_id} 尚未 verified")
        elif not _has_evidence(row.get("证据", "")):
            reasons.append(f"{criterion_id} 已标记 verified，但缺少证据")

    todo_rows = [
        row
        for row in _table_rows(_read(state_root / "todo.md"))
        if row.get("ID", "").startswith("T-")
    ]
    required_rows = [
        row for row in todo_rows if _state(row.get("必要性", "")) in REQUIRED_VALUES
    ]
    if not required_rows:
        reasons.append("active 目标至少需要一项 required 任务")

    for row in required_rows:
        task_id = row.get("ID", "未知任务")
        if _state(row.get("状态", "")) not in DONE_STATES:
            reasons.append(f"required 任务 {task_id} 尚未 done")
        elif not _has_evidence(row.get("执行结果/证据", "")):
            reasons.append(f"required 任务 {task_id} 已标记 done，但缺少执行结果/证据")

    issue_rows = [
        row
        for row in _table_rows(_read(state_root / "issues.md"))
        if row.get("ID", "").startswith("I-")
    ]
    for row in issue_rows:
        if (
            _state(row.get("严重程度", "")) in BLOCKER_VALUES
            and _state(row.get("状态", "")) not in CLOSED_STATES
        ):
            reasons.append(f"存在未关闭的 blocker：{row.get('ID', '未知问题')}")

    if reasons:
        return reasons

    pending_human = [
        row for row in human_rows if _state(row.get("状态", "")) not in VERIFIED_STATES
    ]
    missing_human_evidence = [
        row
        for row in human_rows
        if _state(row.get("状态", "")) in VERIFIED_STATES
        and not _has_evidence(row.get("证据", ""))
    ]
    for row in missing_human_evidence:
        reasons.append(f"{row.get('ID', '未知 human AC')} 已标记 verified，但缺少用户验收证据")

    if reasons:
        return reasons
    if pending_human:
        return [
            "自动门禁已满足，但仍需用户验收；将 goal 状态改为 waiting_user，更新 progress.md，并请求用户回测"
        ]

    return [
        "自动条件和用户验收均有证据；将 goal 状态改为 done，更新 progress.md，并给出逐项验收摘要"
    ]


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
        reason = "WALI active 目标尚未达到可停止状态：\n- " + "\n- ".join(reasons)
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

    print("WALI 检查通过：当前没有 active 目标，或状态门禁无需阻止停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
