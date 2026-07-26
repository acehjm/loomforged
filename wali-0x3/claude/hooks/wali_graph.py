#!/usr/bin/env python3
"""Derive, validate, and inspect the WALI work graph from Markdown state."""

from __future__ import annotations

import argparse
import itertools
import posixpath
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

STATE_DIR = Path("docs/wali-0x3")
STATE_FILES = ("goal.md", "spec.md", "todo.md", "issues.md", "handoff.md")
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
AMBIGUOUS_SCOPES = {
    "待定",
    "待确定",
    "待记录",
    "待补充",
    "另行确认",
    "unknown",
    "tbd",
    "n/a",
    "none",
    "-",
    "—",
}
EXPLICIT_SCOPE_PATTERN = re.compile(r"[A-Za-z0-9._@+!*?\[\]{}()/,-]+")
CRITERION_COLUMNS = {"ID", "类型", "验收条件", "状态", "证据"}
REQUIREMENT_COLUMNS = {"ID", "类型", "规范要求", "来源", "关联 AC"}
ORACLE_COLUMNS = {"AC ID", "判定规则", "验证方法"}
TASK_COLUMNS = {
    "ID",
    "关联 AC",
    "任务",
    "负责人",
    "必要性",
    "状态",
    "依赖",
    "允许修改范围",
    "任务验收条件",
    "执行结果/证据",
    "独立验证者",
}
OPTIONAL_TASK_SKILL_COLUMN = "所用 Skill"
ISSUE_COLUMNS = {
    "ID",
    "来源",
    "关联任务",
    "关联 AC",
    "严重程度",
    "状态",
    "问题描述",
    "修复负责人",
    "复现/证据",
    "验证者",
    "验证结果",
}
CRITERION_TYPES = {"automatic", "human"}
CRITERION_STATES = {"pending", "verified"}
TASK_NECESSITIES = {"required", "optional"}
TASK_STATES = {"pending", "working", "review", "blocked", "done"}
ISSUE_SEVERITIES = {"blocker", "high", "medium", "low"}
ISSUE_STATES = {"open", "fixing", "verify", "closed"}
INDEPENDENT_VERIFIERS = {"reviewer", "tester", "user"}


def without_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def frontmatter(text: str) -> dict[str, str]:
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


def strict_frontmatter(text: str, source: str) -> dict[str, str]:
    """Parse scalar Markdown frontmatter and reject ambiguous duplicate keys."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GraphLoadError(f"{source} 缺少 YAML frontmatter")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in values:
            raise GraphLoadError(f"{source} frontmatter 含重复字段：{key}")
        values[key] = value.strip().strip("\"'")
    raise GraphLoadError(f"{source} frontmatter 未闭合")


class TableParseError(ValueError):
    """Raised when a WALI state table cannot be parsed without data loss."""


def cells(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped and code-span pipes."""

    content = line.strip()
    if content.startswith("|"):
        content = content[1:]
    if content.endswith("|"):
        content = content[:-1]

    parsed_cells: list[str] = []
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
            parsed_cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1

    parsed_cells.append("".join(current).strip())
    return parsed_cells


def is_separator(values: Iterable[str]) -> bool:
    values = list(values)
    return bool(values) and all(re.fullmatch(r":?-{3,}:?", value) for value in values)


def table_rows(text: str, source: str) -> list[dict[str, str]]:
    """Return Markdown table rows keyed by their header labels."""

    lines = without_comments(text).splitlines()
    rows: list[dict[str, str]] = []
    index = 0

    while index + 1 < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue

        headers = cells(lines[index])
        separator = cells(lines[index + 1])
        if not is_separator(separator) or len(headers) != len(separator):
            index += 1
            continue

        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            values = cells(lines[index])
            if len(values) != len(headers):
                raise TableParseError(
                    f"{source}:{index + 1} 表格列数错误：期望 {len(headers)}，实际 {len(values)}"
                )
            rows.append(dict(zip(headers, values)))
            index += 1

    return rows


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(value: str) -> str:
    return value.strip().lower()


