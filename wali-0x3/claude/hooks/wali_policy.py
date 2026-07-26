#!/usr/bin/env python3
"""Enforce WALI phase/effect contracts at Claude Code tool boundaries."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from wali_graph import (
    CRITERION_COLUMNS,
    GraphLoadError,
    ORACLE_COLUMNS,
    REQUIREMENT_COLUMNS,
    TableParseError,
    completion_reasons,
    frontmatter as markdown_frontmatter,
    load_graph,
    strict_frontmatter,
    table_rows,
    validate_graph,
)
from wali_svn import (
    SvnBoundaryError,
    classify_status_xml,
    discover_working_copy_root,
    is_verified_working_copy_root,
    read_status_xml,
)


STATE_DIR = Path("docs/wali-0x3")
WALI_SCHEMA_VERSION = "1"
STATE_FILES = {
    "docs/wali-0x3/goal.md",
    "docs/wali-0x3/spec.md",
    "docs/wali-0x3/todo.md",
    "docs/wali-0x3/issues.md",
    "docs/wali-0x3/handoff.md",
}
PHASES = {
    "clarifying",
    "awaiting_direction",
    "planning",
    "implementing",
    "inspecting",
    "accepting",
    "blocked",
    "delivering",
    "closed",
    "terminated",
}
EFFECTS = {
    "read_workspace",
    "ask_user",
    "update_goal_draft",
    "update_spec_draft",
    "update_goal",
    "update_todo",
    "update_issues",
    "update_handoff",
    "transition_phase",
    "modify_implementation",
    "manage_svn_schedule",
    "sync_svn_working_copy",
    "run_project_commands",
    "run_checks",
}
REQUIRED_KEYS = {
    "wali_schema",
    "goal_id",
    "status",
    "phase",
    "active_task",
    "goal_confirmation",
    "goal_confirmation_evidence",
    "goal_definition_digest",
    "allowed_effects",
    "allowed_capabilities",
    "write_scope",
    "preexisting_changes",
    "carry_epoch",
    "carried_history",
    "carried_changes",
    "stop_intent",
    "waiting_for",
    "waiting_detail",
    "blocked_reason",
    "exit_outcome",
    "exit_reason",
    "exit_evidence",
    "exit_change_disposition",
    "superseded_by",
    "allow_new_artifacts",
    "allow_implementation_changes",
    "allow_external_writes",
    "allow_svn_commit",
}
CLARIFYING_EFFECTS = {
    "read_workspace",
    "ask_user",
    "update_goal_draft",
    "update_spec_draft",
    "update_handoff",
}
CLARIFYING_WRITE_SCOPE = {
    "docs/wali-0x3/goal.md",
    "docs/wali-0x3/spec.md",
    "docs/wali-0x3/handoff.md",
}
PHASE_PROFILES: dict[str, dict[str, object]] = {
    "clarifying": {
        "statuses": {"draft"},
        "effects": CLARIFYING_EFFECTS,
        "scopes": CLARIFYING_WRITE_SCOPE,
        "active_task": "none",
        "confirmation": "pending",
        "flags": (False, False, False, False),
    },
    "awaiting_direction": {
        "statuses": {"waiting_user"},
        "effects": {
            "read_workspace",
            "ask_user",
            "update_goal",
            "update_handoff",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "none",
        "confirmation": "either",
        "flags": (False, False, False, False),
    },
    "planning": {
        "statuses": {"active"},
        "effects": {
            "read_workspace",
            "ask_user",
            "update_goal",
            "update_todo",
            "update_issues",
            "update_handoff",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/todo.md",
            "docs/wali-0x3/issues.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "none",
        "confirmation": "confirmed",
        "flags": (False, False, False, False),
    },
    "implementing": {
        "statuses": {"active"},
        "effects": {
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
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/todo.md",
            "docs/wali-0x3/issues.md",
            "docs/wali-0x3/handoff.md",
            "@active_task",
        },
        "active_task": "task",
        "confirmation": "confirmed",
        "flags": (True, True, False, False),
    },
    "inspecting": {
        "statuses": {"active"},
        "effects": {
            "read_workspace",
            "ask_user",
            "update_todo",
            "update_issues",
            "update_handoff",
            "transition_phase",
            "run_checks",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/todo.md",
            "docs/wali-0x3/issues.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "task",
        "confirmation": "confirmed",
        "flags": (False, False, False, False),
    },
    "accepting": {
        "statuses": {"waiting_user"},
        "effects": {
            "read_workspace",
            "ask_user",
            "update_goal",
            "update_issues",
            "update_handoff",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/issues.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "none",
        "confirmation": "confirmed",
        "flags": (False, False, False, False),
    },
    "blocked": {
        "statuses": {"blocked"},
        "effects": {
            "read_workspace",
            "ask_user",
            "update_goal",
            "update_handoff",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "optional_task",
        "confirmation": "either",
        "flags": (False, False, False, False),
    },
    "delivering": {
        "statuses": {"done"},
        "effects": {
            "read_workspace",
            "update_handoff",
            "transition_phase",
        },
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
            "@svn_commit",
        },
        "active_task": "none",
        "confirmation": "confirmed",
        "flags": (False, False, False, True),
    },
    "closed": {
        "statuses": {"done"},
        "effects": {"read_workspace", "update_handoff", "transition_phase"},
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "none",
        "confirmation": "confirmed",
        "flags": (False, False, False, False),
    },
    "terminated": {
        "statuses": {"cancelled", "superseded", "aborted"},
        "effects": {"read_workspace", "update_handoff", "transition_phase"},
        "scopes": {
            "docs/wali-0x3/goal.md",
            "docs/wali-0x3/handoff.md",
        },
        "active_task": "none",
        "confirmation": "either",
        "flags": (False, False, False, False),
    },
}

PHASE_TRANSITIONS = {
    "clarifying": {"clarifying", "awaiting_direction", "planning", "blocked", "terminated"},
    "awaiting_direction": {
        "awaiting_direction",
        "clarifying",
        "planning",
        "implementing",
        "inspecting",
        "accepting",
        "blocked",
        "terminated",
    },
    "planning": {"planning", "clarifying", "awaiting_direction", "implementing", "blocked", "terminated"},
    "implementing": {
        "implementing",
        "clarifying",
        "awaiting_direction",
        "inspecting",
        "blocked",
        "terminated",
    },
    "inspecting": {
        "inspecting",
        "clarifying",
        "awaiting_direction",
        "implementing",
        "accepting",
        "blocked",
        "terminated",
    },
    "accepting": {
        "accepting",
        "clarifying",
        "awaiting_direction",
        "implementing",
        "delivering",
        "closed",
        "blocked",
        "terminated",
    },
    "blocked": {
        "blocked",
        "clarifying",
        "awaiting_direction",
        "planning",
        "implementing",
        "inspecting",
        "accepting",
        "terminated",
    },
    "delivering": {"delivering", "clarifying", "terminated"},
    "closed": {"closed", "clarifying"},
    "terminated": {"terminated", "clarifying"},
}


class PolicyError(ValueError):
    """Raised when the phase contract cannot be loaded safely."""


def _scalar(value: str) -> str | bool:
    cleaned = value.strip().strip("\"'")
    if cleaned.lower() == "true":
        return True
    if cleaned.lower() == "false":
        return False
    return cleaned


def parse_frontmatter(text: str) -> dict[str, str | bool | tuple[str, ...]]:
    """Parse the flat scalars and string lists used by WALI frontmatter."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PolicyError("goal.md 缺少 YAML frontmatter")

    values: dict[str, str | bool | tuple[str, ...]] = {}
    active_list: str | None = None
    list_values: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            if active_list is not None:
                values[active_list] = tuple(list_values)
            return values
        if line.startswith("  - "):
            if active_list is None:
                raise PolicyError("frontmatter 列表项缺少父字段")
            list_values.append(str(_scalar(line[4:])))
            continue
        if line[:1].isspace() or ":" not in line:
            continue
        if active_list is not None:
            values[active_list] = tuple(list_values)
            active_list = None
            list_values = []
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if key in values:
            raise PolicyError(f"frontmatter 含重复字段：{key}")
        if not raw_value.strip():
            active_list = key
            continue
        values[key] = _scalar(raw_value)
    raise PolicyError("goal.md frontmatter 未闭合")


def _string(contract: dict[str, object], key: str) -> str:
    value = contract.get(key)
    return value if isinstance(value, str) else ""


def _strings(contract: dict[str, object], key: str) -> tuple[str, ...]:
    value = contract.get(key)
    return value if isinstance(value, tuple) else ()


def _goal_body(text: str) -> str:
    match = re.match(r"\A---\s*\n.*?\n---\s*\n?", text, flags=re.DOTALL)
    if not match:
        raise PolicyError("goal.md frontmatter 无法定位")
    return text[match.end() :]


def _numbered_section(body: str, number: int) -> str:
    match = re.search(
        rf"^##\s+{number}\.\s+.*?$([\s\S]*?)(?=^##\s+|\Z)",
        body,
        flags=re.MULTILINE,
    )
    if not match:
        return ""
    section = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL)
    return "\n".join(line.rstrip() for line in section.strip().splitlines())


