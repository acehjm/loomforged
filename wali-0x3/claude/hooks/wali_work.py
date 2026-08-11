#!/usr/bin/env python3
"""Load and validate wali-0x3's small, Markdown-backed work state.

The persistent interface is deliberately limited to ``goal.md`` and
``work.md``.  Dependency traversal is an internal implementation detail used
at planning, verification, and completion checkpoints; callers do not have to
maintain a separate graph artifact.
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


STATE_DIR = Path("docs/wali-0x3")
GOAL_FILE = STATE_DIR / "goal.md"
WORK_FILE = STATE_DIR / "work.md"
PHASES = {"define", "work", "verify", "done", "paused"}
WAIT_REASONS = {"none", "direction", "acceptance", "external"}
OUTCOMES = {"none", "completed", "cancelled", "aborted"}
TASK_STATES = {"pending", "working", "review", "blocked", "done"}
ACCEPTANCE_STATES = {"pending", "verified"}
ISSUE_STATES = {"open", "fixing", "verify", "closed"}
ISSUE_SEVERITIES = {"blocker", "high", "medium", "low"}
PLACEHOLDERS = {"", "-", "—", "none", "n/a", "pending", "待补充", "待验证", "待分配"}


class WorkStateError(RuntimeError):
    """Raised when the persistent state cannot be read or parsed."""


@dataclass(frozen=True)
class Goal:
    id: str
    confirmed: bool
    allow_external_writes: bool
    requirements: tuple["Requirement", ...]
    criteria: tuple["Criterion", ...]


@dataclass(frozen=True)
class Requirement:
    id: str
    description: str
    acceptance_ids: tuple[str, ...]


@dataclass(frozen=True)
class Criterion:
    id: str
    description: str
    method: str


@dataclass(frozen=True)
class Acceptance:
    id: str
    status: str
    evidence: str
    verifier: str


@dataclass(frozen=True)
class Task:
    id: str
    acceptance_ids: tuple[str, ...]
    title: str
    status: str
    dependencies: tuple[str, ...]
    scopes: tuple[str, ...]
    evidence: str
    owner: str
    verifier: str


@dataclass(frozen=True)
class Issue:
    id: str
    task_ids: tuple[str, ...]
    acceptance_ids: tuple[str, ...]
    severity: str
    status: str
    description: str
    evidence: str


@dataclass(frozen=True)
class WorkState:
    goal: Goal
    work_goal_id: str
    phase: str
    active_task: str
    stop_intent: str
    waiting_for: str
    outcome: str
    acceptances: tuple[Acceptance, ...]
    tasks: tuple[Task, ...]
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class PolicyTask:
    id: str
    status: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class PolicyContext:
    goal_id: str
    phase: str
    active_task: str
    allow_external_writes: bool
    task: PolicyTask | None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkStateError(f"无法读取 {path.name}：{error}") from error


def frontmatter(text: str, name: str) -> dict[str, str]:
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, flags=re.DOTALL)
    if match is None:
        raise WorkStateError(f"{name} 缺少 frontmatter")
    values: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in line:
            raise WorkStateError(f"{name} frontmatter 只允许顶层标量字段")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in values:
            raise WorkStateError(f"{name} frontmatter 字段重复：{key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def _boolean(value: str, *, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise WorkStateError(f"{field} 必须是 true 或 false")


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise WorkStateError("Markdown 表格行必须以 | 开始和结束")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    in_code = False
    for character in stripped[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "`":
            current.append(character)
            in_code = not in_code
        elif character == "|" and not in_code:
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def table(text: str, heading: str, name: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return []
    table_lines: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|"):
            table_lines.append(stripped)
        elif table_lines and stripped:
            break
    if not table_lines:
        return []
    if len(table_lines) < 2:
        raise WorkStateError(f"{name} 的 {heading} 表格缺少分隔行")
    headers = _split_markdown_row(table_lines[0])
    separator = _split_markdown_row(table_lines[1])
    if len(headers) != len(separator) or not _is_separator(separator):
        raise WorkStateError(f"{name} 的 {heading} 表格分隔行无效")
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_markdown_row(line)
        if len(cells) != len(headers):
            raise WorkStateError(f"{name} 的 {heading} 表格列数不一致")
        rows.append(dict(zip(headers, cells)))
    return rows


def _references(value: str, prefix: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(rf"\b{re.escape(prefix)}-\d+\b", value.upper())))


def _scopes(value: str) -> tuple[str, ...]:
    normalized = re.sub(r"<br\s*/?>", ",", value, flags=re.IGNORECASE)
    return tuple(
        dict.fromkeys(
            item.strip().strip("`").replace("\\", "/")
            for item in re.split(r"[,;；、]+", normalized)
            if item.strip().strip("`").lower() not in PLACEHOLDERS
        )
    )


def _has_evidence(value: str) -> bool:
    return value.strip().lower() not in PLACEHOLDERS


def parse_goal(text: str) -> Goal:
    metadata = frontmatter(text, "goal.md")
    runtime_fields = {"phase", "active_task", "stop_intent", "waiting_for", "outcome"}
    misplaced = sorted(runtime_fields & metadata.keys())
    if misplaced:
        raise WorkStateError(
            "goal.md 的运行字段必须移到 work.md：" + ", ".join(misplaced)
        )
    required = {
        "agent",
        "goal_id",
        "confirmed",
        "allow_external_writes",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise WorkStateError("goal.md 缺少字段：" + ", ".join(missing))
    if metadata["agent"] != "wali-0x3":
        raise WorkStateError("goal.md 的 agent 必须是 wali-0x3")
    requirements = tuple(
        Requirement(
            id=row.get("ID", "").strip(),
            description=row.get("Requirement", "").strip(),
            acceptance_ids=_references(row.get("Acceptance", ""), "AC"),
        )
        for row in table(text, "## Requirements", "goal.md")
    )
    criteria = tuple(
        Criterion(
            id=row.get("ID", "").strip(),
            description=row.get("Criterion", "").strip(),
            method=row.get("Method", "").strip(),
        )
        for row in table(text, "## Acceptance Criteria", "goal.md")
    )
    return Goal(
        id=metadata["goal_id"],
        confirmed=_boolean(metadata["confirmed"], field="confirmed"),
        allow_external_writes=_boolean(
            metadata["allow_external_writes"], field="allow_external_writes"
        ),
        requirements=requirements,
        criteria=criteria,
    )


def parse_work(
    text: str,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[Acceptance, ...],
    tuple[Task, ...],
    tuple[Issue, ...],
]:
    metadata = frontmatter(text, "work.md")
    required = {"goal_id", "phase", "active_task", "stop_intent", "waiting_for", "outcome"}
    missing = sorted(required - metadata.keys())
    if missing:
        raise WorkStateError("work.md 缺少字段：" + ", ".join(missing))
    acceptances = tuple(
        Acceptance(
            id=row.get("ID", "").strip(),
            status=row.get("Status", "").strip().lower(),
            evidence=row.get("Evidence", "").strip(),
            verifier=row.get("Verifier", "").strip().lower(),
        )
        for row in table(text, "## Acceptance", "work.md")
    )
    tasks = tuple(
        Task(
            id=row.get("ID", "").strip(),
            acceptance_ids=_references(row.get("Acceptance", ""), "AC"),
            title=row.get("Task", "").strip(),
            status=row.get("Status", "").strip().lower(),
            dependencies=_references(row.get("Depends On", ""), "T"),
            scopes=_scopes(row.get("Scope", "")),
            evidence=row.get("Evidence", "").strip(),
            owner=row.get("Owner", "").strip().lower(),
            verifier=row.get("Verifier", "").strip().lower(),
        )
        for row in table(text, "## Tasks", "work.md")
    )
    issues = tuple(
        Issue(
            id=row.get("ID", "").strip(),
            task_ids=_references(row.get("Task", ""), "T"),
            acceptance_ids=_references(row.get("Acceptance", ""), "AC"),
            severity=row.get("Severity", "").strip().lower(),
            status=row.get("Status", "").strip().lower(),
            description=row.get("Description", "").strip(),
            evidence=row.get("Evidence", "").strip(),
        )
        for row in table(text, "## Issues", "work.md")
    )
    return (
        metadata["goal_id"],
        metadata["phase"].lower(),
        metadata["active_task"],
        metadata["stop_intent"].lower(),
        metadata["waiting_for"].lower(),
        metadata["outcome"].lower(),
        acceptances,
        tasks,
        issues,
    )


def load_goal(project_root: Path, *, text: str | None = None) -> Goal:
    return parse_goal(text if text is not None else _read(project_root / GOAL_FILE))


def load_state(
    project_root: Path,
    *,
    goal_text: str | None = None,
    work_text: str | None = None,
) -> WorkState:
    goal = load_goal(project_root, text=goal_text)
    parsed = parse_work(work_text if work_text is not None else _read(project_root / WORK_FILE))
    return WorkState(goal, *parsed)


def load_policy_context(project_root: Path) -> PolicyContext:
    """Load only fields needed by high-frequency PreToolUse decisions."""

    goal_metadata = frontmatter(_read(project_root / GOAL_FILE), "goal.md")
    work_text = _read(project_root / WORK_FILE)
    work_metadata = frontmatter(work_text, "work.md")
    goal_required = {"agent", "goal_id", "confirmed", "allow_external_writes"}
    work_required = {"goal_id", "phase", "active_task"}
    missing_goal = sorted(goal_required - goal_metadata.keys())
    missing_work = sorted(work_required - work_metadata.keys())
    if missing_goal:
        raise WorkStateError("goal.md 缺少门禁字段：" + ", ".join(missing_goal))
    if missing_work:
        raise WorkStateError("work.md 缺少门禁字段：" + ", ".join(missing_work))
    if goal_metadata["agent"] != "wali-0x3":
        raise WorkStateError("goal.md 的 agent 必须是 wali-0x3")
    if goal_metadata["goal_id"] != work_metadata["goal_id"]:
        raise WorkStateError("work.md 的 goal_id 必须与 goal.md 一致")
    phase = work_metadata["phase"].lower()
    if phase not in PHASES:
        raise WorkStateError(f"未知 phase：{phase or '空'}")
    confirmed = _boolean(goal_metadata["confirmed"], field="confirmed")
    if phase != "define" and not confirmed:
        raise WorkStateError(f"{phase} phase 要求 confirmed=true")
    active_task = work_metadata["active_task"]
    task_rows = [
        row
        for row in table(work_text, "## Tasks", "work.md")
        if row.get("ID", "").strip() == active_task
    ]
    if len(task_rows) > 1:
        raise WorkStateError(f"active_task ID 重复：{active_task}")
    task = None
    if task_rows:
        row = task_rows[0]
        scopes = _scopes(row.get("Scope", ""))
        if not scopes or any(not _scope_prefix(scope) for scope in scopes):
            raise WorkStateError(f"{active_task} 缺少明确 Scope")
        task = PolicyTask(
            id=active_task,
            status=row.get("Status", "").strip().lower(),
            scopes=scopes,
        )
    return PolicyContext(
        goal_id=goal_metadata["goal_id"],
        phase=phase,
        active_task=active_task,
        allow_external_writes=_boolean(
            goal_metadata["allow_external_writes"],
            field="allow_external_writes",
        ),
        task=task,
    )


def _duplicates(values: list[str]) -> tuple[str, ...]:
    return tuple(value for value, count in Counter(values).items() if value and count > 1)


def _scope_prefix(scope: str) -> str:
    if (
        not scope
        or scope in {".", "*", "**", "**/*"}
        or scope.startswith(("/", "~"))
        or ".." in scope.split("/")
    ):
        return ""
    wildcard = min(
        (index for token in ("*", "?", "[") if (index := scope.find(token)) >= 0),
        default=len(scope),
    )
    prefix = scope[:wildcard]
    return (prefix.rsplit("/", 1)[0] if wildcard != len(scope) and "/" in prefix else prefix).rstrip("/")


def scopes_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return True
    for left_scope, right_scope in itertools.product(left, right):
        left_prefix = _scope_prefix(left_scope)
        right_prefix = _scope_prefix(right_scope)
        if not left_prefix or not right_prefix:
            return True
        if (
            left_prefix == right_prefix
            or left_prefix.startswith(right_prefix + "/")
            or right_prefix.startswith(left_prefix + "/")
        ):
            return True
    return False


def validate_state(state: WorkState) -> list[str]:
    reasons: list[str] = []
    goal = state.goal
    if state.phase not in PHASES:
        reasons.append(f"未知 phase：{state.phase or '空'}")
    if goal.id != "pending" and not re.fullmatch(r"G-\d+", goal.id):
        reasons.append(f"Goal ID 格式无效：{goal.id or '空'}")
    if goal.id == "pending" and state.phase != "define":
        reasons.append("只有 define phase 可以使用 pending Goal ID")
    if state.phase != "define" and not goal.confirmed:
        reasons.append(f"{state.phase} phase 要求 confirmed=true")
    if state.stop_intent not in {"continue", "handoff"}:
        reasons.append("stop_intent 必须是 continue 或 handoff")
    if state.waiting_for not in WAIT_REASONS:
        reasons.append("waiting_for 值无效")
    if state.outcome not in OUTCOMES:
        reasons.append("outcome 值无效")
    if state.phase == "paused" and state.waiting_for == "none":
        reasons.append("paused phase 必须记录 waiting_for")
    if state.phase != "paused" and state.waiting_for != "none":
        reasons.append("只有 paused phase 可以设置 waiting_for")
    if state.phase == "done" and state.outcome == "none":
        reasons.append("done phase 必须记录 outcome")
    if state.phase != "done" and state.outcome != "none":
        reasons.append("只有 done phase 可以记录最终 outcome")
    if state.work_goal_id != goal.id:
        reasons.append("work.md 的 goal_id 必须与 goal.md 一致")

    for label, identifiers in (
        ("Requirement", [item.id for item in goal.requirements]),
        ("Acceptance Criterion", [item.id for item in goal.criteria]),
        ("Acceptance", [item.id for item in state.acceptances]),
        ("Task", [item.id for item in state.tasks]),
        ("Issue", [item.id for item in state.issues]),
    ):
        for identifier in _duplicates(identifiers):
            reasons.append(f"{label} ID 重复：{identifier}")

    criterion_ids = {criterion.id for criterion in goal.criteria}
    task_ids = {task.id for task in state.tasks}
    acceptance_ids = {acceptance.id for acceptance in state.acceptances}
    if state.phase in {"work", "verify"} and state.active_task not in task_ids:
        reasons.append(f"{state.phase} phase 的 active_task 必须引用真实 Task")
    if state.phase in {"define", "done"} and state.active_task != "none":
        reasons.append(f"{state.phase} phase 的 active_task 必须是 none")
    if state.phase == "paused" and state.active_task != "none" and state.active_task not in task_ids:
        reasons.append("paused phase 的 active_task 必须是 none 或真实 Task")
    for requirement in goal.requirements:
        if not re.fullmatch(r"R-\d+", requirement.id):
            reasons.append(f"Requirement ID 格式无效：{requirement.id or '空'}")
        if not requirement.description:
            reasons.append(f"{requirement.id or 'Requirement'} 缺少描述")
        if not requirement.acceptance_ids:
            reasons.append(f"{requirement.id or 'Requirement'} 没有关联 Acceptance Criterion")
        for criterion_id in requirement.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(f"{requirement.id} 引用不存在的 {criterion_id}")
    covered = {
        criterion_id
        for requirement in goal.requirements
        for criterion_id in requirement.acceptance_ids
    }
    for criterion in goal.criteria:
        if not re.fullmatch(r"AC-\d+", criterion.id):
            reasons.append(f"Acceptance Criterion ID 格式无效：{criterion.id or '空'}")
        if not criterion.description or not criterion.method:
            reasons.append(f"{criterion.id or 'Acceptance Criterion'} 缺少描述或验证方法")
        if criterion.id not in covered:
            reasons.append(f"{criterion.id} 没有 Requirement 覆盖")
        if criterion.id not in acceptance_ids:
            reasons.append(f"work.md 缺少 {criterion.id} 的运行状态")
    for acceptance in state.acceptances:
        if acceptance.id not in criterion_ids:
            reasons.append(f"work.md 引用不存在的 {acceptance.id}")
        if acceptance.status not in ACCEPTANCE_STATES:
            reasons.append(f"{acceptance.id} 状态必须是 pending 或 verified")
        if acceptance.status == "verified" and (
            not _has_evidence(acceptance.evidence) or acceptance.verifier in PLACEHOLDERS
        ):
            reasons.append(f"{acceptance.id} 已 verified，但缺少证据或验证者")
    for task in state.tasks:
        if not re.fullmatch(r"T-\d+", task.id):
            reasons.append(f"Task ID 格式无效：{task.id or '空'}")
        if task.status not in TASK_STATES:
            reasons.append(f"{task.id} 状态无效")
        if not task.acceptance_ids:
            reasons.append(f"{task.id} 没有关联 Acceptance Criterion")
        for criterion_id in task.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(f"{task.id} 引用不存在的 {criterion_id}")
        for dependency_id in task.dependencies:
            if dependency_id not in task_ids:
                reasons.append(f"{task.id} 依赖不存在的 {dependency_id}")
        if not task.scopes or any(not _scope_prefix(scope) for scope in task.scopes):
            reasons.append(f"{task.id} 缺少明确 Scope")
        if not task.title or task.owner in PLACEHOLDERS:
            reasons.append(f"{task.id} 缺少任务描述或 Owner")
        if task.status == "done":
            if not _has_evidence(task.evidence):
                reasons.append(f"{task.id} 已 done，但缺少 Evidence")
            if task.verifier in PLACEHOLDERS or task.verifier == task.owner:
                reasons.append(f"{task.id} 已 done，但缺少独立 Verifier")
    for issue in state.issues:
        if not re.fullmatch(r"I-\d+", issue.id):
            reasons.append(f"Issue ID 格式无效：{issue.id or '空'}")
        if issue.status not in ISSUE_STATES or issue.severity not in ISSUE_SEVERITIES:
            reasons.append(f"{issue.id} 的状态或严重程度无效")
        if not issue.task_ids and not issue.acceptance_ids:
            reasons.append(f"{issue.id} 必须关联 Task 或 Acceptance Criterion")
        for task_id in issue.task_ids:
            if task_id not in task_ids:
                reasons.append(f"{issue.id} 引用不存在的 {task_id}")
        for criterion_id in issue.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(f"{issue.id} 引用不存在的 {criterion_id}")
        if issue.status == "closed" and not _has_evidence(issue.evidence):
            reasons.append(f"{issue.id} 已 closed，但缺少 Evidence")

    dependencies = {task.id: task.dependencies for task in state.tasks}
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(task_id: str) -> tuple[str, ...] | None:
        if task_id in visiting:
            start = visiting.index(task_id)
            return tuple(visiting[start:] + [task_id])
        if task_id in visited:
            return None
        visiting.append(task_id)
        for dependency_id in dependencies.get(task_id, ()):
            cycle = visit(dependency_id)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(task_id)
        return None

    for task in state.tasks:
        cycle = visit(task.id)
        if cycle:
            reasons.append("Task 依赖存在环：" + " → ".join(cycle))
            break
    working = [task for task in state.tasks if task.status == "working"]
    if len(working) > 1:
        reasons.append("默认运行时只允许一个 working Task")
    if working and working[0].id != state.active_task:
        reasons.append("working Task 必须与 active_task 一致")
    for left, right in itertools.combinations(working, 2):
        if scopes_overlap(left.scopes, right.scopes):
            reasons.append(f"working Task {left.id} 与 {right.id} 的 Scope 重叠")
    return list(dict.fromkeys(reasons))


def frontier(state: WorkState) -> tuple[Task, ...]:
    tasks = {task.id: task for task in state.tasks}
    blockers = [
        issue
        for issue in state.issues
        if issue.severity == "blocker" and issue.status != "closed"
    ]
    runnable = []
    for task in state.tasks:
        blocked = any(
            task.id in issue.task_ids
            or bool(set(task.acceptance_ids) & set(issue.acceptance_ids))
            for issue in blockers
        )
        if (
            task.status == "pending"
            and not blocked
            and all(tasks.get(item) and tasks[item].status == "done" for item in task.dependencies)
        ):
            runnable.append(task)
    return tuple(sorted(runnable, key=lambda item: item.id))


def safe_parallel_pairs(state: WorkState) -> tuple[tuple[Task, Task], ...]:
    return tuple(
        (left, right)
        for left, right in itertools.combinations(frontier(state), 2)
        if not scopes_overlap(left.scopes, right.scopes)
    )


def checkpoint_reasons(state: WorkState, checkpoint: str) -> list[str]:
    reasons = validate_state(state)
    if checkpoint == "work":
        if not state.goal.confirmed:
            reasons.append("进入 work 前必须确认 Goal")
        if not state.tasks:
            reasons.append("进入 work 前至少需要一个 Task")
    elif checkpoint == "verify":
        active = next(
            (task for task in state.tasks if task.id == state.active_task),
            None,
        )
        if active is None or active.status != "review":
            reasons.append("进入 verify 前 active_task 必须处于 review")
        elif not _has_evidence(active.evidence):
            reasons.append("进入 verify 前 active_task 必须记录实现证据")
    elif checkpoint == "done":
        for task in state.tasks:
            if task.status != "done":
                reasons.append(f"{task.id} 尚未 done")
        for acceptance in state.acceptances:
            if acceptance.status != "verified":
                reasons.append(f"{acceptance.id} 尚未 verified")
        for issue in state.issues:
            if issue.severity == "blocker" and issue.status != "closed":
                reasons.append(f"存在未关闭 blocker：{issue.id}")
    else:
        reasons.append(f"未知 checkpoint：{checkpoint}")
    return list(dict.fromkeys(reasons))


def _run_check(project_root: Path, checkpoint: str | None) -> int:
    try:
        state = load_state(project_root)
        reasons = checkpoint_reasons(state, checkpoint) if checkpoint else validate_state(state)
    except WorkStateError as error:
        reasons = [str(error)]
    if reasons:
        print("WALI 状态检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    print("WALI 状态检查通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--checkpoint", choices=("work", "verify", "done"))
    subparsers.add_parser("frontier")
    subparsers.add_parser("parallel")
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.command == "check":
        return _run_check(root, args.checkpoint)
    try:
        state = load_state(root)
        reasons = validate_state(state)
    except WorkStateError as error:
        print(f"WALI 状态读取失败：{error}")
        return 1
    if reasons:
        for reason in reasons:
            print(reason)
        return 1
    if args.command == "frontier":
        for task in frontier(state):
            print(f"{task.id}\t{task.title}\t{', '.join(task.scopes)}")
        return 0
    for left, right in safe_parallel_pairs(state):
        print(f"{left.id}\t{right.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