def has_evidence(value: str) -> bool:
    return normalized(value) not in EMPTY_EVIDENCE


class GraphLoadError(ValueError):
    """Raised when the WALI work graph cannot be loaded safely."""


@dataclass(frozen=True)
class Criterion:
    id: str
    kind: str
    description: str
    status: str
    evidence: str


@dataclass(frozen=True)
class Requirement:
    id: str
    kind: str
    description: str
    source: str
    acceptance_raw: str
    acceptance_ids: tuple[str, ...]


@dataclass(frozen=True)
class AcceptanceOracle:
    criterion_id: str
    rule: str
    method: str


@dataclass(frozen=True)
class Task:
    id: str
    acceptance_raw: str
    acceptance_ids: tuple[str, ...]
    title: str
    owner: str
    necessity: str
    status: str
    dependencies_raw: str
    dependencies: tuple[str, ...]
    scopes: tuple[str, ...]
    skills_raw: str
    skills: tuple[str, ...]
    evidence: str
    verifier: str


@dataclass(frozen=True)
class Issue:
    id: str
    task_raw: str
    task_ids: tuple[str, ...]
    acceptance_raw: str
    acceptance_ids: tuple[str, ...]
    severity: str
    status: str
    description: str
    fixer: str
    reproduction: str
    verifier: str
    validation: str


@dataclass(frozen=True)
class WaliGraph:
    goal_id: str
    goal_status: str
    spec_id: str
    spec_goal_id: str
    allowed_capabilities: tuple[str, ...]
    requirements: tuple[Requirement, ...]
    criteria: tuple[Criterion, ...]
    oracles: tuple[AcceptanceOracle, ...]
    tasks: tuple[Task, ...]
    issues: tuple[Issue, ...]


def _references(value: str, prefix: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(rf"\b{re.escape(prefix)}-\d+\b", value.upper())))


def _invalid_reference_tokens(value: str, prefix: str) -> tuple[str, ...]:
    cleaned = re.sub(r"<br\s*/?>", ",", value, flags=re.IGNORECASE)
    tokens = re.split(r"[,;；、/\\\s]+", cleaned)
    allowed_empty = {"", "-", "—", "无", "NONE", "N/A"}
    invalid: list[str] = []
    for token in tokens:
        normalized_token = token.strip().strip("`")
        if normalized_token.upper() in allowed_empty:
            continue
        if not re.fullmatch(rf"{re.escape(prefix)}-\d+", normalized_token.upper()):
            invalid.append(normalized_token)
    return tuple(dict.fromkeys(invalid))


def _scopes(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"<br\s*/?>", ",", value, flags=re.IGNORECASE)
    parts = re.split(r"[,;；、\n]+", cleaned)
    normalized_scopes: list[str] = []
    for part in parts:
        scope = part.strip().strip("`").replace("\\", "/")
        if not scope:
            continue
        normalized_scope = posixpath.normpath(scope)
        normalized_scopes.append(normalized_scope)
    return tuple(dict.fromkeys(normalized_scopes))


def _frontmatter_sequence(text: str, key: str) -> tuple[str, ...]:
    """Read one top-level YAML sequence after strict scalar-key validation."""

    lines = text.splitlines()
    collecting = False
    values: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line and not line[:1].isspace():
            current_key, separator, raw_value = line.partition(":")
            collecting = bool(separator and current_key.strip() == key)
            if collecting and raw_value.strip():
                raise GraphLoadError(f"goal.md 的 {key} 必须使用逐行列表")
            continue
        if not collecting or not line.strip():
            continue
        match = re.fullmatch(r"\s+-\s+(.+?)\s*", line)
        if match is None:
            raise GraphLoadError(f"goal.md 的 {key} 列表格式无效")
        values.append(match.group(1).strip().strip("\"'"))
    return tuple(dict.fromkeys(values))


def _skills(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"<br\s*/?>", ",", value, flags=re.IGNORECASE)
    parts = re.split(r"[,;；、\n]+", cleaned)
    return tuple(
        dict.fromkeys(
            part.strip().strip("`")
            for part in parts
            if part.strip().strip("`") not in {"", "-", "—", "无", "none", "N/A"}
        )
    )