def _normalized_spec_snapshot(text: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    normalized_lines = [line.rstrip() for line in without_comments.replace("\r\n", "\n").splitlines()]
    return "\n".join(normalized_lines).strip() + "\n"


def _goal_definition_digest_from_text(
    text: str, contract: dict[str, object], spec_text: str
) -> str:
    body = _goal_body(text)
    try:
        rows = table_rows(text, "goal.md")
    except TableParseError as error:
        raise PolicyError(str(error)) from error
    criteria = [
        {
            "id": row.get("ID", "").strip(),
            "kind": row.get("类型", "").strip().lower(),
            "description": row.get("验收条件", "").strip(),
        }
        for row in rows
        if {"ID", "类型", "验收条件", "状态", "证据"}.issubset(row)
    ]
    checks = [
        {
            "name": row.get("检查", "").strip(),
            "method": row.get("命令或方法", "").strip(),
            "pass": row.get("通过条件", "").strip(),
        }
        for row in rows
        if {"检查", "命令或方法", "通过条件"}.issubset(row)
    ]
    canonical = {
        "goal_id": _string(contract, "goal_id"),
        "sections": [_numbered_section(body, number) for number in range(2, 7)],
        "criteria": criteria,
        "checks": checks,
        "spec_snapshot": _normalized_spec_snapshot(spec_text),
        "preexisting_changes": sorted(_strings(contract, "preexisting_changes")),
        "allowed_capabilities": sorted(_strings(contract, "allowed_capabilities")),
    }
    serialized = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def goal_definition_digest(project_root: Path, contract: dict[str, object]) -> str:
    """Hash the user-confirmed, stable portion of Goal—not mutable evidence."""

    goal_path = project_root / STATE_DIR / "goal.md"
    spec_path = project_root / STATE_DIR / "spec.md"
    return _goal_definition_digest_from_text(
        goal_path.read_text(encoding="utf-8"),
        contract,
        spec_path.read_text(encoding="utf-8"),
    )


def _goal_completeness_from_text(text: str) -> list[str]:
    body = _goal_body(text)
    try:
        rows = table_rows(text, "goal.md")
    except TableParseError as error:
        return [str(error)]
    reasons: list[str] = []
    for number, label in ((5, "目标与背景"), (6, "范围与约束")):
        content = _numbered_section(body, number)
        meaningful = [
            line.strip(" #-")
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not any(value and "待" not in value for value in meaningful):
            reasons.append(f"Goal 的{label}尚未形成可确认内容")
    question_rows = [
        row
        for row in rows
        if {"ID", "问题", "为什么影响结果", "状态", "答案或依据"}.issubset(row)
    ]
    open_questions = [
        row.get("ID", "未知问题")
        for row in question_rows
        if row.get("状态", "").strip().lower() not in {"resolved", "closed"}
    ]
    if open_questions:
        reasons.append("仍有未解决的高影响问题：" + ", ".join(open_questions))
    criteria = [
        row
        for row in rows
        if {"ID", "类型", "验收条件", "状态", "证据"}.issubset(row)
    ]
    kinds = {row.get("类型", "").strip().lower() for row in criteria}
    if "automatic" not in kinds:
        reasons.append("Goal 至少需要一项 automatic 验收条件")
    if "human" not in kinds:
        reasons.append("Goal 至少需要一项 human 验收条件")
    if any(not row.get("验收条件", "").strip() for row in criteria):
        reasons.append("Goal 验收条件不得为空")
    checks = [
        row
        for row in rows
        if {"检查", "命令或方法", "通过条件"}.issubset(row)
    ]
    if not checks:
        reasons.append("Goal 至少需要一种明确检查方式")
    return reasons


def _spec_completeness_from_text(spec_text: str, goal_text: str) -> list[str]:
    """Validate the normalized specification that is sealed with a Goal."""

    reasons: list[str] = []
    metadata = markdown_frontmatter(spec_text)
    goal_metadata = markdown_frontmatter(goal_text)
    goal_id = goal_metadata.get("goal_id", "").strip()
    if metadata.get("spec_id", "").strip() != f"SPEC-{goal_id}":
        reasons.append(f"spec.md 的 spec_id 必须是 SPEC-{goal_id or 'G-n'}")
    if metadata.get("goal_id", "").strip() != goal_id:
        reasons.append("spec.md 的 goal_id 必须与 goal.md 一致")
    if metadata.get("source_mode", "").strip().lower() not in {
        "discovery",
        "pressure_test",
        "hybrid",
    }:
        reasons.append("spec.md 的 source_mode 必须是 discovery、pressure_test 或 hybrid")
    try:
        spec_rows = table_rows(spec_text, "spec.md")
        goal_rows = table_rows(goal_text, "goal.md")
    except TableParseError as error:
        return reasons + [str(error)]

    spec_body = _goal_body(spec_text)
    for number, label in (
        (1, "输入、来源与形成方式"),
        (3, "行为、场景与边界"),
        (4, "接口、数据与错误契约"),
        (5, "质量属性、依赖与运行约束"),
    ):
        content = _numbered_section(spec_body, number)
        meaningful = [
            line.strip(" #-")
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not any(
            value
            and not any(
                placeholder in value.lower()
                for placeholder in ("待补充", "待确定", "tbd", "unknown")
            )
            for value in meaningful
        ):
            reasons.append(f"spec.md 的{label}尚未形成可确认内容")

    requirements = [
        row for row in spec_rows if REQUIREMENT_COLUMNS.issubset(row)
    ]
    oracles = [row for row in spec_rows if ORACLE_COLUMNS.issubset(row)]
    criteria = [row for row in goal_rows if CRITERION_COLUMNS.issubset(row)]
    criterion_ids = {row.get("ID", "").strip() for row in criteria}
    if not requirements:
        reasons.append("spec.md 至少需要一项规范需求")
    linked_criteria: set[str] = set()
    requirement_ids: set[str] = set()
    for row in requirements:
        requirement_id = row.get("ID", "").strip()
        if not re.fullmatch(r"R-\d+", requirement_id):
            reasons.append(f"需求 ID 格式无效：{requirement_id or '空'}")
        elif requirement_id in requirement_ids:
            reasons.append(f"需求 ID 重复：{requirement_id}")
        requirement_ids.add(requirement_id)
        for column in ("类型", "规范要求", "来源"):
            value = row.get(column, "").strip()
            if not value or value.lower() in {"tbd", "unknown", "待补充", "待确定"}:
                reasons.append(f"{requirement_id or '未知需求'} 的{column}尚未形成可确认内容")
        raw_links = row.get("关联 AC", "").strip()
        links = set(re.findall(r"\bAC-\d+\b", raw_links.upper()))
        cleaned_links = re.sub(r"<br\s*/?>", ",", raw_links, flags=re.IGNORECASE)
        invalid_links = [
            token.strip().strip("`")
            for token in re.split(r"[,;；、/\\\s]+", cleaned_links)
            if token.strip().strip("`")
            and not re.fullmatch(r"AC-\d+", token.strip().strip("`").upper())
        ]
        if invalid_links:
            reasons.append(
                f"{requirement_id or '未知需求'} 的关联 AC 含无效内容："
                + ", ".join(dict.fromkeys(invalid_links))
            )
        if not links:
            reasons.append(f"{requirement_id or '未知需求'} 没有关联任何验收条件")
        linked_criteria.update(links)
        unknown = sorted(links - criterion_ids)
        if unknown:
            reasons.append(
                f"{requirement_id or '未知需求'} 引用了不存在的验收条件："
                + ", ".join(unknown)
            )
    for criterion_id in sorted(criterion_ids - linked_criteria):
        reasons.append(f"{criterion_id} 没有任何关联需求")

    oracle_ids: list[str] = []
    for row in oracles:
        criterion_id = row.get("AC ID", "").strip()
        oracle_ids.append(criterion_id)
        if criterion_id not in criterion_ids:
            reasons.append(f"规格判定规则引用不存在的验收条件 {criterion_id or '空'}")
        if not row.get("判定规则", "").strip():
            reasons.append(f"{criterion_id or '未知 AC'} 的判定规则不得为空")
        if not row.get("验证方法", "").strip():
            reasons.append(f"{criterion_id or '未知 AC'} 的验证方法不得为空")
    for criterion_id, count in Counter(oracle_ids).items():
        if count > 1:
            reasons.append(f"{criterion_id or '未知 AC'} 的规格判定规则重复")
    for criterion_id in sorted(criterion_ids - set(oracle_ids)):
        reasons.append(f"{criterion_id} 缺少规格判定规则")
    return reasons


def _goal_completeness(project_root: Path) -> list[str]:
    goal_path = project_root / STATE_DIR / "goal.md"
    spec_path = project_root / STATE_DIR / "spec.md"
    goal_text = goal_path.read_text(encoding="utf-8")
    spec_text = spec_path.read_text(encoding="utf-8")
    return _goal_completeness_from_text(goal_text) + _spec_completeness_from_text(
        spec_text, goal_text
    )


def _spec_identity_reasons(
    project_root: Path, contract: dict[str, object]
) -> list[str]:
    """Keep the fixed Spec owned by the current Goal in every phase."""

    try:
        spec_text = (project_root / STATE_DIR / "spec.md").read_text(encoding="utf-8")
        metadata = strict_frontmatter(spec_text, "spec.md")
    except (OSError, GraphLoadError) as error:
        return [str(error)]
    goal_id = _string(contract, "goal_id")
    reasons: list[str] = []
    if metadata.get("goal_id", "").strip() != goal_id:
        reasons.append("spec.md 的 goal_id 必须与 goal.md 一致")
    if metadata.get("spec_id", "").strip() != f"SPEC-{goal_id}":
        reasons.append(f"spec.md 的 spec_id 必须是 SPEC-{goal_id or 'G-n'}")
    return reasons


def _success_exit_reasons(
    project_root: Path,
    contract: dict[str, object],
    *,
    goal_text: str | None = None,
    status_xml: str | None = None,
) -> list[str]:
    """Validate the evidence graph and live SVN boundary before success."""

    try:
        graph = load_graph(project_root, goal_text=goal_text)
    except GraphLoadError as error:
        return [str(error)]
    reasons = completion_reasons(graph, require_human=True)
    if status_xml is not None:
        reasons.extend(audit_changes(project_root, contract, status_xml))
        return list(dict.fromkeys(reasons))
    try:
        svn_root = _svn_working_copy_root(project_root)
    except PolicyError as error:
        return reasons + [f"无法确认 SVN 工作副本边界：{error}"]
    if svn_root is None:
        return reasons
    if svn_root != project_root.resolve():
        return reasons + ["WALI 必须从 SVN 工作副本根进入成功终态"]
    try:
        live_status = status_xml if status_xml is not None else _status_xml_from_svn(project_root)
    except PolicyError as error:
        return reasons + [f"成功收尾前无法审计 SVN 差异：{error}"]
    reasons.extend(audit_changes(project_root, contract, live_status))
    return list(dict.fromkeys(reasons))


def validate_contract(contract: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    missing = sorted(REQUIRED_KEYS - contract.keys())
    if missing:
        reasons.append(f"阶段契约缺少字段：{', '.join(missing)}")
        return reasons

    wali_schema = _string(contract, "wali_schema")
    if wali_schema != WALI_SCHEMA_VERSION:
        reasons.append(
            "不支持的 wali_schema："
            f"{wali_schema or '空'}；当前仅支持 {WALI_SCHEMA_VERSION}"
        )

    phase = _string(contract, "phase").lower()
    if phase not in PHASES:
        reasons.append(f"未知 phase：{phase or '空'}")

    effects = set(_strings(contract, "allowed_effects"))
    unknown_effects = sorted(effects - EFFECTS)
    if unknown_effects:
        reasons.append(f"allowed_effects 含未知值：{', '.join(unknown_effects)}")

    for key in (
        "allowed_effects",
        "allowed_capabilities",
        "write_scope",
        "preexisting_changes",
        "carried_history",
        "carried_changes",
    ):
        if not isinstance(contract.get(key), tuple):
            reasons.append(f"{key} 必须是 YAML 列表")

    for capability in _strings(contract, "allowed_capabilities"):
        if not re.fullmatch(r"(?:Skill|Agent):[A-Za-z0-9._-]+", capability):
            reasons.append(f"allowed_capabilities 格式无效：{capability}")

    stop_intent = _string(contract, "stop_intent")
    if stop_intent not in {"continue", "handoff"}:
        reasons.append("stop_intent 必须是 continue 或 handoff")

    for scope in _strings(contract, "write_scope"):
        normalized = posixpath.normpath(scope.replace("\\", "/"))
        if (
            scope.startswith(("/", "~"))
            or ".." in scope.split("/")
            or normalized == "."
            or normalized == ".svn"
            or normalized.startswith(".svn/")
        ):
            reasons.append(f"write_scope 必须是明确的项目相对路径：{scope}")

    for entry in _strings(contract, "preexisting_changes"):
        path, separator, fingerprint = entry.rpartition("::")
        normalized = posixpath.normpath(path.replace("\\", "/"))
        if (
            not separator
            or not path
            or path.startswith(("/", "~"))
            or ".." in path.split("/")
            or normalized == "."
            or normalized == ".svn"
            or normalized.startswith(".svn/")
        ):
            reasons.append(f"preexisting_changes 路径无效：{entry}")
        elif fingerprint != "missing" and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            reasons.append(f"preexisting_changes 指纹无效：{entry}")

    for entry in _strings(contract, "carried_changes"):
        path, separator, fingerprint = entry.rpartition("::")
        normalized = posixpath.normpath(path.replace("\\", "/"))
        if (
            not separator
            or not path
            or path.startswith(("/", "~"))
            or ".." in path.split("/")
            or normalized == "."
            or normalized == ".svn"
            or normalized.startswith(".svn/")
        ):
            reasons.append(f"carried_changes 路径无效：{entry}")
        elif fingerprint != "missing" and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            reasons.append(f"carried_changes 指纹无效：{entry}")

    carry_epoch = _string(contract, "carry_epoch")
    valid_carry_epoch = carry_epoch.isdigit()
    if not valid_carry_epoch:
        reasons.append("carry_epoch 必须是非负整数")
    carry_epoch_number = int(carry_epoch) if valid_carry_epoch else 0
    if _strings(contract, "carried_changes") and carry_epoch_number == 0:
        reasons.append("存在 carried_changes 时 carry_epoch 必须大于 0")
    history_keys: set[tuple[int, str]] = set()
    for entry in _strings(contract, "carried_history"):
        parts = entry.split("::", 2)
        if len(parts) != 3:
            reasons.append(f"carried_history 条目无效：{entry}")
            continue
        raw_epoch, path, fingerprint = parts
        normalized = posixpath.normpath(path.replace("\\", "/"))
        if (
            not raw_epoch.isdigit()
            or int(raw_epoch) >= carry_epoch_number
            or not path
            or path.startswith(("/", "~"))
            or ".." in path.split("/")
            or normalized == "."
            or normalized == ".svn"
            or normalized.startswith(".svn/")
            or (
                fingerprint != "missing"
                and not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            )
        ):
            reasons.append(f"carried_history 条目无效：{entry}")
            continue
        key = (int(raw_epoch), normalized)
        if key in history_keys:
            reasons.append(f"carried_history 含重复代次路径：{entry}")
        history_keys.add(key)

    for key in (
        "allow_new_artifacts",
        "allow_implementation_changes",
        "allow_external_writes",
        "allow_svn_commit",
    ):
        if not isinstance(contract.get(key), bool):
            reasons.append(f"{key} 必须是 true 或 false")

    exit_outcome = _string(contract, "exit_outcome")
    exit_reason = _string(contract, "exit_reason").strip()
    exit_evidence = _string(contract, "exit_evidence").strip()
    exit_disposition = _string(contract, "exit_change_disposition")
    superseded_by = _string(contract, "superseded_by")
    if exit_outcome not in {
        "none",
        "completed",
        "cancelled",
        "superseded",
        "aborted",
    }:
        reasons.append(
            "exit_outcome 必须是 none、completed、cancelled、superseded 或 aborted"
        )
    if phase in {"delivering", "closed"}:
        if exit_outcome != "completed":
            reasons.append(f"{phase} phase 的 exit_outcome 必须是 completed")
        if not exit_reason:
            reasons.append(f"{phase} phase 必须记录 exit_reason")
        if not exit_evidence:
            reasons.append(f"{phase} phase 必须记录 exit_evidence")
        if exit_disposition != "none":
            reasons.append("成功完成时 exit_change_disposition 必须是 none")
        if superseded_by != "none":
            reasons.append("成功完成时 superseded_by 必须是 none")
    elif phase == "terminated":
        if exit_outcome not in {"cancelled", "superseded", "aborted"}:
            reasons.append(
                "terminated phase 的 exit_outcome 必须是 cancelled、superseded 或 aborted"
            )
        if not exit_reason:
            reasons.append("terminated phase 必须记录 exit_reason")
        if not exit_evidence:
            reasons.append("terminated phase 必须记录 exit_evidence")
        if exit_disposition not in {
            "preserve",
            "handoff",
            "user_authorized_cleanup",
        }:
            reasons.append(
                "terminated phase 的 exit_change_disposition 必须是 preserve、handoff 或 user_authorized_cleanup"
            )
        if exit_outcome == "superseded":
            if not re.fullmatch(r"G-\d+", superseded_by) or superseded_by == _string(
                contract, "goal_id"
            ):
                reasons.append("superseded 退出必须记录不同的 superseded_by Goal ID")
        elif superseded_by != "none":
            reasons.append("非 superseded 退出的 superseded_by 必须是 none")
        if _string(contract, "status") != exit_outcome:
            reasons.append("terminated phase 的 status 必须与 exit_outcome 一致")
    elif any(
        (
            exit_outcome != "none",
            bool(exit_reason),
            bool(exit_evidence),
            exit_disposition != "none",
            superseded_by != "none",
        )
    ):
        reasons.append(
            "非退出阶段不得声明退出结果；exit_outcome、退出说明和变更处置必须保持空状态"
        )

    profile = PHASE_PROFILES.get(phase)
    if profile:
        status = _string(contract, "status")
        if status not in profile["statuses"]:
            expected = ", ".join(sorted(profile["statuses"]))
            reasons.append(f"{phase} phase 的 status 必须是 {expected}")
        if effects != profile["effects"]:
            reasons.append(f"{phase} phase 的 allowed_effects 与标准契约不一致")
        if set(_strings(contract, "write_scope")) != profile["scopes"]:
            reasons.append(f"{phase} phase 的 write_scope 与标准契约不一致")

        active_task = _string(contract, "active_task")
        active_requirement = profile["active_task"]
        if active_requirement == "none" and active_task.lower() not in {"none", "无"}:
            reasons.append(f"{phase} phase 不能设置 active_task")
        if active_requirement == "task" and not re.fullmatch(r"T-\d+", active_task):
            reasons.append(f"{phase} phase 必须设置有效 active_task")
        if active_requirement == "optional_task" and active_task.lower() not in {"none", "无"}:
            if not re.fullmatch(r"T-\d+", active_task):
                reasons.append("blocked phase 的 active_task 必须是 none 或有效任务 ID")

        confirmation = _string(contract, "goal_confirmation")
        confirmation_requirement = profile["confirmation"]
        if confirmation_requirement != "either" and confirmation != confirmation_requirement:
            reasons.append(
                f"{phase} phase 的 goal_confirmation 必须是 {confirmation_requirement}"
            )
        if confirmation_requirement == "confirmed" and not _string(
            contract, "goal_confirmation_evidence"
        ).strip():
            reasons.append("goal_confirmation_evidence 必须记录用户确认依据")
        elif confirmation == "confirmed" and not _string(
            contract, "goal_confirmation_evidence"
        ).strip():
            reasons.append("goal_confirmation_evidence 必须记录用户确认依据")
        if confirmation == "pending" and _string(
            contract, "goal_confirmation_evidence"
        ).strip():
            reasons.append("goal_confirmation=pending 时不得保留确认依据")

        waiting_for = _string(contract, "waiting_for")
        if phase == "awaiting_direction":
            if waiting_for != "direction" or not _string(
                contract, "waiting_detail"
            ).strip():
                reasons.append(
                    "awaiting_direction 必须设置 waiting_for=direction 并记录 waiting_detail"
                )
        elif phase == "accepting":
            if waiting_for != "acceptance" or not _string(
                contract, "waiting_detail"
            ).strip():
                reasons.append(
                    "accepting 必须设置 waiting_for=acceptance 并记录 waiting_detail"
                )
        elif waiting_for != "none":
            reasons.append(f"{phase} phase 的 waiting_for 必须是 none")
        if phase == "blocked" and not _string(contract, "blocked_reason").strip():
            reasons.append("blocked phase 必须记录 blocked_reason")

        flag_keys = (
            "allow_new_artifacts",
            "allow_implementation_changes",
            "allow_external_writes",
            "allow_svn_commit",
        )
        for key, expected in zip(flag_keys, profile["flags"]):
            if contract.get(key) is not expected:
                reasons.append(f"{phase} phase 的 {key} 必须是 {str(expected).lower()}")

        if phase == "delivering":
            commit_paths = _strings(contract, "svn_commit_paths")
            carried_paths = set(_carried_changes(contract))
            if not commit_paths:
                reasons.append("delivering phase 必须记录 svn_commit_paths")
            for path in commit_paths:
                normalized = posixpath.normpath(path.replace("\\", "/"))
                if (
                    path.startswith(("/", "~"))
                    or ".." in path.split("/")
                    or normalized in {"", "."}
                    or normalized == ".svn"
                    or normalized.startswith(".svn/")
                    or any(token in path for token in ("*", "?", "["))
                ):
                    reasons.append(f"svn_commit_paths 必须是精确项目相对路径：{path}")
            if len(set(commit_paths)) != len(commit_paths):
                reasons.append("svn_commit_paths 不得重复")
            missing_carried = sorted(set(commit_paths) - STATE_FILES - carried_paths)
            if missing_carried:
                reasons.append(
                    "svn_commit_paths 必须来自已冻结的 carried_changes："
                    + ", ".join(missing_carried)
                )
            if not _string(contract, "svn_commit_evidence").strip():
                reasons.append("delivering phase 必须记录 svn_commit_evidence")

    return reasons


def validate_project_contract(
    project_root: Path,
    contract: dict[str, object],
    status_xml: str | None = None,
) -> list[str]:
    """Validate the phase contract together with its active graph node."""

    reasons = validate_contract(contract)
    reasons.extend(_spec_identity_reasons(project_root, contract))
    phase = _string(contract, "phase")
    confirmation = _string(contract, "goal_confirmation")
    digest = _string(contract, "goal_definition_digest")
    if confirmation == "pending":
        if digest:
            reasons.append("未确认 Goal 的 goal_definition_digest 必须为空")
    elif confirmation == "confirmed":
        try:
            expected_digest = goal_definition_digest(project_root, contract)
            reasons.extend(_goal_completeness(project_root))
        except (OSError, PolicyError) as error:
            reasons.append(f"Goal 确认内容无法校验：{error}")
        else:
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                reasons.append("已确认 Goal 必须记录有效 goal_definition_digest")
            elif digest != expected_digest:
                reasons.append(
                    "Goal 定义已在用户确认后变化；必须清空确认并返回 clarifying"
                )
    if not reasons and phase in {"closed", "delivering"}:
        reasons.extend(
            _success_exit_reasons(project_root, contract, status_xml=status_xml)
        )
    if reasons or phase not in {"implementing", "inspecting"}:
        return reasons
    try:
        graph = load_graph(project_root)
    except GraphLoadError as error:
        return reasons + [str(error)]
    reasons.extend(validate_graph(graph))
    active_task = _string(contract, "active_task")
    task = next((candidate for candidate in graph.tasks if candidate.id == active_task), None)
    if task is None:
        reasons.append(f"active_task 不存在于工作图：{active_task or '空'}")
        return reasons
    required_statuses = (
        {"working", "review"}
        if phase == "implementing"
        else {"review", "done"}
    )
    if task.status not in required_statuses:
        reasons.append(
            f"{phase} phase 的 active_task {active_task} 必须处于 "
            + " 或 ".join(sorted(required_statuses))
        )
    tasks_by_id = {candidate.id: candidate for candidate in graph.tasks}
    unfinished_dependencies = [
        dependency
        for dependency in task.dependencies
        if dependency not in tasks_by_id or tasks_by_id[dependency].status != "done"
    ]
    if unfinished_dependencies:
        reasons.append(
            f"active_task {active_task} 仍有未完成依赖：{', '.join(unfinished_dependencies)}"
        )
    open_blockers = [
        issue.id
        for issue in graph.issues
        if issue.severity == "blocker"
        and issue.status != "closed"
        and (
            active_task in issue.task_ids
            or bool(set(task.acceptance_ids) & set(issue.acceptance_ids))
        )
    ]
    if open_blockers:
        reasons.append(
            f"active_task {active_task} 被未关闭 blocker 阻断：{', '.join(open_blockers)}"
        )
    return reasons


def load_contract(project_root: Path) -> dict[str, object]:
    goal_path = project_root / STATE_DIR / "goal.md"
    if not goal_path.exists():
        raise PolicyError("缺少 docs/wali-0x3/goal.md")
    return dict(parse_frontmatter(goal_path.read_text(encoding="utf-8")))


def _run_check(project_root: Path) -> int:
    try:
        contract = load_contract(project_root)
    except PolicyError as error:
        print(f"WALI 阶段契约检查未通过：\n- {error}")
        return 1
    reasons = validate_project_contract(project_root, contract)
    if reasons:
        print("WALI 阶段契约检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    print("WALI 阶段契约检查通过。")
    return 0


def _run_digest(project_root: Path) -> int:
    try:
        contract = load_contract(project_root)
        digest = goal_definition_digest(project_root, contract)
    except (OSError, PolicyError) as error:
        print(f"WALI Goal 摘要生成失败：\n- {error}")
        return 1
    print(digest)
    return 0


def _run_handoff_digest(project_root: Path, status_xml_path: Path | None) -> int:
    try:
        contract = load_contract(project_root)
        status_xml = (
            _load_status_xml(project_root, status_xml_path)
            if status_xml_path is not None
            else None
        )
        digest = handoff_state_digest(project_root, contract, status_xml)
    except (OSError, PolicyError) as error:
        print(f"WALI 交接摘要生成失败：\n- {error}")
        return 1
    print(digest)
    return 0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    requires_user_confirmation: bool = False


def _relative_path(project_root: Path, raw_path: str) -> str | None:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def _scope_matches(path: str, scope: str) -> bool:
    normalized_scope = posixpath.normpath(scope.replace("\\", "/"))
    if normalized_scope == path:
        return True
    if not any(token in normalized_scope for token in ("*", "?", "[")):
        return path.startswith(normalized_scope.rstrip("/") + "/")
    return fnmatch.fnmatchcase(path, normalized_scope)


def _effective_scopes(
    project_root: Path, contract: dict[str, object]
) -> tuple[str, ...]:
    declared = _strings(contract, "write_scope")
    expanded: list[str] = []
    for scope in declared:
        if scope == "@active_task":
            active_task = _string(contract, "active_task")
            try:
                graph = load_graph(project_root)
            except GraphLoadError as error:
                raise PolicyError(f"无法解析 active_task 范围：{error}") from error
            task = next((candidate for candidate in graph.tasks if candidate.id == active_task), None)
            if task is None:
                raise PolicyError(f"active_task 不存在：{active_task or '空'}")
            if not task.scopes:
                raise PolicyError(f"active_task {active_task} 没有明确允许修改范围")
            expanded.extend(task.scopes)
        elif scope == "@svn_commit":
            commit_paths = _strings(contract, "svn_commit_paths")
            if not commit_paths:
                raise PolicyError("@svn_commit 缺少 svn_commit_paths")
            expanded.extend(commit_paths)
        else:
            expanded.append(scope)
    return tuple(expanded)


def _write_effect(path: str, phase: str) -> str:
    if (
        path == "CLAUDE.md"
        or path == ".claude"
        or path.startswith(".claude/")
        or path == "claude"
        or path.startswith("claude/")
        or path == ".svn"
        or path.startswith(".svn/")
    ):
        return "modify_control_plane"
    if path == "docs/wali-0x3/goal.md":
        if phase == "clarifying":
            return "update_goal_draft"
        if phase in {
            "implementing",
            "inspecting",
            "delivering",
            "closed",
            "terminated",
        }:
            return "transition_phase"
        return "update_goal"
    if path == "docs/wali-0x3/spec.md":
        return "update_spec_draft"
    if path == "docs/wali-0x3/todo.md":
        return "update_todo"
    if path == "docs/wali-0x3/issues.md":
        return "update_issues"
    if path == "docs/wali-0x3/handoff.md":
        return "update_handoff"
    return "modify_implementation"


def _capability_name(tool_name: str, tool_input: dict[str, object]) -> str:
    if tool_name == "Skill":
        name = tool_input.get("skill") or tool_input.get("name")
    else:
        name = tool_input.get("subagent_type") or tool_input.get("name")
    return str(name or "").strip()


def _capability_definition(
    project_root: Path, tool_name: str, name: str
) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return None
    candidates = (
        (
            project_root / ".claude" / "skills" / name / "SKILL.md",
            project_root / "claude" / "skills" / name / "SKILL.md",
        )
        if tool_name == "Skill"
        else (
            project_root / ".claude" / "agents" / f"{name}.md",
            project_root / "claude" / "agents" / f"{name}.md",
        )
    )
    for candidate in candidates:
        if candidate.is_file() and _relative_path(project_root, str(candidate)) is not None:
            return candidate
    return None


def _capability_is_declarative(path: Path, tool_name: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    frontmatter_match = re.match(r"\A---\s*\n(.*?)\n---", text, flags=re.DOTALL)
    if frontmatter_match is None:
        return False
    frontmatter_text = frontmatter_match.group(1)
    keys: list[str] = []
    for line in frontmatter_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            return False
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*.+$", line)
        if match is None:
            return False
        keys.append(match.group(1))
    allowed_keys = (
        {
            "name",
            "description",
            "argument-hint",
            "disable-model-invocation",
            "user-invocable",
        }
        if tool_name == "Skill"
        else {
            "name",
            "description",
            "tools",
            "model",
            "effort",
            "color",
            "permissionMode",
        }
    )
    if len(keys) != len(set(keys)) or set(keys) - allowed_keys:
        return False
    if tool_name == "Skill" and not re.search(
        r"(?mi)^disable-model-invocation\s*:\s*true\s*$", frontmatter_text
    ):
        return False
    permission_match = re.search(
        r"(?mi)^permissionMode\s*:\s*([^\s#]+)", frontmatter_text
    )
    if permission_match and permission_match.group(1) != "default":
        return False
    effort_match = re.search(r"(?mi)^effort\s*:\s*([^\s#]+)", frontmatter_text)
    if effort_match and effort_match.group(1) not in {
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }:
        return False
    # Claude Skills can execute !`shell commands` while loading. These bypass
    # the later Bash tool decision and are therefore never treated as pure.
    if re.search(r"!\s*`", text) or re.search(r"(?m)^\s*`{3,}!", text):
        return False
    return True


def _prospective_goal_text(
    project_root: Path, tool_name: str, tool_input: dict[str, object]
) -> str | None:
    goal_path = project_root / STATE_DIR / "goal.md"
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    try:
        text = goal_path.read_text(encoding="utf-8")
    except OSError:
        return None
    edits: list[dict[str, object]]
    if tool_name == "Edit":
        edits = [tool_input]
    elif tool_name == "MultiEdit" and isinstance(tool_input.get("edits"), list):
        edits = [edit for edit in tool_input["edits"] if isinstance(edit, dict)]
    else:
        return None
    if not edits:
        return None
    for edit in edits:
        old = str(edit.get("old_string", ""))
        new = str(edit.get("new_string", ""))
        replace_all = bool(edit.get("replace_all", False))
        count = text.count(old) if old else 0
        if not old or count == 0 or (count != 1 and not replace_all):
            return None
        text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    return text


def _argument_escapes_workspace(argument: str, project_root: Path) -> bool:
    if argument.startswith("-") and "=" in argument:
        option_value = argument.split("=", 1)[1]
        normalized_value = option_value.replace("\\", "/")
        if (
            option_value.startswith(("~", "$", "${", "file:", "http:", "https:", "svn:", "^/"))
            or Path(option_value).is_absolute()
            or ".." in normalized_value.split("/")
            or _relative_path(project_root, option_value) is None
        ):
            return True
    if argument.startswith(("~", "$", "${", "file:", "http:", "https:", "svn:", "^/")):
        return True
    normalized = argument.replace("\\", "/")
    if ".." in normalized.split("/"):
        return True
    if Path(argument).is_absolute():
        return _relative_path(project_root, argument) is None
    return _relative_path(project_root, argument) is None


def _has_unquoted_shell_expansion(command: str) -> bool:
    quote = ""
    for character in command:
        if quote == "'":
            if character == "'":
                quote = ""
            continue
        if quote == '"':
            if character == '"':
                quote = ""
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character == "\\" or character in "{}*?[]()":
            return True
    return False


def _wali_read_only_command(arguments: list[str], project_root: Path) -> bool:
    if len(arguments) < 2 or not Path(arguments[0]).name.startswith("python"):
        return False
    script = posixpath.normpath(arguments[1].replace("\\", "/"))
    permitted_scripts = {
        ".claude/hooks/wali-doctor.py",
        "claude/hooks/wali-doctor.py",
        ".claude/hooks/wali_policy.py",
        "claude/hooks/wali_policy.py",
        ".claude/hooks/wali_graph.py",
        "claude/hooks/wali_graph.py",
        ".claude/hooks/wali_stop.py",
        "claude/hooks/wali_stop.py",
        ".claude/hooks/wali_supervision.py",
        "claude/hooks/wali_supervision.py",
    }
    if script not in permitted_scripts:
        return False
    script_name = Path(script).name
    remaining = arguments[2:]
    if remaining[:2] == ["--project-root", "."]:
        remaining = remaining[2:]
    elif remaining[:1] == ["--project-root=."]:
        remaining = remaining[1:]
    if any(argument.startswith("--project-root") for argument in remaining):
        return False
    if script_name == "wali_policy.py":
        return len(remaining) == 1 and remaining[0] in {
            "check",
            "audit",
            "baseline",
            "carry",
            "digest",
            "handoff-digest",
        }
    if script_name == "wali_graph.py":
        return len(remaining) == 1 and remaining[0] in {
            "check",
            "frontier",
            "parallel",
            "mermaid",
        }
    if script_name == "wali_supervision.py":
        return remaining == ["status"]
    return not remaining


def _svn_read_only_command(arguments: list[str]) -> bool:
    if len(arguments) < 2 or arguments[0] != "svn":
        return False
    command = arguments[1].lower()
    if command not in {
        "info",
        "status",
        "st",
        "diff",
        "di",
        "log",
        "list",
        "ls",
        "cat",
        "blame",
        "proplist",
        "propget",
    }:
        return False
    no_value_options = {
        "--force",
        "--ignore-ancestry",
        "--ignore-externals",
        "--ignore-keywords",
        "--include-externals",
        "--incremental",
        "--internal-diff",
        "--no-ignore",
        "--notice-ancestry",
        "--patch-compatible",
        "--properties-only",
        "--quiet",
        "--recursive",
        "--show-inherited-props",
        "--show-updates",
        "--stop-on-copy",
        "--strict",
        "--summarize",
        "--use-merge-history",
        "--verbose",
        "--with-all-revprops",
        "--with-no-revprops",
        "--xml",
        "-g",
        "-q",
        "-R",
        "-u",
        "-v",
    }
    value_options = {
        "--change",
        "--changelist",
        "--depth",
        "--encoding",
        "--limit",
        "--revision",
        "--revprop",
        "--search",
        "--search-and",
        "--show-item",
        "--with-revprop",
        "-c",
        "-l",
        "-r",
    }
    index = 2
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            break
        if argument.startswith("--") and "=" in argument:
            option, value = argument.split("=", 1)
            if option not in value_options or not value:
                return False
        elif argument in no_value_options:
            pass
        elif argument in value_options:
            index += 1
            if index >= len(arguments) or not arguments[index]:
                return False
        elif argument.startswith("-"):
            return False
        index += 1
    if command in {"diff", "di"} and "--internal-diff" not in arguments[2:]:
        return False
    return True


def _read_only_bash(command: str, project_root: Path) -> bool:
    if not command.strip() or any(
        token in command
        for token in ("\n", "\r", ";", "&", "||", "|", ">", "<", "`", "$", "$(", "\\")
    ) or _has_unquoted_shell_expansion(command):
        return False
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    if not arguments or "=" in arguments[0]:
        return False
    if any(_argument_escapes_workspace(argument, project_root) for argument in arguments[1:]):
        return False

    if arguments[0] != Path(arguments[0]).name:
        return False
    program = arguments[0]
    if _wali_read_only_command(arguments, project_root):
        return True
    if program == "svn":
        return _svn_read_only_command(arguments)
    return program == "pwd" and len(arguments) == 1


def _bash_escapes_workspace(command: str, project_root: Path) -> bool:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    return any(
        _argument_escapes_workspace(argument, project_root) for argument in arguments[1:]
    )


def _contains_svn_commit(command: str) -> bool:
    return bool(
        re.search(
            r"(?:^|[;&|]\s*)(?:[^\s;&|]*/)?svn\s+(?:commit|ci)(?:\s|$)",
            command,
            flags=re.IGNORECASE,
        )
    )


def _unsafe_shell_syntax(command: str) -> bool:
    return any(
        token in command
        for token in ("\n", "\r", ";", "&", "|", ">", "<", "`", "$", "$(")
    )


def _svn_mutating_command(command: str) -> bool:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return True
    if len(arguments) < 2 or Path(arguments[0]).name != "svn":
        return False
    return arguments[1].lower() in {
        "add",
        "changelist",
        "cleanup",
        "copy",
        "cp",
        "delete",
        "del",
        "import",
        "lock",
        "merge",
        "mkdir",
        "move",
        "mv",
        "patch",
        "propdel",
        "propset",
        "relocate",
        "resolve",
        "resolved",
        "revert",
        "switch",
        "unlock",
        "update",
        "up",
    }


def _svn_commit_targets(project_root: Path, command: str) -> tuple[str, ...] | None:
    if any(
        token in command
        for token in ("\n", "\r", ";", "&", "|", ">", "<", "`", "$", "$(")
    ):
        return None
    try:
        arguments = shlex.split(command)
    except ValueError:
        return None
    if not (
        len(arguments) >= 6
        and arguments[0] == "svn"
        and arguments[1].lower() in {"commit", "ci"}
        and arguments[2] in {"-m", "--message"}
        and bool(arguments[3].strip())
        and arguments[4] == "--"
    ):
        return None
    raw_targets = arguments[5:]
    if not raw_targets:
        return None
    targets: list[str] = []
    for raw_target in raw_targets:
        if raw_target.startswith(
            ("~", "$", "file:", "http:", "https:", "svn:", "^/")
        ):
            return None
        if Path(raw_target).is_absolute() or ".." in raw_target.replace(
            "\\", "/"
        ).split("/"):
            return None
        relative = _relative_path(project_root, raw_target)
        if relative is None or relative in {"", "."}:
            return None
        if (project_root / relative).is_dir() or raw_target.endswith(("/", "\\")):
            return None
        targets.append(relative)
    return tuple(targets)


def _svn_node_kind(project_root: Path, path: str) -> str | None:
    try:
        result = subprocess.run(
            ["svn", "info", "--show-item", "kind", "--", path],
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    kind = result.stdout.strip().lower()
    return kind if result.returncode == 0 and kind else None


def _svn_working_copy_root(project_root: Path) -> Path | None:
    """Translate the shared SVN boundary error into a policy error."""
    try:
        return discover_working_copy_root(project_root)
    except SvnBoundaryError as error:
        raise PolicyError(str(error)) from error


def _exact_svn_paths(
    project_root: Path, raw_targets: list[str], *, allow_missing: bool = True
) -> tuple[str, ...] | None:
    if not raw_targets:
        return None
    targets: list[str] = []
    for raw_target in raw_targets:
        if raw_target.startswith(
            ("~", "$", "file:", "http:", "https:", "svn:", "^/")
        ):
            return None
        if Path(raw_target).is_absolute() or ".." in raw_target.replace(
            "\\", "/"
        ).split("/"):
            return None
        relative = _relative_path(project_root, raw_target)
        if relative is None or relative in {"", "."}:
            return None
        path = project_root / relative
        if path.is_dir() or raw_target.endswith(("/", "\\")):
            return None
        if not allow_missing and not (path.is_file() or path.is_symlink()):
            return None
        targets.append(relative)
    if len(set(targets)) != len(targets):
        return None
    return tuple(targets)


def _svn_schedule_targets(
    project_root: Path, command: str
) -> tuple[str, tuple[str, ...]] | None:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return None
    if len(arguments) < 4 or arguments[0] != "svn":
        return None
    operation = arguments[1].lower()
    if operation == "add" and arguments[2] == "--":
        targets = _exact_svn_paths(
            project_root, arguments[3:], allow_missing=False
        )
    elif operation in {"delete", "del"}:
        start = 3 if arguments[2] == "--" else 4
        if start == 4 and not (
            len(arguments) >= 5
            and arguments[2] == "--force"
            and arguments[3] == "--"
        ):
            return None
        targets = _exact_svn_paths(
            project_root, arguments[start:], allow_missing=False
        )
        operation = "delete"
    elif operation in {"move", "mv", "copy", "cp"} and len(arguments) == 5:
        if arguments[2] != "--":
            return None
        targets = _exact_svn_paths(project_root, arguments[3:])
        operation = "move" if operation in {"move", "mv"} else "copy"
        if targets is not None:
            source, destination = (project_root / target for target in targets)
            if not (source.is_file() or source.is_symlink()) or destination.exists():
                return None
    else:
        return None
    return (operation, targets) if targets is not None else None


def _svn_sync_targets(
    project_root: Path, command: str
) -> tuple[str, tuple[str, ...]] | None:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return None
    if len(arguments) < 4 or arguments[0] != "svn":
        return None
    operation = arguments[1].lower()
    if operation in {"update", "up"} and arguments[2] == "--":
        targets = _exact_svn_paths(
            project_root, arguments[3:], allow_missing=False
        )
        return ("update", targets) if targets is not None else None
    if (
        operation in {"resolve", "resolved"}
        and len(arguments) >= 6
        and arguments[2:5] == ["--accept", "working", "--"]
    ):
        targets = _exact_svn_paths(
            project_root, arguments[5:], allow_missing=False
        )
        return ("resolve", targets) if targets is not None else None
    return None


def _declared_project_commands(project_root: Path) -> set[str]:
    goal_path = project_root / STATE_DIR / "goal.md"
    try:
        rows = table_rows(goal_path.read_text(encoding="utf-8"), "goal.md")
    except (OSError, TableParseError):
        return set()

    commands: set[str] = set()
    for row in rows:
        raw_command = row.get("命令或方法", "").strip()
        if len(raw_command) >= 2 and raw_command.startswith("`") and raw_command.endswith("`"):
            command = raw_command[1:-1].strip()
            if command:
                commands.add(command)
    return commands


def _looks_like_external_write(command: str) -> bool:
    """Conservatively identify common commands that mutate remote systems."""

    try:
        arguments = shlex.split(command)
    except ValueError:
        return True
    if not arguments:
        return False
    program = Path(arguments[0]).name.lower()
    lowered = [argument.lower() for argument in arguments[1:]]
    if program in {"scp", "sftp", "ssh", "ftp"}:
        return True
    if program == "curl":
        write_flags = {
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
            "-f",
            "--form",
            "-t",
            "--upload-file",
        }
        if any(argument in write_flags for argument in lowered):
            return True
        for index, argument in enumerate(lowered):
            if argument in {"-x", "--request"} and index + 1 < len(lowered):
                return lowered[index + 1] not in {"get", "head", "options"}
        return False
    if program in {"npm", "pnpm", "yarn"} and "publish" in lowered:
        return True
    if program == "docker" and lowered[:1] == ["push"]:
        return True
    if program == "kubectl" and lowered[:1] and lowered[0] in {
        "apply",
        "create",
        "delete",
        "patch",
        "replace",
        "rollout",
        "scale",
        "set",
    }:
        return True
    if program == "svn" and lowered[:1] and lowered[0] in {
        "commit",
        "ci",
        "copy",
        "cp",
        "delete",
        "del",
        "move",
        "mv",
        "mkdir",
        "propset",
        "propdel",
        "lock",
        "unlock",
    }:
        return True
    return False


def decide_tool(
    project_root: Path, contract: dict[str, object], payload: dict[str, object]
) -> Decision:
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return Decision(False, "tool_input 必须是对象")

    effects = set(_strings(contract, "allowed_effects"))
    phase = _string(contract, "phase")
    active_task_status = ""
    if phase == "implementing":
        try:
            graph = load_graph(project_root)
        except GraphLoadError:
            graph = None
        if graph is not None:
            active = next(
                (task for task in graph.tasks if task.id == _string(contract, "active_task")),
                None,
            )
            active_task_status = active.status if active is not None else ""
    if tool_name in {"Read", "Glob", "Grep"}:
        raw_path = str(
            tool_input.get("file_path")
            or tool_input.get("path")
            or project_root
        )
        if _relative_path(project_root, raw_path) is None:
            return Decision(False, f"读取路径不在工作区内：{raw_path}")
        pattern = str(tool_input.get("pattern", ""))
        glob_pattern = str(tool_input.get("glob", ""))
        for candidate in (pattern if tool_name == "Glob" else "", glob_pattern):
            if candidate and _argument_escapes_workspace(candidate, project_root):
                return Decision(False, f"读取模式可能超出工作区：{candidate}")
        if "read_workspace" in effects:
            return Decision(True)
        return Decision(False, f"{phase} phase 不允许读取工作区")
    if tool_name == "AskUserQuestion":
        if "ask_user" in effects:
            if phase in {"clarifying", "awaiting_direction"}:
                questions = tool_input.get("questions")
                if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
                    return Decision(
                        False,
                        f"{phase} 每轮必须集中询问 1–3 个最高影响问题",
                    )
            return Decision(True)
        return Decision(False, f"{phase} phase 不允许向用户提问")
    if tool_name in {"Skill", "Agent"}:
        if "read_workspace" not in effects:
            return Decision(False, f"{phase} phase 不允许调用能力")
        name = _capability_name(tool_name, tool_input)
        capability = f"{tool_name}:{name}"
        if capability not in set(_strings(contract, "allowed_capabilities")):
            return Decision(False, f"能力未列入 allowed_capabilities：{capability}")
        definition = _capability_definition(project_root, tool_name, name)
        if definition is None:
            return Decision(False, f"能力定义不在项目内或无法检查：{capability}")
        if not _capability_is_declarative(definition, tool_name):
            return Decision(
                False,
                f"能力包含 lifecycle hook、动态 shell 或绕过权限配置：{capability}",
            )
        return Decision(True)
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if _contains_svn_commit(command):
            if contract.get("allow_svn_commit") is not True:
                return Decision(False, "allow_svn_commit=false，禁止执行 SVN 提交")
            targets = _svn_commit_targets(project_root, command)
            authorized_targets = tuple(_strings(contract, "svn_commit_paths"))
            if targets is None:
                return Decision(
                    False,
                    "SVN 提交必须是独立命令，并在 -- 后列出与 svn_commit_paths 一致的精确项目相对路径",
                )
            if len(set(targets)) != len(targets) or set(targets) != set(
                authorized_targets
            ):
                return Decision(False, "SVN 提交目标必须与 svn_commit_paths 完全一致")
            if not is_verified_working_copy_root(project_root):
                return Decision(
                    False,
                    "SVN 提交前必须从可验证且可写的工作副本根启动项目",
                )
            live_status_xml = _status_xml_from_svn(project_root)
            reasons = audit_changes(
                project_root,
                contract,
                live_status_xml,
            )
            if reasons:
                return Decision(False, "SVN 提交前差异审计未通过：" + "；".join(reasons))
            changed_paths = {
                path for path, _item in _svn_changes(live_status_xml, project_root)
            }
            unchanged_targets = sorted(set(targets) - changed_paths)
            if unchanged_targets:
                return Decision(
                    False,
                    "SVN 提交目标必须全部是当前真实差异，禁止空提交或夹带清洁路径："
                    + ", ".join(unchanged_targets),
                )
            non_leaf_targets = sorted(
                path for path in targets if _svn_node_kind(project_root, path) != "file"
            )
            if non_leaf_targets:
                return Decision(
                    False,
                    "SVN 提交目标必须是可由 SVN 元数据证明的 leaf file："
                    + ", ".join(non_leaf_targets),
                )
            return Decision(
                True,
                "SVN 提交会写入共享仓库；请核对命令和精确路径后明确确认本次提交",
                True,
            )
        if _unsafe_shell_syntax(command):
            return Decision(False, "Bash 命令不得包含串联、管道、重定向、变量展开或命令替换")
        schedule = _svn_schedule_targets(project_root, command)
        sync = _svn_sync_targets(project_root, command)
        if schedule is not None or sync is not None:
            effect = "manage_svn_schedule" if schedule is not None else "sync_svn_working_copy"
            selected = schedule if schedule is not None else sync
            assert selected is not None
            operation, targets = selected
            if effect not in effects or phase != "implementing":
                return Decision(False, f"{phase} phase 不允许 {effect}")
            if active_task_status != "working":
                return Decision(False, "只有 working 状态的 active_task 可以变更 SVN 工作副本")
            try:
                scopes = tuple(
                    scope
                    for scope in _effective_scopes(project_root, contract)
                    if scope not in STATE_FILES
                )
            except PolicyError as error:
                return Decision(False, str(error))
            protected = set(_preexisting_changes(contract))
            invalid = [
                target
                for target in targets
                if target in protected
                or _write_effect(target, phase) == "modify_control_plane"
                or not any(_scope_matches(target, scope) for scope in scopes)
            ]
            if invalid:
                return Decision(
                    False,
                    f"SVN {operation} 目标超出 active_task 或命中用户保护基线："
                    + ", ".join(invalid),
                )
            return Decision(True)
        if _svn_mutating_command(command):
            return Decision(False, "SVN 工作副本变更不包含在当前命令权限中，需单独授权和转段")
        if (
            contract.get("allow_external_writes") is not True
            and _looks_like_external_write(command)
        ):
            return Decision(False, f"allow_external_writes=false，禁止外部写入：{command}")
        if _bash_escapes_workspace(command, project_root):
            return Decision(False, f"Bash 读写参数超出工作区：{command}")
        if "read_workspace" in effects and _read_only_bash(command, project_root):
            return Decision(True)
        if phase == "implementing" and active_task_status == "review":
            return Decision(False, "active_task 已处于 review，只能转入 inspecting 或更新交接")
        command_effect = (
            "run_checks" if "run_checks" in effects else "run_project_commands"
        )
        if command_effect not in effects:
            return Decision(False, f"{phase} phase 禁止此 Bash 命令：{command or '空'}")
        if command not in _declared_project_commands(project_root):
            return Decision(False, f"命令未在 goal.md 声明：{command or '空'}")
        return Decision(True)
    if tool_name in {"Edit", "Write", "NotebookEdit", "MultiEdit"}:
        raw_path = str(
            tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or tool_input.get("path")
            or ""
        )
        relative_path = _relative_path(project_root, raw_path)
        if not relative_path:
            return Decision(False, f"写入路径不在项目内：{raw_path or '空'}")
        effect = _write_effect(relative_path, phase)
        confirmation_reason = ""
        if relative_path == "docs/wali-0x3/goal.md":
            prospective_text = _prospective_goal_text(
                project_root, tool_name, tool_input
            )
            if prospective_text is None:
                return Decision(False, "goal.md 修改必须提供可前瞻校验的精确内容")
            try:
                spec_text = (project_root / STATE_DIR / "spec.md").read_text(
                    encoding="utf-8"
                )
            except OSError as error:
                return Decision(False, f"无法读取固定规格文档 spec.md：{error}")
            try:
                prospective_contract = dict(parse_frontmatter(prospective_text))
            except PolicyError as error:
                return Decision(False, f"修改后的阶段契约无效：{error}")
            prospective_reasons = validate_contract(prospective_contract)
            if prospective_reasons:
                return Decision(
                    False, "修改后的阶段契约无效：" + "；".join(prospective_reasons)
                )
            prospective_phase = _string(prospective_contract, "phase")
            allowed_transitions = PHASE_TRANSITIONS.get(phase, {phase})
            if prospective_phase not in allowed_transitions:
                return Decision(
                    False,
                    f"不允许从 {phase} 直接转入 {prospective_phase}；必须经过定义的阶段闭环",
                )
            delivery_state = ""
            if phase == "delivering" and prospective_phase != "delivering":
                try:
                    delivery_state = _delivery_transition_state(project_root, contract)
                except PolicyError as error:
                    return Decision(False, f"无法判定交付是否已冻结：{error}")
                if delivery_state == "unproven_clean" and prospective_phase == "clarifying":
                    return Decision(
                        False,
                        "SVN 授权路径已清洁但缺少有效交付回执；不得复活原 Goal，必须查明后受确认进入 terminated",
                    )
                if delivery_state in {"precommit", "unavailable"} and prospective_phase == "clarifying":
                    if _string(prospective_contract, "goal_id") != _string(contract, "goal_id"):
                        return Decision(False, "未完成交付不得直接换用新 Goal ID；必须先回到原 Goal 或进入 terminated")
                    if "svn_commit_paths" in prospective_contract or _string(
                        prospective_contract, "svn_commit_evidence"
                    ):
                        return Decision(
                            False,
                            "撤销交付准备并返回 clarifying 时必须清除 svn_commit_paths 和 svn_commit_evidence",
                        )
                    confirmation_reason = (
                        "即将撤销当前交付准备并返回原 Goal 的 clarifying；请核对未提交差异和撤销原因后明确确认"
                    )
            terminal_origin = phase in {"closed", "terminated"} or (
                phase == "delivering" and delivery_state == "completed"
            )
            if terminal_origin:
                if prospective_phase != "clarifying":
                    return Decision(False, f"{phase} 终态只允许以新 Goal 重置到 clarifying")
                current_goal_id = _string(contract, "goal_id")
                next_goal_id = _string(prospective_contract, "goal_id")
                if next_goal_id == current_goal_id:
                    return Decision(False, "终态之后开始新工作必须使用不同的 Goal ID")
                if (
                    phase == "terminated"
                    and _string(contract, "exit_outcome") == "superseded"
                    and next_goal_id != _string(contract, "superseded_by")
                ):
                    return Decision(
                        False,
                        "superseded 退出后的新 Goal ID 必须与 superseded_by 一致",
                    )
                reset_reasons = _new_goal_reset_reasons(
                    project_root, prospective_contract
                )
                if reset_reasons:
                    return Decision(
                        False,
                        "新 Goal 必须建立全新治理代次：" + "；".join(reset_reasons),
                    )
                confirmation_reason = (
                    f"即将结束 {current_goal_id} 的冻结状态并以 {next_goal_id} 开始新 Goal；请核对新 Goal ID 和 clarifying 最小权限后明确确认"
                )
            if (
                _string(contract, "goal_confirmation") == "pending"
                and _string(prospective_contract, "goal_confirmation") == "confirmed"
            ):
                if prospective_phase != "planning":
                    return Decision(False, "Goal 确认后必须先进入 planning")
                completeness_reasons = _goal_completeness_from_text(
                    prospective_text
                ) + _spec_completeness_from_text(spec_text, prospective_text)
                prospective_digest = _goal_definition_digest_from_text(
                    prospective_text, prospective_contract, spec_text
                )
                if completeness_reasons:
                    return Decision(
                        False,
                        "Goal + Spec 联合确认包尚不完整："
                        + "；".join(completeness_reasons),
                    )
                if _string(prospective_contract, "goal_definition_digest") != prospective_digest:
                    return Decision(
                        False,
                        "Goal 确认前必须写入与当前确认包一致的 goal_definition_digest",
                    )
                confirmation_reason = (
                    "即将共同确认当前 Goal 与 Spec 并开放 planning；请核对完整确认包后明确确认"
                )
            if phase == "accepting" and prospective_phase in {"delivering", "closed"}:
                success_reasons = _success_exit_reasons(
                    project_root,
                    prospective_contract,
                    goal_text=prospective_text,
                )
                if success_reasons:
                    return Decision(
                        False,
                        "成功收尾条件未满足：" + "；".join(success_reasons),
                    )
                confirmation_reason = (
                    "即将记录用户业务验收并进入终态；请核对验收结果后明确确认"
                )
            if phase != "terminated" and prospective_phase == "terminated":
                try:
                    svn_root = _svn_working_copy_root(project_root)
                except PolicyError as error:
                    return Decision(False, f"无法验证退出时的工作副本边界：{error}")
                if svn_root is not None:
                    if svn_root != project_root.resolve():
                        return Decision(False, "退出前必须回到 SVN 工作副本根审计差异")
                    try:
                        exit_audit_reasons = audit_changes(
                            project_root,
                            prospective_contract,
                            _status_xml_from_svn(project_root),
                        )
                    except (OSError, PolicyError) as error:
                        return Decision(False, f"无法验证退出时的工作副本状态：{error}")
                    if exit_audit_reasons:
                        return Decision(
                            False,
                            "退出前必须先冻结或按用户授权处置当前差异："
                            + "；".join(exit_audit_reasons),
                        )
                confirmation_reason = (
                    "即将以非成功结果退出当前 Goal；请核对退出类型、原因、证据和未提交变更处置后明确确认"
                )
            if _string(contract, "goal_confirmation") == "confirmed":
                returns_to_clarifying = (
                    _string(prospective_contract, "phase") == "clarifying"
                    and _string(prospective_contract, "goal_confirmation") == "pending"
                    and not _string(prospective_contract, "goal_definition_digest")
                )
                if not returns_to_clarifying:
                    if _string(prospective_contract, "goal_confirmation_evidence") != _string(
                        contract, "goal_confirmation_evidence"
                    ):
                        return Decision(
                            False,
                            "已确认 Goal 的用户确认依据不得在后续阶段改写",
                        )
                    expected = _string(contract, "goal_definition_digest")
                    prospective_digest = _goal_definition_digest_from_text(
                        prospective_text, prospective_contract, spec_text
                    )
                    if (
                        _string(prospective_contract, "goal_definition_digest")
                        != expected
                        or prospective_digest != expected
                    ):
                        return Decision(
                            False,
                            "已确认 Goal 的稳定定义不得在转段时改变；请清空确认并返回 clarifying",
                        )
                    current_carried = _carried_changes(contract)
                    prospective_carried = _carried_changes(prospective_contract)
                    current_history = set(_strings(contract, "carried_history"))
                    prospective_history = set(
                        _strings(prospective_contract, "carried_history")
                    )
                    current_epoch = int(_string(contract, "carry_epoch"))
                    prospective_epoch = int(
                        _string(prospective_contract, "carry_epoch")
                    )
                    carry_changed = (
                        prospective_carried != current_carried
                        or prospective_history != current_history
                        or prospective_epoch != current_epoch
                    )
                    if carry_changed and phase != "implementing":
                        return Decision(
                            False,
                            "carry 代次只能在 implementing 中由实时 carry 结果更新",
                        )
                    if carry_changed:
                        expected_history = current_history | {
                            f"{current_epoch}::{path}::{fingerprint}"
                            for path, fingerprint in current_carried.items()
                        }
                        if prospective_epoch != current_epoch + 1:
                            return Decision(False, "carry_epoch 必须恰好递增一代")
                        if prospective_history != expected_history:
                            return Decision(
                                False,
                                "carried_history 必须完整保留旧记录并归档上一代 carry",
                            )
                        try:
                            task_scopes = tuple(
                                scope
                                for scope in _effective_scopes(project_root, contract)
                                if scope not in STATE_FILES
                            )
                            preexisting = set(_preexisting_changes(contract))
                            live_paths = {
                                path
                                for path, item in _svn_changes(
                                    _status_xml_from_svn(project_root), project_root
                                )
                                if path not in STATE_FILES
                                and path not in preexisting
                                and item != "external"
                            }
                        except (PolicyError, OSError) as error:
                            return Decision(False, f"无法验证 carry 结果：{error}")
                        invalid_paths = sorted(
                            path
                            for path in live_paths | set(prospective_carried)
                            if path not in live_paths
                            or path not in prospective_carried
                            or _path_fingerprint(project_root, path)
                            != prospective_carried.get(path)
                            or (
                                prospective_carried.get(path)
                                != current_carried.get(path)
                                and not any(
                                    _scope_matches(path, scope)
                                    for scope in task_scopes
                                )
                            )
                        )
                        if invalid_paths:
                            return Decision(
                                False,
                                "新一代 carried_changes 必须精确匹配当前 active_task 的实时 SVN 差异："
                                + ", ".join(invalid_paths),
                            )
        if effect == "modify_implementation" and contract.get("allow_implementation_changes") is not True:
            return Decision(False, f"{phase} phase 禁止修改实现：{relative_path}")
        if (
            effect == "modify_implementation"
            and phase == "implementing"
            and active_task_status == "review"
        ):
            return Decision(False, "active_task 已处于 review，禁止继续修改实现")
        if effect not in effects:
            return Decision(False, f"allowed_effects 不允许 {effect}：{relative_path}")
        try:
            effective_scopes = _effective_scopes(project_root, contract)
        except PolicyError as error:
            return Decision(False, str(error))
        if not any(_scope_matches(relative_path, scope) for scope in effective_scopes):
            return Decision(False, f"写入超出 write_scope：{relative_path}")
        if (
            contract.get("allow_new_artifacts") is not True
            and relative_path not in STATE_FILES
            and not (project_root / relative_path).exists()
        ):
            return Decision(False, f"禁止创建新产物：{relative_path}")
        return Decision(True, confirmation_reason, bool(confirmation_reason))
    return Decision(False, f"{phase} phase 未授权工具：{tool_name or '空'}")


def _repair_decision(project_root: Path, payload: dict[str, object]) -> Decision:
    """Permit only a prospective clarifying contract or Spec-identity repair."""

    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    if tool_name not in {"Edit", "Write"} or not isinstance(tool_input, dict):
        return Decision(False, "阶段契约无效；只允许修复 clarifying Goal 或与其绑定的 Spec 身份")
    raw_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    relative_path = _relative_path(project_root, raw_path)
    if relative_path not in {
        "docs/wali-0x3/goal.md",
        "docs/wali-0x3/spec.md",
    }:
        return Decision(False, "阶段契约无效；只允许修复 docs/wali-0x3/goal.md 或 spec.md 身份")
    target_path = project_root / relative_path
    if tool_name == "Write":
        prospective = str(tool_input.get("content", ""))
    else:
        try:
            current = target_path.read_text(encoding="utf-8")
        except OSError as error:
            return Decision(False, f"无法读取待修复文档：{error}")
        old = str(tool_input.get("old_string", ""))
        new = str(tool_input.get("new_string", ""))
        if not old or current.count(old) != 1:
            return Decision(False, "契约恢复 Edit 必须精确匹配一次 old_string")
        prospective = current.replace(old, new, 1)
    if relative_path == "docs/wali-0x3/spec.md":
        try:
            current_contract = load_contract(project_root)
            metadata = strict_frontmatter(prospective, "spec.md")
        except (PolicyError, GraphLoadError) as error:
            return Decision(False, f"修复后的 Spec 身份仍无效：{error}")
        if _string(current_contract, "phase") != "clarifying":
            return Decision(False, "Spec 身份恢复通道只在 clarifying 可用")
        goal_id = _string(current_contract, "goal_id")
        if metadata.get("goal_id", "") != goal_id or metadata.get(
            "spec_id", ""
        ) != f"SPEC-{goal_id}":
            return Decision(False, "修复后的 Spec ID 和 goal_id 必须与当前 Goal 一致")
        return Decision(True)
    try:
        prospective_contract = dict(parse_frontmatter(prospective))
    except PolicyError as error:
        return Decision(False, f"修复后的阶段契约仍无效：{error}")
    reasons = validate_contract(prospective_contract)
    if _string(prospective_contract, "phase") != "clarifying":
        reasons.append("恢复通道只能回到 clarifying phase")
    if reasons:
        return Decision(False, "修复后的阶段契约仍无效：" + "；".join(reasons))
    return Decision(True)


def _status_xml_from_svn(project_root: Path) -> str:
    """Translate the shared SVN status error into a policy error."""

    try:
        return read_status_xml(project_root)
    except SvnBoundaryError as error:
        raise PolicyError(str(error)) from error


def _svn_changes(status_xml: str, project_root: Path) -> list[tuple[str, str]]:
    try:
        return list(classify_status_xml(project_root, status_xml).auditable_changes)
    except SvnBoundaryError as error:
        raise PolicyError(str(error)) from error


def _path_fingerprint(project_root: Path, relative_path: str) -> str:
    path = project_root / relative_path
    digest = hashlib.sha256()
    if path.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.readlink(path).encode("utf-8"))
    elif path.is_file():
        digest.update(b"file\0")
        digest.update(path.read_bytes())
    elif path.is_dir():
        digest.update(b"directory\0")
        for child in sorted(path.rglob("*")):
            child_relative = child.relative_to(path).as_posix()
            digest.update(child_relative.encode("utf-8"))
            if child.is_symlink():
                digest.update(os.readlink(child).encode("utf-8"))
            elif child.is_file():
                digest.update(child.read_bytes())
    else:
        return "missing"

    if (project_root / ".svn").is_dir():
        try:
            properties = subprocess.run(
                ["svn", "proplist", "--xml", "-v", "--", relative_path],
                cwd=project_root,
                capture_output=True,
                check=False,
                text=False,
            )
        except OSError:
            properties = None
        if properties is not None and properties.returncode == 0:
            digest.update(b"\0svn-properties\0")
            digest.update(properties.stdout)
    return digest.hexdigest()


def handoff_state_digest(
    project_root: Path,
    contract: dict[str, object],
    status_xml: str | None = None,
) -> str:
    """Hash the complete resumable state, including normalized handoff text.

    ``stop_intent`` is deliberately excluded: an agent may refresh handoff.md
    and then switch that field to ``handoff`` without making the new snapshot
    stale. Only handoff's own ``state_digest`` value is excluded to avoid a
    circular hash; the remainder of both Goal and handoff is bound.
    """

    if status_xml is None:
        svn_root = _svn_working_copy_root(project_root)
        if svn_root is not None:
            if svn_root != project_root.resolve():
                raise PolicyError("handoff 摘要必须从 SVN 工作副本根生成")
            status_xml = _status_xml_from_svn(project_root)
    changes: list[dict[str, str]] = []
    delivering_paths = (
        set(_strings(contract, "svn_commit_paths"))
        if _string(contract, "phase") == "delivering"
        else set()
    )
    if status_xml is not None:
        for path, item in sorted(_svn_changes(status_xml, project_root)):
            if path in STATE_FILES:
                continue
            if path in delivering_paths:
                # The immutable carried_changes entry already captures the
                # authorized payload. Omitting its transient SVN status keeps
                # a pre-commit handoff snapshot valid after the exact commit.
                continue
            changes.append(
                {
                    "path": path,
                    "item": item,
                    "fingerprint": _path_fingerprint(project_root, path),
                }
            )
    goal_text = (project_root / STATE_DIR / "goal.md").read_text(encoding="utf-8")
    handoff_text = (project_root / STATE_DIR / "handoff.md").read_text(
        encoding="utf-8"
    )
    spec_text = (project_root / STATE_DIR / "spec.md").read_text(encoding="utf-8")
    goal_snapshot = re.sub(
        r"(?m)^stop_intent:\s*.*$", "stop_intent: <excluded>", goal_text
    ).replace("\r\n", "\n")
    handoff_snapshot = re.sub(
        r"(?m)^state_digest:\s*.*$", 'state_digest: ""', handoff_text
    ).replace("\r\n", "\n")
    canonical = {
        "goal_snapshot": goal_snapshot,
        "spec_snapshot": _normalized_spec_snapshot(spec_text),
        "handoff_snapshot": handoff_snapshot,
        "goal_id": _string(contract, "goal_id"),
        "status": _string(contract, "status"),
        "phase": _string(contract, "phase"),
        "active_task": _string(contract, "active_task"),
        "goal_confirmation": _string(contract, "goal_confirmation"),
        "goal_definition_digest": _string(contract, "goal_definition_digest"),
        "waiting_for": _string(contract, "waiting_for"),
        "waiting_detail": _string(contract, "waiting_detail"),
        "blocked_reason": _string(contract, "blocked_reason"),
        "exit_outcome": _string(contract, "exit_outcome"),
        "exit_reason": _string(contract, "exit_reason"),
        "exit_evidence": _string(contract, "exit_evidence"),
        "exit_change_disposition": _string(
            contract, "exit_change_disposition"
        ),
        "superseded_by": _string(contract, "superseded_by"),
        "preexisting_changes": sorted(_strings(contract, "preexisting_changes")),
        "carry_epoch": _string(contract, "carry_epoch"),
        "carried_history": sorted(_strings(contract, "carried_history")),
        "carried_changes": sorted(_strings(contract, "carried_changes")),
        "todo_fingerprint": _path_fingerprint(
            project_root, "docs/wali-0x3/todo.md"
        ),
        "issues_fingerprint": _path_fingerprint(
            project_root, "docs/wali-0x3/issues.md"
        ),
        "working_copy_changes": changes,
    }
    serialized = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _preexisting_changes(contract: dict[str, object]) -> dict[str, str]:
    baseline: dict[str, str] = {}
    for entry in _strings(contract, "preexisting_changes"):
        path, separator, fingerprint = entry.rpartition("::")
        if separator:
            baseline[posixpath.normpath(path.replace("\\", "/"))] = fingerprint
    return baseline


def _carried_changes(contract: dict[str, object]) -> dict[str, str]:
    carried: dict[str, str] = {}
    for entry in _strings(contract, "carried_changes"):
        path, separator, fingerprint = entry.rpartition("::")
        if separator:
            carried[posixpath.normpath(path.replace("\\", "/"))] = fingerprint
    return carried


def _fresh_preexisting_changes(project_root: Path) -> tuple[str, ...]:
    """Snapshot every existing non-governance WC difference for a new Goal."""

    svn_root = _svn_working_copy_root(project_root)
    if svn_root is None:
        return ()
    if svn_root != project_root.resolve():
        raise PolicyError("新 Goal 必须从 SVN 工作副本根建立保护基线")
    entries: list[str] = []
    for path, item in _svn_changes(_status_xml_from_svn(project_root), project_root):
        if path in STATE_FILES:
            continue
        if item == "external":
            raise PolicyError(f"SVN external 不能自动纳入新 Goal 保护基线：{path}")
        entries.append(f"{path}::{_path_fingerprint(project_root, path)}")
    return tuple(sorted(entries))


def _new_goal_reset_reasons(
    project_root: Path, prospective_contract: dict[str, object]
) -> list[str]:
    """Require a fresh governance epoch instead of inheriting old authority."""

    reasons: list[str] = []
    try:
        expected_baseline = _fresh_preexisting_changes(project_root)
    except PolicyError as error:
        return [str(error)]
    if tuple(sorted(_strings(prospective_contract, "preexisting_changes"))) != expected_baseline:
        reasons.append(
            "新 Goal 的 preexisting_changes 必须重建为当前全部非治理差异的保护基线"
        )
    if _string(prospective_contract, "carry_epoch") != "0":
        reasons.append("新 Goal 的 carry_epoch 必须重置为 0")
    if _strings(prospective_contract, "carried_history"):
        reasons.append("新 Goal 不得继承旧 Goal 的 carried_history")
    if _strings(prospective_contract, "carried_changes"):
        reasons.append("新 Goal 不得继承旧 Goal 的 carried_changes")
    if _strings(prospective_contract, "allowed_capabilities"):
        reasons.append(
            "新 Goal 的受确认重置不得继承旧 Goal 能力；进入 clarifying 后再显式声明"
        )
    if "svn_commit_paths" in prospective_contract or _string(
        prospective_contract, "svn_commit_evidence"
    ):
        reasons.append("新 Goal 不得继承旧 Goal 的 SVN 提交授权")
    return reasons


def _delivery_transition_state(
    project_root: Path, contract: dict[str, object]
) -> str:
    """Classify delivery as pre-commit, completed, or clean without proof."""

    svn_root = _svn_working_copy_root(project_root)
    if svn_root is None:
        return "unavailable"
    if svn_root != project_root.resolve():
        raise PolicyError("交付状态只能从 SVN 工作副本根转换")
    status_xml = _status_xml_from_svn(project_root)
    changed_paths = {path for path, _item in _svn_changes(status_xml, project_root)}
    if set(_strings(contract, "svn_commit_paths")) & changed_paths:
        return "precommit"
    if not delivery_completion_reasons(project_root, contract, status_xml):
        return "completed"
    return "unproven_clean"


def audit_changes(
    project_root: Path,
    contract: dict[str, object],
    status_xml: str,
) -> list[str]:
    reasons: list[str] = []
    try:
        scopes = _effective_scopes(project_root, contract)
        changes = _svn_changes(status_xml, project_root)
    except PolicyError as error:
        return [str(error)]

    phase = _string(contract, "phase")
    preexisting = _preexisting_changes(contract)
    carried = _carried_changes(contract)
    commit_paths = set(_strings(contract, "svn_commit_paths"))
    for path, item in changes:
        if path in preexisting:
            if _path_fingerprint(project_root, path) == preexisting[path]:
                continue
            reasons.append(f"用户既有修改在基线后发生变化：{path}")
            continue
        if phase == "delivering" and path not in commit_paths:
            reasons.append(f"交付差异未列入 svn_commit_paths：{path} ({item})")
            continue
        if path in STATE_FILES:
            # These files are the policy's own journal. Their write authority is
            # checked at PreToolUse; retaining their earlier diffs is expected.
            continue
        if item == "external":
            reasons.append(f"SVN external 不在当前项目授权边界内：{path}")
            continue
        current_fingerprint = _path_fingerprint(project_root, path)
        if path in carried:
            if current_fingerprint == carried[path]:
                continue
            if not (
                phase == "implementing"
                and contract.get("allow_implementation_changes") is True
                and any(_scope_matches(path, scope) for scope in scopes)
            ):
                reasons.append(f"阶段继承的修改在记录后发生变化：{path}")
                continue
        effect = _write_effect(path, phase)
        if not any(_scope_matches(path, scope) for scope in scopes):
            reasons.append(f"SVN 差异超出 write_scope：{path} ({item})")
        if (
            effect == "modify_implementation"
            and contract.get("allow_implementation_changes") is not True
            and not (phase == "delivering" and path in commit_paths)
        ):
            reasons.append(f"{phase} phase 出现未授权实现变更：{path} ({item})")
        if item in {"added", "replaced", "unversioned", "ignored"} and contract.get(
            "allow_new_artifacts"
        ) is not True and not (phase == "delivering" and path in commit_paths):
            reasons.append(f"allow_new_artifacts=false，发现新产物：{path} ({item})")
    return reasons


def _run_baseline(project_root: Path, status_xml_path: Path | None) -> int:
    try:
        status_xml = _load_status_xml(project_root, status_xml_path)
        changes = _svn_changes(status_xml, project_root)
    except PolicyError as error:
        print(f"WALI SVN 基线读取失败：\n- {error}")
        return 1
    try:
        scopes = _effective_scopes(project_root, load_contract(project_root))
    except PolicyError:
        scopes = ()
    print("preexisting_changes:")
    for path, _item in changes:
        if any(_scope_matches(path, scope) for scope in scopes):
            continue
        entry = f"{path}::{_path_fingerprint(project_root, path)}"
        print(f"  - {json.dumps(entry, ensure_ascii=False)}")
    return 0


def _run_carry(project_root: Path, status_xml_path: Path | None) -> int:
    """Emit immutable fingerprints for authorized work entering the next phase."""

    try:
        contract = load_contract(project_root)
        status_xml = _load_status_xml(project_root, status_xml_path)
    except PolicyError as error:
        print(f"WALI 阶段继承记录失败：\n- {error}")
        return 1
    reasons = validate_project_contract(project_root, contract) + audit_changes(
        project_root, contract, status_xml
    )
    if reasons:
        print("WALI 阶段继承记录失败：")
        for reason in reasons:
            print(f"- {reason}")
        return 1

    preexisting = _preexisting_changes(contract)
    try:
        changes = _svn_changes(status_xml, project_root)
    except PolicyError as error:
        print(f"WALI 阶段继承记录失败：\n- {error}")
        return 1
    current_epoch = int(_string(contract, "carry_epoch"))
    print(f"carry_epoch: {current_epoch + 1}")
    print("carried_history:")
    history = list(_strings(contract, "carried_history"))
    history.extend(
        f"{current_epoch}::{path}::{fingerprint}"
        for path, fingerprint in sorted(_carried_changes(contract).items())
    )
    for entry in sorted(history):
        print(f"  - {json.dumps(entry, ensure_ascii=False)}")
    print("carried_changes:")
    for path, item in changes:
        if path in STATE_FILES or path in preexisting:
            continue
        if item == "external":
            print(f"- SVN external 不能进入阶段继承记录：{path}")
            return 1
        entry = f"{path}::{_path_fingerprint(project_root, path)}"
        print(f"  - {json.dumps(entry, ensure_ascii=False)}")
    return 0


def _load_status_xml(project_root: Path, status_xml_path: Path | None) -> str:
    if status_xml_path is not None:
        try:
            return status_xml_path.read_text(encoding="utf-8")
        except OSError as error:
            raise PolicyError(f"无法读取 SVN status XML：{error}") from error
    svn_root = _svn_working_copy_root(project_root)
    if svn_root is None:
        raise PolicyError("当前目录不在可验证的 SVN 工作副本中")
    if svn_root != project_root.resolve() or not is_verified_working_copy_root(project_root):
        raise PolicyError("SVN 状态命令必须从可验证且可写的工作副本根运行")
    return _status_xml_from_svn(project_root)


def _run_audit(project_root: Path, status_xml_path: Path | None) -> int:
    try:
        contract = load_contract(project_root)
        status_xml = _load_status_xml(project_root, status_xml_path)
    except PolicyError as error:
        print(f"WALI SVN 差异审计未通过：\n- {error}")
        return 1
    reasons = validate_project_contract(project_root, contract) + audit_changes(
        project_root, contract, status_xml
    )
    if reasons:
        print("WALI SVN 差异审计未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    print("WALI SVN 差异审计通过。")
    return 0


def _snapshot_path(project_root: Path, payload: dict[str, object]) -> Path:
    raw_id = str(
        payload.get("tool_use_id")
        or payload.get("toolUseID")
        or payload.get("session_id")
        or "latest"
    )
    snapshot_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    return project_root / ".svn" / "wali-policy" / f"{snapshot_id}.json"


def _delivery_receipt_path(project_root: Path, contract: dict[str, object]) -> Path:
    goal_id = re.sub(r"[^A-Za-z0-9_-]", "_", _string(contract, "goal_id"))
    return project_root / ".svn" / "wali-policy" / f"delivery-{goal_id}.json"


def _delivery_authorization_digest(contract: dict[str, object]) -> str:
    commit_paths = sorted(_strings(contract, "svn_commit_paths"))
    carried = _carried_changes(contract)
    canonical = {
        "goal_id": _string(contract, "goal_id"),
        "goal_definition_digest": _string(contract, "goal_definition_digest"),
        "carry_epoch": _string(contract, "carry_epoch"),
        "carried_history": sorted(_strings(contract, "carried_history")),
        "paths": commit_paths,
        "carried_changes": {
            path: carried[path] for path in commit_paths if path in carried
        },
        "svn_commit_evidence": _string(contract, "svn_commit_evidence"),
    }
    serialized = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _svn_last_changed_revisions(
    project_root: Path, paths: tuple[str, ...]
) -> dict[str, str] | None:
    revisions: dict[str, str] = {}
    for path in paths:
        if _path_fingerprint(project_root, path) == "missing":
            continue
        try:
            result = subprocess.run(
                ["svn", "info", "--show-item", "last-changed-revision", "--", path],
                cwd=project_root,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:
            return None
        revision = result.stdout.strip()
        if result.returncode != 0 or not revision.isdigit():
            return None
        revisions[path] = revision
    return revisions


def _commit_revision_from_payload(payload: dict[str, object]) -> str | None:
    response = payload.get("tool_response")
    if not isinstance(response, dict):
        return None
    stdout = response.get("stdout")
    if not isinstance(stdout, str):
        return None
    matches = re.findall(
        r"(?im)(?:Committed revision|提交后的版本为|提交版本)\s*(\d+)\s*[.。]?",
        stdout,
    )
    return matches[-1] if len(matches) == 1 else None


def _record_delivery_receipt(
    project_root: Path,
    contract: dict[str, object],
    targets: tuple[str, ...],
    status_xml: str,
    precommit_proof: object,
    commit_revision: str | None,
) -> list[str]:
    changed_paths = {path for path, _item in _svn_changes(status_xml, project_root)}
    remaining = sorted(set(targets) & changed_paths)
    if remaining:
        return ["SVN 提交未成功完成，授权路径仍有工作副本差异：" + ", ".join(remaining)]
    if not commit_revision or not commit_revision.isdigit():
        return ["PostToolUse 未获得 SVN 成功提交输出中的唯一修订号"]
    if not isinstance(precommit_proof, dict) or set(precommit_proof) != set(targets):
        return ["缺少逐路径提交前差异快照，禁止生成交付回执"]
    carried = _carried_changes(contract)
    for target in targets:
        proof = precommit_proof.get(target)
        if not isinstance(proof, dict):
            return [f"提交前差异快照格式无效：{target}"]
        if proof.get("kind") != "file" or not str(proof.get("item", "")):
            return [f"提交前目标不是已证明的 leaf file 差异：{target}"]
        if target not in STATE_FILES and proof.get("fingerprint") != carried.get(target):
            return [f"提交前目标指纹与当前 carry 代次不一致：{target}"]
    current_fingerprints = {
        path: _path_fingerprint(project_root, path) for path in sorted(targets)
    }
    existing_targets = tuple(
        path for path in sorted(targets) if current_fingerprints[path] != "missing"
    )
    live_revisions = _svn_last_changed_revisions(project_root, existing_targets)
    if live_revisions is None or any(
        live_revisions.get(path) != commit_revision for path in existing_targets
    ):
        return ["提交后 leaf file 的 last-changed-revision 与本次提交修订号不一致"]
    revisions = {path: commit_revision for path in sorted(targets)}
    receipt_path = _delivery_receipt_path(project_root, contract)
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "goal_id": _string(contract, "goal_id"),
                    "paths": sorted(targets),
                    "authorization_digest": _delivery_authorization_digest(contract),
                    "commit_revision": commit_revision,
                    "precommit": precommit_proof,
                    "fingerprints": current_fingerprints,
                    "revisions": revisions,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        return [f"无法写入 SVN 本地交付回执：{error}"]
    return []


def delivery_completion_reasons(
    project_root: Path, contract: dict[str, object], status_xml: str
) -> list[str]:
    if _string(contract, "phase") != "delivering":
        return []
    commit_paths = set(_strings(contract, "svn_commit_paths"))
    try:
        changed_paths = {path for path, _item in _svn_changes(status_xml, project_root)}
    except PolicyError as error:
        return [str(error)]
    remaining = sorted(commit_paths & changed_paths)
    reasons: list[str] = []
    if remaining:
        reasons.append("交付尚未提交成功，授权路径仍有差异：" + ", ".join(remaining))
    receipt_path = _delivery_receipt_path(project_root, contract)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        reasons.append("缺少 SVN 提交成功后的本地交付回执")
        return reasons
    if not isinstance(receipt, dict):
        reasons.append("SVN 交付回执格式无效")
        return reasons
    if receipt.get("goal_id") != _string(contract, "goal_id"):
        reasons.append("SVN 交付回执的 goal_id 不匹配")
    if receipt.get("authorization_digest") != _delivery_authorization_digest(contract):
        reasons.append("SVN 交付回执与当前精确授权不匹配")
    receipt_paths = receipt.get("paths")
    if not isinstance(receipt_paths, list) or not all(
        isinstance(path, str) for path in receipt_paths
    ) or set(receipt_paths) != commit_paths:
        reasons.append("SVN 交付回执的路径清单与 svn_commit_paths 不匹配")
    revisions = receipt.get("revisions")
    commit_revision = receipt.get("commit_revision")
    if not isinstance(commit_revision, str) or not commit_revision.isdigit():
        reasons.append("SVN 交付回执缺少本次提交修订号")
    if (
        not isinstance(revisions, dict)
        or set(revisions) != commit_paths
        or not isinstance(commit_revision, str)
        or any(value != commit_revision for value in revisions.values())
    ):
        reasons.append("SVN 交付回执缺少逐路径有效修订号")
    precommit = receipt.get("precommit")
    carried = _carried_changes(contract)
    if not isinstance(precommit, dict) or set(precommit) != commit_paths:
        reasons.append("SVN 交付回执缺少逐路径提交前差异证据")
    else:
        for path in commit_paths:
            proof = precommit.get(path)
            if (
                not isinstance(proof, dict)
                or proof.get("kind") != "file"
                or not str(proof.get("item", ""))
                or (
                    path not in STATE_FILES
                    and proof.get("fingerprint") != carried.get(path)
                )
            ):
                reasons.append(f"SVN 交付回执的提交前证据无效：{path}")
    fingerprints = receipt.get("fingerprints")
    current_fingerprints = {
        path: _path_fingerprint(project_root, path) for path in commit_paths
    }
    if not isinstance(fingerprints, dict) or fingerprints != current_fingerprints:
        reasons.append("SVN 交付回执的文件指纹与当前工作副本不一致")
    existing_paths = tuple(
        sorted(path for path, value in current_fingerprints.items() if value != "missing")
    )
    if isinstance(commit_revision, str) and commit_revision.isdigit():
        live_revisions = _svn_last_changed_revisions(
            project_root, existing_paths
        )
        if live_revisions is None or any(
            live_revisions.get(path) != commit_revision for path in existing_paths
        ):
            reasons.append("SVN 交付回执的修订号与当前工作副本不一致")
    return reasons


def _protected_action_paths(
    project_root: Path, contract: dict[str, object]
) -> set[str]:
    receipt = _delivery_receipt_path(project_root, contract)
    relative_receipt = _relative_path(project_root, str(receipt))
    return STATE_FILES | ({relative_receipt} if relative_receipt else set())


def _save_action_snapshot(
    project_root: Path,
    payload: dict[str, object],
    contract: dict[str, object],
) -> bool:
    path = _snapshot_path(project_root, payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            relative: _path_fingerprint(project_root, relative)
            for relative in sorted(_protected_action_paths(project_root, contract))
        }
        delivery_precommit: dict[str, dict[str, str]] | None = None
        tool_input = payload.get("tool_input", {})
        command = (
            str(tool_input.get("command", ""))
            if isinstance(tool_input, dict) and payload.get("tool_name") == "Bash"
            else ""
        )
        commit_targets = _svn_commit_targets(project_root, command)
        if commit_targets is not None:
            changes = dict(
                _svn_changes(_status_xml_from_svn(project_root), project_root)
            )
            if set(commit_targets).issubset(changes):
                delivery_precommit = {
                    target: {
                        "item": changes[target],
                        "fingerprint": _path_fingerprint(project_root, target),
                        "kind": _svn_node_kind(project_root, target) or "unknown",
                    }
                    for target in commit_targets
                }
        path.write_text(
            json.dumps(
                {
                    "tool_name": str(payload.get("tool_name", "")),
                    "state": state,
                    "delivery_precommit": delivery_precommit,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return True
    except (OSError, PolicyError):
        return False


def _audit_action_snapshot(
    project_root: Path,
    payload: dict[str, object],
    contract: dict[str, object],
) -> list[str]:
    path = _snapshot_path(project_root, payload)
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["缺少当前工具动作的 WALI 状态前置快照"]
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    before = snapshot.get("state", {})
    if not isinstance(before, dict):
        return ["WALI 状态前置快照格式无效"]
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    allowed_state_path = ""
    if tool_name in {"Edit", "Write", "MultiEdit", "NotebookEdit"} and isinstance(
        tool_input, dict
    ):
        raw_path = str(
            tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or tool_input.get("path")
            or ""
        )
        allowed_state_path = _relative_path(project_root, raw_path) or ""
    reasons: list[str] = []
    for relative in sorted(_protected_action_paths(project_root, contract)):
        previous = before.get(relative)
        current = _path_fingerprint(project_root, relative)
        if previous != current and not (
            relative == allowed_state_path and relative in STATE_FILES
        ):
            reasons.append(
                f"工具 {tool_name or '未知'} 夹带修改了未声明的 WALI 受保护状态：{relative}"
            )
    return reasons


def _run_hook(project_root: Path) -> int:
    contract: dict[str, object] = {}
    try:
        payload = json.load(sys.stdin)
        contract = load_contract(project_root)
    except (json.JSONDecodeError, OSError, PolicyError) as error:
        if "payload" in locals() and isinstance(payload, dict):
            decision = _repair_decision(project_root, payload)
            if not decision.allowed and not decision.reason:
                decision = Decision(False, f"WALI 策略输入无效：{error}")
        else:
            decision = Decision(False, f"WALI 策略输入无效：{error}")
    else:
        reasons = validate_project_contract(project_root, contract)
        decision = (
            _repair_decision(project_root, payload)
            if reasons
            else decide_tool(project_root, contract, payload)
        )

    mutating_tool = str(payload.get("tool_name", "")) in {
        "Bash",
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
    }
    if decision.allowed and mutating_tool:
        try:
            svn_root = _svn_working_copy_root(project_root)
        except PolicyError as error:
            decision = Decision(False, f"无法确认 SVN 工作副本边界：{error}")
        else:
            if svn_root is not None and svn_root != project_root.resolve():
                decision = Decision(False, "WALI 动作必须从 SVN 工作副本根执行，不允许在普通子目录启动")
            elif svn_root is not None and not is_verified_working_copy_root(project_root):
                decision = Decision(False, "WALI 动作必须从可验证且可写的 SVN 工作副本根执行")
            elif svn_root is not None and not _save_action_snapshot(
                project_root, payload, contract
            ):
                decision = Decision(False, "无法保存 WALI 动作前快照，已在工具执行前拒绝")

    if not decision.allowed:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": decision.reason,
                    }
                },
                ensure_ascii=False,
            )
        )
    elif decision.requires_user_confirmation:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": decision.reason,
                    }
                },
                ensure_ascii=False,
            )
        )
    return 0


def _run_post_hook(project_root: Path, status_xml_path: Path | None) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise PolicyError("PostToolUse payload 必须是对象")
        contract = load_contract(project_root)
        supplied_status_xml = (
            _load_status_xml(project_root, status_xml_path)
            if status_xml_path is not None
            else None
        )
        reasons = validate_project_contract(
            project_root, contract, status_xml=supplied_status_xml
        )
        action_snapshot: dict[str, object] = {}
        svn_root = (
            project_root.resolve()
            if supplied_status_xml is not None and (project_root / ".svn").is_dir()
            else _svn_working_copy_root(project_root)
        )
        if svn_root is not None:
            if svn_root != project_root.resolve() or not is_verified_working_copy_root(project_root):
                reasons.append("当前目录不是可验证且可写的 SVN 工作副本根")
            try:
                raw_snapshot = json.loads(
                    _snapshot_path(project_root, payload).read_text(encoding="utf-8")
                )
                if isinstance(raw_snapshot, dict):
                    action_snapshot = raw_snapshot
            except (OSError, json.JSONDecodeError):
                action_snapshot = {}
            reasons.extend(_audit_action_snapshot(project_root, payload, contract))
        live_status_xml: str | None = None
        if supplied_status_xml is not None:
            live_status_xml = supplied_status_xml
        else:
            info = subprocess.run(
                ["svn", "info", "--show-item", "wc-root"],
                cwd=project_root,
                capture_output=True,
                check=False,
                text=True,
            )
            if info.returncode == 0:
                live_status_xml = _status_xml_from_svn(project_root)
        if live_status_xml is not None:
            reasons.extend(audit_changes(project_root, contract, live_status_xml))
        tool_input = payload.get("tool_input", {})
        command = (
            str(tool_input.get("command", ""))
            if isinstance(tool_input, dict) and payload.get("tool_name") == "Bash"
            else ""
        )
        commit_targets = _svn_commit_targets(project_root, command)
        if (
            not reasons
            and live_status_xml is not None
            and commit_targets is not None
            and _string(contract, "phase") == "delivering"
        ):
            reasons.extend(
                _record_delivery_receipt(
                    project_root,
                    contract,
                    commit_targets,
                    live_status_xml,
                    action_snapshot.get("delivery_precommit"),
                    _commit_revision_from_payload(payload),
                )
            )
    except (json.JSONDecodeError, OSError, PolicyError) as error:
        reasons = [f"WALI PostToolUse 检查失败：{error}"]
    if reasons:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "WALI 工具执行后检查未通过：\n- "
                    + "\n- ".join(reasons),
                },
                ensure_ascii=False,
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    parser.add_argument(
        "command",
        choices=(
            "check",
            "hook",
            "post-hook",
            "audit",
            "baseline",
            "carry",
            "digest",
            "handoff-digest",
        ),
    )
    parser.add_argument("--status-xml", type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "hook":
        return _run_hook(project_root)
    if args.command == "post-hook":
        return _run_post_hook(project_root, args.status_xml)
    if args.command == "audit":
        return _run_audit(project_root, args.status_xml)
    if args.command == "baseline":
        return _run_baseline(project_root, args.status_xml)
    if args.command == "carry":
        return _run_carry(project_root, args.status_xml)
    if args.command == "digest":
        return _run_digest(project_root)
    if args.command == "handoff-digest":
        return _run_handoff_digest(project_root, args.status_xml)
    return _run_check(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
