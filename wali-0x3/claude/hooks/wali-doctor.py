#!/usr/bin/env python3
"""Read-only deployment diagnostics for WALI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from wali_graph import GraphLoadError, load_graph, validate_graph
from wali_policy import PolicyError, load_contract, validate_project_contract
from wali_svn import (
    SvnBoundaryError,
    classify_status_xml,
    discover_working_copy_root,
    read_status_xml,
)


CORE_PATHS = (
    "CLAUDE.md",
    ".claude/settings.json",
    ".claude/agents/architect.md",
    ".claude/agents/coordinator.md",
    ".claude/agents/developer.md",
    ".claude/agents/reviewer.md",
    ".claude/agents/tester.md",
    ".claude/hooks/wali-doctor.py",
    ".claude/hooks/wali_graph.py",
    ".claude/hooks/wali_policy.py",
    ".claude/hooks/wali_stop.py",
    ".claude/hooks/wali_supervision.py",
    ".claude/hooks/wali_svn.py",
    ".claude/refs/INDEX.md",
    ".claude/refs/compliance/INDEX.md",
    ".claude/refs/compatibility.md",
    ".claude/refs/operations.md",
    ".claude/refs/templates/INDEX.md",
    ".claude/rules/engineering.md",
    ".claude/rules/testing.md",
    ".claude/skills/wali-handoff/SKILL.md",
    ".claude/skills/wali-inspect/SKILL.md",
    ".claude/skills/wali-resume/SKILL.md",
    ".claude/skills/wali-start/SKILL.md",
    "docs/wali-0x3/goal.md",
    "docs/wali-0x3/handoff.md",
    "docs/wali-0x3/issues.md",
    "docs/wali-0x3/spec.md",
    "docs/wali-0x3/todo.md",
)
REQUIRED_HOOKS = {
    "PreToolUse": (
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/wali_policy.py",
        "hook",
    ),
    "PostToolUse": (
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/wali_policy.py",
        "post-hook",
    ),
    "Stop": (
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/wali_stop.py",
        "--hook",
    ),
}
SUPERVISION_HOOKS = {
    event: (
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/wali_supervision.py",
        "hook",
    )
    for event in ("TeammateIdle", "TaskCompleted", "StopFailure")
}
POST_TOOL_MATCHERS = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"}
MINIMUM_PYTHON = (3, 9)
MINIMUM_SVN = (1, 9)


@dataclass(frozen=True)
class Diagnostic:
    level: str
    name: str
    detail: str


def _layout_diagnostic(project_root: Path) -> Diagnostic:
    missing = [
        relative_path
        for relative_path in CORE_PATHS
        if not (project_root / relative_path).is_file()
    ]
    if missing:
        return Diagnostic("FAIL", "项目结构", "缺少：" + "、".join(missing))
    return Diagnostic("PASS", "项目结构", "核心文件完整")


def _run_read_only(
    arguments: list[str], project_root: Path
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            arguments,
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _first_line(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stdout.strip() or result.stderr.strip()
    return output.splitlines()[0] if output else "没有诊断输出"


def _version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _python_diagnostic() -> Diagnostic:
    actual = sys.version_info[:3]
    detail = ".".join(str(part) for part in actual)
    if actual < MINIMUM_PYTHON:
        return Diagnostic("FAIL", "Python", f"{detail}，要求 3.9+")
    return Diagnostic("PASS", "Python", detail)


def _claude_diagnostic(project_root: Path) -> Diagnostic:
    version_result = _run_read_only(["claude", "--version"], project_root)
    if version_result is None or version_result.returncode != 0:
        return Diagnostic("FAIL", "Claude Code", "无法执行 claude --version")
    doctor_result = _run_read_only(["claude", "doctor"], project_root)
    if doctor_result is None:
        return Diagnostic("FAIL", "Claude Code", "无法执行只读 claude doctor")
    if doctor_result.returncode != 0:
        return Diagnostic(
            "FAIL",
            "Claude Code",
            "内置 Doctor 未通过：" + _first_line(doctor_result),
        )
    return Diagnostic(
        "PASS",
        "Claude Code",
        _first_line(version_result) + "；内置 Doctor 通过",
    )


def _hook_matchers(
    settings: dict[str, object],
    event: str,
    expected_handler: tuple[str, ...],
) -> tuple[str | None, ...]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return ()
    groups = hooks.get(event)
    if not isinstance(groups, list):
        return ()
    matchers: list[str | None] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        raw_handlers = group.get("hooks")
        if not isinstance(raw_handlers, list):
            continue
        for handler in raw_handlers:
            if not isinstance(handler, dict) or handler.get("type") != "command":
                continue
            command = handler.get("command")
            arguments = handler.get("args")
            if not isinstance(command, str) or not isinstance(arguments, list):
                continue
            if not all(isinstance(argument, str) for argument in arguments):
                continue
            if (command, *arguments) != expected_handler:
                continue
            matcher = group.get("matcher")
            matchers.append(matcher if isinstance(matcher, str) else None)
    return tuple(matchers)


def _settings_diagnostic(project_root: Path) -> Diagnostic:
    settings_path = project_root / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Diagnostic("FAIL", "Hook 配置", f"settings.json 无法读取：{error}")
    if not isinstance(settings, dict):
        return Diagnostic("FAIL", "Hook 配置", "settings.json 顶层必须是对象")

    reasons: list[str] = []
    if settings.get("disableSkillShellExecution") is not True:
        reasons.append("disableSkillShellExecution 必须是 true")
    expected = dict(REQUIRED_HOOKS)
    environment = settings.get("env")
    teams_enabled = (
        isinstance(environment, dict)
        and environment.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1"
    )
    if teams_enabled:
        expected.update(SUPERVISION_HOOKS)
    for event, arguments in expected.items():
        expected_handler = ("python3", *arguments)
        matchers = _hook_matchers(settings, event, expected_handler)
        if not matchers:
            reasons.append(f"{event} 未接入预期 WALI Hook")
            continue
        if event == "PostToolUse":
            covered_tools = {
                part.strip()
                for matcher in matchers
                if matcher
                for part in matcher.split("|")
                if part.strip()
            }
            matcher_is_complete = (
                any(matcher in {None, ""} for matcher in matchers)
                or POST_TOOL_MATCHERS <= covered_tools
            )
            if not matcher_is_complete:
                reasons.append(
                    "PostToolUse matcher 必须覆盖 "
                    + "|".join(sorted(POST_TOOL_MATCHERS))
                )
        elif not any(matcher in {None, ""} for matcher in matchers):
            reasons.append(f"{event} matcher 不得缩小 WALI Hook 覆盖范围")
    if reasons:
        return Diagnostic("FAIL", "Hook 配置", "；".join(reasons))
    count = len(expected)
    return Diagnostic("PASS", "Hook 配置", f"{count} 类事件配置有效")


def _svn_diagnostics(
    project_root: Path,
) -> tuple[Diagnostic, Diagnostic, str | None]:
    version_result = _run_read_only(["svn", "--version", "--quiet"], project_root)
    if version_result is None or version_result.returncode != 0:
        return (
            Diagnostic("FAIL", "SVN", "无法执行 svn --version --quiet"),
            Diagnostic("WARN", "原生 Ignore", "因 SVN 不可用而跳过"),
            None,
        )
    parsed_version = _version(_first_line(version_result))
    if parsed_version is None or parsed_version < MINIMUM_SVN:
        return (
            Diagnostic(
                "FAIL",
                "SVN",
                f"{_first_line(version_result)}，要求 1.9+",
            ),
            Diagnostic("WARN", "原生 Ignore", "因 SVN 版本不兼容而跳过"),
            None,
        )
    try:
        reported_root = discover_working_copy_root(project_root)
    except SvnBoundaryError as error:
        return (
            Diagnostic("FAIL", "SVN", str(error)),
            Diagnostic("WARN", "原生 Ignore", "因工作副本边界无效而跳过"),
            None,
        )
    if reported_root != project_root.resolve():
        detail = "当前目录不是 SVN 工作副本根"
        if reported_root is not None:
            detail += f"；实际根为 {reported_root}"
        return (
            Diagnostic("FAIL", "SVN", detail),
            Diagnostic("WARN", "原生 Ignore", "因工作副本边界无效而跳过"),
            None,
        )
    metadata = project_root / ".svn"
    if not metadata.is_dir() or not os.access(metadata, os.W_OK):
        return (
            Diagnostic("FAIL", "SVN", ".svn 元数据目录不存在或不可写"),
            Diagnostic("WARN", "原生 Ignore", "因工作副本元数据无效而跳过"),
            None,
        )
    try:
        status_xml = read_status_xml(project_root)
        status = classify_status_xml(project_root, status_xml)
    except SvnBoundaryError as error:
        return (
            Diagnostic("FAIL", "SVN", f"无法读取完整状态：{error}"),
            Diagnostic("WARN", "原生 Ignore", "因状态读取失败而跳过"),
            None,
        )
    svn_detail = (
        f"{_first_line(version_result)}；工作副本根有效；"
        f"{len(status.auditable_changes)} 项需审计差异"
    )
    ignore_detail = f"{len(status.local_only_changes)} 个项目本地产物"
    return (
        Diagnostic("PASS", "SVN", svn_detail),
        Diagnostic("PASS", "原生 Ignore", ignore_detail),
        status_xml,
    )


def _state_diagnostics(
    project_root: Path, status_xml: str | None
) -> tuple[Diagnostic, Diagnostic]:
    try:
        contract = load_contract(project_root)
        contract_reasons = validate_project_contract(
            project_root, contract, status_xml=status_xml
        )
    except (OSError, PolicyError) as error:
        contract_reasons = [str(error)]
    if contract_reasons:
        contract_result = Diagnostic(
            "FAIL", "Goal 契约", "；".join(contract_reasons)
        )
    else:
        contract_result = Diagnostic("PASS", "Goal 契约", "schema 与阶段契约有效")

    try:
        graph = load_graph(project_root)
        graph_reasons = validate_graph(graph)
    except (OSError, GraphLoadError) as error:
        graph_reasons = [str(error)]
    if graph_reasons:
        graph_result = Diagnostic("FAIL", "工作图", "；".join(graph_reasons))
    else:
        graph_result = Diagnostic("PASS", "工作图", "关系与状态一致")
    return contract_result, graph_result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读检查 WALI 部署环境和项目状态。"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    diagnostics = [
        _layout_diagnostic(project_root),
        _python_diagnostic(),
        _claude_diagnostic(project_root),
        _settings_diagnostic(project_root),
    ]
    svn_result, ignore_result, status_xml = _svn_diagnostics(project_root)
    diagnostics.extend((svn_result, ignore_result))
    diagnostics.extend(_state_diagnostics(project_root, status_xml))

    for result in diagnostics:
        print(f"[{result.level}] {result.name}：{result.detail}")
    failed = sum(result.level == "FAIL" for result in diagnostics)
    warned = sum(result.level == "WARN" for result in diagnostics)
    passed = sum(result.level == "PASS" for result in diagnostics)
    print(
        f"汇总：{passed} 项通过，{warned} 项警告，{failed} 项失败。"
        "Doctor 只读，不会修改文件或 SVN 属性。"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