def load_graph(project_root: Path, *, goal_text: str | None = None) -> WaliGraph:
    state_root = project_root / STATE_DIR
    missing = [name for name in STATE_FILES if not (state_root / name).exists()]
    if missing:
        raise GraphLoadError(f"缺少 WALI 状态文件：{', '.join(missing)}")

    try:
        goal_text = goal_text if goal_text is not None else read_text(state_root / "goal.md")
        goal_rows = table_rows(goal_text, "goal.md")
        spec_text = read_text(state_root / "spec.md")
        spec_rows = table_rows(spec_text, "spec.md")
        todo_rows = table_rows(read_text(state_root / "todo.md"), "todo.md")
        issue_rows = table_rows(read_text(state_root / "issues.md"), "issues.md")
    except TableParseError as error:
        raise GraphLoadError(str(error)) from error

    metadata = strict_frontmatter(goal_text, "goal.md")
    allowed_capabilities = _frontmatter_sequence(goal_text, "allowed_capabilities")
    spec_metadata = strict_frontmatter(spec_text, "spec.md")
    requirements = tuple(
        Requirement(
            id=row.get("ID", "").strip(),
            kind=row.get("类型", "").strip().lower(),
            description=row.get("规范要求", "").strip(),
            source=row.get("来源", "").strip(),
            acceptance_raw=row.get("关联 AC", "").strip(),
            acceptance_ids=_references(row.get("关联 AC", ""), "AC"),
        )
        for row in spec_rows
        if REQUIREMENT_COLUMNS.issubset(row)
    )
    criteria = tuple(
        Criterion(
            id=row.get("ID", "").strip(),
            kind=row.get("类型", "").strip().lower(),
            description=row.get("验收条件", "").strip(),
            status=row.get("状态", "").strip().lower(),
            evidence=row.get("证据", "").strip(),
        )
        for row in goal_rows
        if CRITERION_COLUMNS.issubset(row)
    )
    oracles = tuple(
        AcceptanceOracle(
            criterion_id=row.get("AC ID", "").strip(),
            rule=row.get("判定规则", "").strip(),
            method=row.get("验证方法", "").strip(),
        )
        for row in spec_rows
        if ORACLE_COLUMNS.issubset(row)
    )
    tasks = tuple(
        Task(
            id=row.get("ID", "").strip(),
            acceptance_raw=row.get("关联 AC", "").strip(),
            acceptance_ids=_references(row.get("关联 AC", ""), "AC"),
            title=row.get("任务", "").strip(),
            owner=row.get("负责人", "").strip().lower(),
            necessity=row.get("必要性", "").strip().lower(),
            status=row.get("状态", "").strip().lower(),
            dependencies_raw=row.get("依赖", "").strip(),
            dependencies=_references(row.get("依赖", ""), "T"),
            scopes=_scopes(row.get("允许修改范围", "")),
            skills_raw=row.get(OPTIONAL_TASK_SKILL_COLUMN, "").strip(),
            skills=_skills(row.get(OPTIONAL_TASK_SKILL_COLUMN, "")),
            evidence=row.get("执行结果/证据", "").strip(),
            verifier=row.get("独立验证者", "").strip().lower(),
        )
        for row in todo_rows
        if TASK_COLUMNS.issubset(row)
    )
    issues = tuple(
        Issue(
            id=row.get("ID", "").strip(),
            task_raw=row.get("关联任务", "").strip(),
            task_ids=_references(row.get("关联任务", ""), "T"),
            acceptance_raw=row.get("关联 AC", "").strip(),
            acceptance_ids=_references(row.get("关联 AC", ""), "AC"),
            severity=row.get("严重程度", "").strip().lower(),
            status=row.get("状态", "").strip().lower(),
            description=row.get("问题描述", "").strip(),
            fixer=row.get("修复负责人", "").strip().lower(),
            reproduction=row.get("复现/证据", "").strip(),
            verifier=row.get("验证者", "").strip().lower(),
            validation=row.get("验证结果", "").strip(),
        )
        for row in issue_rows
        if ISSUE_COLUMNS.issubset(row)
    )
    return WaliGraph(
        goal_id=metadata.get("goal_id", "").strip(),
        goal_status=metadata.get("status", "").strip().lower(),
        spec_id=spec_metadata.get("spec_id", "").strip(),
        spec_goal_id=spec_metadata.get("goal_id", "").strip(),
        allowed_capabilities=allowed_capabilities,
        requirements=requirements,
        criteria=criteria,
        oracles=oracles,
        tasks=tasks,
        issues=issues,
    )


def validate_graph(graph: WaliGraph) -> list[str]:
    reasons: list[str] = []
    if not graph.goal_id:
        reasons.append("goal.md 缺少 goal_id")
    elif not re.fullmatch(r"G-\d+", graph.goal_id):
        reasons.append(f"Goal ID 格式无效：{graph.goal_id}")
    if graph.spec_goal_id != graph.goal_id:
        reasons.append("spec.md 的 goal_id 必须与 goal.md 一致")
    if graph.spec_id != f"SPEC-{graph.goal_id}":
        reasons.append(f"Spec ID 必须是 SPEC-{graph.goal_id or 'G-n'}")
    for label, identifiers in (
        ("需求", [requirement.id for requirement in graph.requirements]),
        ("验收条件", [criterion.id for criterion in graph.criteria]),
        ("规格判定规则", [oracle.criterion_id for oracle in graph.oracles]),
        ("任务", [task.id for task in graph.tasks]),
        ("问题", [issue.id for issue in graph.issues]),
    ):
        for identifier, count in Counter(identifiers).items():
            if count > 1:
                reasons.append(f"{label} ID 重复：{identifier}")
    criterion_ids = {criterion.id for criterion in graph.criteria}
    task_ids = {task.id for task in graph.tasks}
    allowed_capabilities = set(graph.allowed_capabilities)
    for requirement in graph.requirements:
        if not re.fullmatch(r"R-\d+", requirement.id):
            reasons.append(f"需求 ID 格式无效：{requirement.id}")
        if not requirement.kind:
            reasons.append(f"{requirement.id or '未知需求'} 缺少需求类型")
        if not requirement.description:
            reasons.append(f"{requirement.id or '未知需求'} 的规范要求不得为空")
        if not requirement.source:
            reasons.append(f"{requirement.id or '未知需求'} 缺少来源")
        invalid_acceptance = _invalid_reference_tokens(
            requirement.acceptance_raw, "AC"
        )
        if invalid_acceptance:
            reasons.append(
                f"{requirement.id} 的关联 AC 含无效内容：{', '.join(invalid_acceptance)}"
            )
        if not requirement.acceptance_ids:
            reasons.append(f"{requirement.id} 没有关联任何验收条件")
        for criterion_id in requirement.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(
                    f"{requirement.id} 引用了不存在的验收条件 {criterion_id}"
                )
    for criterion in graph.criteria:
        if not re.fullmatch(r"AC-\d+", criterion.id):
            reasons.append(f"验收条件 ID 格式无效：{criterion.id}")
        if criterion.kind not in CRITERION_TYPES:
            reasons.append(f"{criterion.id or '未知 AC'} 类型必须是 automatic 或 human")
        if criterion.status not in CRITERION_STATES:
            reasons.append(f"{criterion.id or '未知 AC'} 状态必须是 pending 或 verified")
        if criterion.status == "verified" and not has_evidence(criterion.evidence):
            reasons.append(f"{criterion.id or '未知 AC'} 已标记 verified，但缺少证据")
    covered_by_requirements = {
        criterion_id
        for requirement in graph.requirements
        for criterion_id in requirement.acceptance_ids
    }
    for criterion in graph.criteria:
        if criterion.id not in covered_by_requirements:
            reasons.append(f"{criterion.id} 没有任何关联需求")
    oracle_by_criterion = {oracle.criterion_id: oracle for oracle in graph.oracles}
    for oracle in graph.oracles:
        if not re.fullmatch(r"AC-\d+", oracle.criterion_id):
            reasons.append(f"规格判定规则 AC ID 格式无效：{oracle.criterion_id}")
        elif oracle.criterion_id not in criterion_ids:
            reasons.append(f"规格判定规则引用不存在的验收条件 {oracle.criterion_id}")
        if not oracle.rule:
            reasons.append(f"{oracle.criterion_id or '未知 AC'} 的判定规则不得为空")
        if not oracle.method:
            reasons.append(f"{oracle.criterion_id or '未知 AC'} 的验证方法不得为空")
    for criterion in graph.criteria:
        if criterion.id not in oracle_by_criterion:
            reasons.append(f"{criterion.id} 缺少规格判定规则")
    for task in graph.tasks:
        if not re.fullmatch(r"T-\d+", task.id):
            reasons.append(f"任务 ID 格式无效：{task.id}")
        invalid_acceptance = _invalid_reference_tokens(task.acceptance_raw, "AC")
        if invalid_acceptance:
            reasons.append(
                f"{task.id} 的关联 AC 含无效内容：{', '.join(invalid_acceptance)}"
            )
        invalid_dependencies = _invalid_reference_tokens(task.dependencies_raw, "T")
        if invalid_dependencies:
            reasons.append(
                f"{task.id} 的依赖含无效内容：{', '.join(invalid_dependencies)}"
            )
        if not task.acceptance_ids:
            reasons.append(f"{task.id} 没有关联任何验收条件")
        for criterion_id in task.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(f"{task.id} 引用了不存在的验收条件 {criterion_id}")
        for dependency_id in task.dependencies:
            if dependency_id not in task_ids:
                reasons.append(f"{task.id} 依赖不存在的任务 {dependency_id}")
        if task.necessity not in TASK_NECESSITIES:
            reasons.append(f"{task.id or '未知任务'} 必要性必须是 required 或 optional")
        if task.status not in TASK_STATES:
            reasons.append(f"{task.id or '未知任务'} 状态不是允许的任务状态")
        if task.status == "done":
            if not has_evidence(task.evidence):
                reasons.append(f"任务 {task.id or '未知'} 已标记 done，但缺少执行结果/证据")
            if task.verifier not in INDEPENDENT_VERIFIERS:
                reasons.append(
                    f"任务 {task.id or '未知'} 必须记录 reviewer、tester 或 user 作为独立验证者"
                )
            elif task.verifier == task.owner:
                reasons.append(f"任务 {task.id or '未知'} 的独立验证者必须与负责人不同")
        if not task.scopes:
            reasons.append(f"{task.id} 没有明确允许修改范围")
        for skill in task.skills:
            if not re.fullmatch(r"Skill:[A-Za-z0-9._-]+", skill):
                reasons.append(f"{task.id} 的所用 Skill 格式无效：{skill}")
            elif skill not in allowed_capabilities:
                reasons.append(f"{task.id} 使用了未获 Goal 授权的能力：{skill}")
        for scope in task.scopes:
            prefix = _static_scope_prefix(scope)
            if not prefix:
                reasons.append(f"{task.id} 的允许修改范围过宽或无效：{scope}")
                continue
            if (
                prefix == "CLAUDE.md"
                or prefix == ".claude"
                or prefix.startswith(".claude/")
                or prefix == "claude"
                or prefix.startswith("claude/")
                or prefix == ".svn"
                or prefix.startswith(".svn/")
            ):
                reasons.append(f"{task.id} 的允许修改范围触及 WALI 控制面：{scope}")
    for issue in graph.issues:
        if not re.fullmatch(r"I-\d+", issue.id):
            reasons.append(f"问题 ID 格式无效：{issue.id}")
        invalid_tasks = _invalid_reference_tokens(issue.task_raw, "T")
        if invalid_tasks:
            reasons.append(
                f"{issue.id} 的关联任务含无效内容：{', '.join(invalid_tasks)}"
            )
        invalid_acceptance = _invalid_reference_tokens(issue.acceptance_raw, "AC")
        if invalid_acceptance:
            reasons.append(
                f"{issue.id} 的关联 AC 含无效内容：{', '.join(invalid_acceptance)}"
            )
        if not issue.task_ids and not issue.acceptance_ids:
            reasons.append(f"{issue.id} 没有关联任何任务或验收条件")
        for task_id in issue.task_ids:
            if task_id not in task_ids:
                reasons.append(f"{issue.id} 引用了不存在的任务 {task_id}")
        for criterion_id in issue.acceptance_ids:
            if criterion_id not in criterion_ids:
                reasons.append(f"{issue.id} 引用了不存在的验收条件 {criterion_id}")
        if issue.severity not in ISSUE_SEVERITIES:
            reasons.append(f"{issue.id or '未知问题'} 严重程度不是允许值")
        if issue.status not in ISSUE_STATES:
            reasons.append(f"{issue.id or '未知问题'} 状态不是允许的问题状态")
        if issue.status == "closed":
            if issue.verifier not in INDEPENDENT_VERIFIERS:
                reasons.append(
                    f"已关闭问题 {issue.id or '未知'} 必须记录 reviewer、tester 或 user 作为验证者"
                )
            elif issue.verifier == issue.fixer:
                reasons.append(f"已关闭问题 {issue.id or '未知'} 的验证者必须与修复负责人不同")
            if not has_evidence(issue.validation):
                reasons.append(f"已关闭问题 {issue.id or '未知'} 缺少独立验证结果")

    covered_criteria = {
        criterion_id for task in graph.tasks for criterion_id in task.acceptance_ids
    }
    for criterion in graph.criteria:
        if criterion.kind == "automatic" and criterion.id not in covered_criteria:
            reasons.append(f"{criterion.id} 没有任何关联任务")
        if criterion.kind == "automatic" and criterion.status == "verified":
            completed_required = [
                task
                for task in graph.tasks
                if task.necessity == "required"
                and task.status == "done"
                and criterion.id in task.acceptance_ids
            ]
            if not completed_required:
                reasons.append(f"{criterion.id} 已 verified，但没有关联已完成的 required 任务")

    dependencies = {task.id: task.dependencies for task in graph.tasks}
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

    for task in graph.tasks:
        cycle = visit(task.id)
        if cycle:
            reasons.append(f"任务依赖存在环：{' → '.join(cycle)}")
            break

    working_tasks = [task for task in graph.tasks if task.status == "working"]
    for left, right in itertools.combinations(working_tasks, 2):
        if scopes_overlap(left.scopes, right.scopes):
            reasons.append(
                f"working 任务 {left.id} 与 {right.id} 的允许修改范围重叠"
            )
    return reasons


def completion_reasons(graph: WaliGraph, *, require_human: bool) -> list[str]:
    """Return deterministic reasons the graph cannot enter a successful exit."""

    reasons = validate_graph(graph)
    automatic = [criterion for criterion in graph.criteria if criterion.kind == "automatic"]
    human = [criterion for criterion in graph.criteria if criterion.kind == "human"]
    required = [task for task in graph.tasks if task.necessity == "required"]
    if not automatic:
        reasons.append("目标至少需要一项 automatic 验收条件")
    if not human:
        reasons.append("目标至少需要一项 human 验收条件以保留用户最终验收权")
    if not required:
        reasons.append("目标至少需要一项 required 任务")
    for criterion in automatic:
        if criterion.status != "verified":
            reasons.append(f"{criterion.id} 尚未 verified")
    if require_human:
        for criterion in human:
            if criterion.status != "verified":
                reasons.append(f"{criterion.id} 尚未获得用户验收")
    for task in required:
        if task.status != "done":
            reasons.append(f"required 任务 {task.id} 尚未 done")
    for issue in graph.issues:
        if issue.severity == "blocker" and issue.status != "closed":
            reasons.append(f"存在未关闭的 blocker：{issue.id}")
    return list(dict.fromkeys(reasons))


def frontier(graph: WaliGraph) -> tuple[Task, ...]:
    tasks_by_id = {task.id: task for task in graph.tasks}
    blocking_issues = [
        issue
        for issue in graph.issues
        if issue.severity == "blocker" and issue.status != "closed"
    ]

    def is_blocked(task: Task) -> bool:
        return any(
            task.id in issue.task_ids
            or bool(set(task.acceptance_ids) & set(issue.acceptance_ids))
            for issue in blocking_issues
        )

    runnable = [
        task
        for task in graph.tasks
        if task.status == "pending"
        and not is_blocked(task)
        and all(
            tasks_by_id.get(dependency_id)
            and tasks_by_id[dependency_id].status == "done"
            for dependency_id in task.dependencies
        )
    ]
    return tuple(sorted(runnable, key=lambda task: (task.necessity != "required", task.id)))


def _static_scope_prefix(scope: str) -> str:
    if (
        normalized(scope) in AMBIGUOUS_SCOPES
        or not EXPLICIT_SCOPE_PATTERN.fullmatch(scope)
        or scope in {"", "."}
        or scope.startswith(("/", "~"))
        or ".." in scope.split("/")
    ):
        return ""
    wildcard = min(
        (index for token in ("*", "?", "[") if (index := scope.find(token)) >= 0),
        default=len(scope),
    )
    prefix = scope[:wildcard]
    if wildcard != len(scope):
        return prefix.rsplit("/", 1)[0] if "/" in prefix else ""
    return prefix.rstrip("/")


def scopes_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return True
    for left_scope in left:
        for right_scope in right:
            left_prefix = _static_scope_prefix(left_scope)
            right_prefix = _static_scope_prefix(right_scope)
            if not left_prefix or not right_prefix:
                return True
            if left_prefix == right_prefix:
                return True
            if left_prefix.startswith(right_prefix + "/"):
                return True
            if right_prefix.startswith(left_prefix + "/"):
                return True
    return False


def safe_parallel_pairs(graph: WaliGraph) -> tuple[tuple[Task, Task], ...]:
    return tuple(
        (left, right)
        for left, right in itertools.combinations(frontier(graph), 2)
        if not scopes_overlap(left.scopes, right.scopes)
    )


def _node_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value.upper())


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "\\\"").replace("\n", " ")


def to_mermaid(graph: WaliGraph) -> str:
    lines = ["flowchart LR"]
    goal_node = _node_id(graph.goal_id or "GOAL")
    criteria_by_id = {criterion.id: criterion for criterion in graph.criteria}

    if not graph.requirements and not graph.criteria:
        lines.append(f'    {goal_node}["{_label(graph.goal_id or "Goal")}"]')
    for requirement in graph.requirements:
        requirement_node = _node_id(requirement.id)
        lines.append(
            f'    {goal_node}["{_label(graph.goal_id or "Goal")}"] -->|包含需求| {requirement_node}'
        )
        lines.append(
            f'    {requirement_node}["{_label(f"{requirement.id} {requirement.description}")}"]'
        )
        for criterion_id in requirement.acceptance_ids:
            if criterion_id in criteria_by_id:
                lines.append(
                    f"    {requirement_node} -->|定义验收| {_node_id(criterion_id)}"
                )
    for criterion in graph.criteria:
        criterion_node = _node_id(criterion.id)
        lines.append(
            f'    {criterion_node}["{_label(f"{criterion.id} {criterion.description}")}"]'
        )
        if has_evidence(criterion.evidence):
            evidence_node = f"E_{criterion_node}"
            lines.append(f'    {evidence_node}["{_label(criterion.evidence)}"]')
            lines.append(f"    {criterion_node} -->|证据| {evidence_node}")

    for task in graph.tasks:
        task_node = _node_id(task.id)
        lines.append(f'    {task_node}["{_label(f"{task.id} {task.title}")}"]')
        for criterion_id in task.acceptance_ids:
            if criterion_id in criteria_by_id:
                lines.append(f"    {_node_id(criterion_id)} -->|由任务实现| {task_node}")
        for dependency_id in task.dependencies:
            lines.append(f"    {_node_id(dependency_id)} -->|阻塞| {task_node}")
        if task.owner and task.owner not in {"待分配", "none", "-"}:
            owner_node = f"AGENT_{_node_id(task.owner)}"
            lines.append(f'    {owner_node}(["{_label(task.owner)}"])')
            lines.append(f"    {owner_node} -->|负责| {task_node}")
        for skill in task.skills:
            skill_node = f"SKILL_{_node_id(skill)}"
            lines.append(f'    {skill_node}(["{_label(skill)}"])')
            lines.append(f"    {skill_node} -->|提供方法| {task_node}")
        if task.verifier and task.verifier not in {"待分配", "none", "-"}:
            verifier_node = f"AGENT_{_node_id(task.verifier)}"
            lines.append(f'    {verifier_node}(["{_label(task.verifier)}"])')
            lines.append(f"    {verifier_node} -->|验证| {task_node}")
        if has_evidence(task.evidence):
            evidence_node = f"E_{task_node}"
            lines.append(f'    {evidence_node}["{_label(task.evidence)}"]')
            lines.append(f"    {task_node} -->|证据| {evidence_node}")

    for issue in graph.issues:
        issue_node = _node_id(issue.id)
        lines.append(f'    {issue_node}{{"{_label(f"{issue.id} {issue.description}")}"}}')
        for task_id in issue.task_ids:
            lines.append(f"    {issue_node} -->|影响| {_node_id(task_id)}")
        for criterion_id in issue.acceptance_ids:
            lines.append(f"    {issue_node} -->|影响| {_node_id(criterion_id)}")
        if has_evidence(issue.reproduction):
            evidence_node = f"E_{issue_node}_REPRO"
            lines.append(f'    {evidence_node}["{_label(issue.reproduction)}"]')
            lines.append(f"    {issue_node} -->|复现证据| {evidence_node}")
        if has_evidence(issue.validation):
            evidence_node = f"E_{issue_node}_VERIFY"
            lines.append(f'    {evidence_node}["{_label(issue.validation)}"]')
            lines.append(f"    {issue_node} -->|验证证据| {evidence_node}")

    return "\n".join(lines) + "\n"


def _run_check(project_root: Path) -> int:
    try:
        graph = load_graph(project_root)
    except GraphLoadError as error:
        print(f"WALI 工作图检查未通过：\n- {error}")
        return 1

    reasons = validate_graph(graph)
    if reasons:
        print("WALI 工作图检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1

    print("WALI 工作图检查通过。")
    return 0


def _run_frontier(project_root: Path) -> int:
    try:
        graph = load_graph(project_root)
    except GraphLoadError as error:
        print(f"无法计算当前可执行任务：{error}")
        return 1

    reasons = validate_graph(graph)
    if reasons:
        print("无法计算当前可执行任务，工作图检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    tasks = frontier(graph)
    if not tasks:
        print("当前没有可执行任务。")
        return 0
    print("当前可执行任务：")
    for task in tasks:
        print(f"- {task.id} {task.title} ({task.necessity})")
    return 0


def _run_parallel(project_root: Path) -> int:
    try:
        graph = load_graph(project_root)
    except GraphLoadError as error:
        print(f"无法计算安全并行候选：{error}")
        return 1

    reasons = validate_graph(graph)
    if reasons:
        print("无法计算安全并行候选，工作图检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    pairs = safe_parallel_pairs(graph)
    if not pairs:
        print("当前没有可安全并行的任务组合。")
        return 0
    print("安全并行候选：")
    for left, right in pairs:
        print(f"- {left.id} + {right.id}")
    return 0


def _run_mermaid(project_root: Path) -> int:
    try:
        graph = load_graph(project_root)
    except GraphLoadError as error:
        print(f"无法生成 Mermaid：{error}")
        return 1
    print(to_mermaid(graph), end="")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("command", choices=("check", "frontier", "parallel", "mermaid"))
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "frontier":
        return _run_frontier(project_root)
    if args.command == "parallel":
        return _run_parallel(project_root)
    if args.command == "mermaid":
        return _run_mermaid(project_root)
    return _run_check(project_root)


if __name__ == "__main__":
    sys.exit(main())
