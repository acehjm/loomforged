#!/usr/bin/env python3
"""Read-only deployment checks for wali-0x3."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from wali_work import WorkStateError, load_state, validate_state


CORE_PROJECT_PATHS = (
    "CLAUDE.md",
    "docs/wali-0x3/goal.md",
    "docs/wali-0x3/spec.md",
    "docs/wali-0x3/work.md",
)
AGENT_NAMES = (
    "wali-0x3",
    "architect",
    "backend-dev",
    "frontend-dev",
    "reviewer",
    "tester",
)
CORE_CONTROL_PATHS = (
    "settings.json",
    "agents/wali-0x3.md",
    "agents/architect.md",
    "agents/backend-dev.md",
    "agents/frontend-dev.md",
    "agents/reviewer.md",
    "agents/tester.md",
    "hooks/wali-doctor.py",
    "hooks/wali_work.py",
    "hooks/wali_policy.py",
    "hooks/wali_stop.py",
    "hooks/wali_svn.py",
    "skills/wali-start/SKILL.md",
    "skills/wali-resume/SKILL.md",
    "skills/wali-handoff/SKILL.md",
    "skills/wali-inspect/SKILL.md",
)


@dataclass(frozen=True)
class Diagnostic:
    level: str
    name: str
    detail: str


def _layout(project_root: Path) -> Diagnostic:
    control = ".claude" if (project_root / ".claude").is_dir() else "claude"
    paths = CORE_PROJECT_PATHS + tuple(f"{control}/{path}" for path in CORE_CONTROL_PATHS)
    missing = [path for path in paths if not (project_root / path).is_file()]
    if missing:
        return Diagnostic("FAIL", "布局", "缺少：" + ", ".join(missing))
    legacy = project_root / control / "agents" / "developer.md"
    if legacy.is_file():
        return Diagnostic("FAIL", "布局", f"不应保留遗留 Agent：{control}/agents/developer.md")
    invalid_identities = []
    for name in AGENT_NAMES:
        path = project_root / control / "agents" / f"{name}.md"
        definition = path.read_text(encoding="utf-8")
        if "## 身份" not in definition or "你是 wali-0x3" not in definition:
            invalid_identities.append(f"{control}/agents/{name}.md")
    if invalid_identities:
        return Diagnostic(
            "FAIL",
            "布局",
            "缺少明确身份契约：" + ", ".join(invalid_identities),
        )
    return Diagnostic("PASS", "布局", "goal.md + spec.md + work.md 控制面完整")


def _hook_command(entry: dict[str, object]) -> tuple[str, tuple[str, ...]]:
    hooks = entry.get("hooks")
    if not isinstance(hooks, list) or len(hooks) != 1 or not isinstance(hooks[0], dict):
        return "", ()
    hook = hooks[0]
    command = str(hook.get("command", ""))
    arguments = hook.get("args")
    return command, tuple(str(item) for item in arguments) if isinstance(arguments, list) else ()


def _settings(project_root: Path) -> Diagnostic:
    control = ".claude" if (project_root / ".claude").is_dir() else "claude"
    path = project_root / control / "settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Diagnostic("FAIL", "Hook 设置", str(error))
    skill_shell_disabled = settings.get("disableSkillShellExecution") is not False
    if settings.get("agent") != "wali-0x3":
        return Diagnostic("FAIL", "Hook 设置", "默认 Agent 必须是 wali-0x3")
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return Diagnostic("FAIL", "Hook 设置", "缺少 hooks")
    for legacy in ("TeammateIdle", "TaskCompleted", "StopFailure"):
        if legacy in hooks:
            return Diagnostic("FAIL", "Hook 设置", f"默认配置不应启用 {legacy}")
    pre = hooks.get("PreToolUse")
    post = hooks.get("PostToolUse")
    stop = hooks.get("Stop")
    subagent_start = hooks.get("SubagentStart")
    subagent_stop = hooks.get("SubagentStop")
    if not all(
        isinstance(value, list) and len(value) == 1
        for value in (pre, post, stop, subagent_start, subagent_stop)
    ):
        return Diagnostic(
            "FAIL",
            "Hook 设置",
            "Pre/Post/Stop/SubagentStart/SubagentStop 必须各注册一次",
        )
    assert all(
        isinstance(value, list)
        for value in (pre, post, stop, subagent_start, subagent_stop)
    )
    pre_entry = pre[0]
    post_entry = post[0]
    stop_entry = stop[0]
    subagent_start_entry = subagent_start[0]
    subagent_stop_entry = subagent_stop[0]
    if not all(
        isinstance(value, dict)
        for value in (
            pre_entry,
            post_entry,
            stop_entry,
            subagent_start_entry,
            subagent_stop_entry,
        )
    ):
        return Diagnostic("FAIL", "Hook 设置", "Hook 条目格式无效")
    expected_agents = "backend-dev|frontend-dev"
    if (
        subagent_start_entry.get("matcher") != expected_agents
        or subagent_stop_entry.get("matcher") != expected_agents
    ):
        return Diagnostic("FAIL", "Hook 设置", "实现 Agent 生命周期 matcher 无效")
    pre_tools = {tool for tool in str(pre_entry.get("matcher", "")).split("|") if tool}
    post_tools = {tool for tool in str(post_entry.get("matcher", "")).split("|") if tool}
    expected_pre = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"}
    expected_post = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
    if pre_tools != expected_pre:
        return Diagnostic("FAIL", "Hook 设置", "PreToolUse matcher 必须只覆盖 Bash 与写入工具")
    if post_tools != expected_post:
        return Diagnostic("FAIL", "Hook 设置", "PostToolUse matcher 必须只覆盖写入工具")
    expected = (
        (pre_entry, "wali_policy.py", "hook"),
        (post_entry, "wali_policy.py", "post-hook"),
        (stop_entry, "wali_stop.py", "--hook"),
        (subagent_start_entry, "wali_work.py", "claim-hook"),
        (subagent_stop_entry, "wali_work.py", "release-hook"),
    )
    for entry, script, argument in expected:
        command, arguments = _hook_command(entry)
        if command != "python3" or not any(item.endswith(script) for item in arguments) or argument not in arguments:
            return Diagnostic("FAIL", "Hook 设置", f"{script} 注册无效")
    if skill_shell_disabled:
        return Diagnostic("WARN", "Hook 设置", "Skill 动态上下文命令已禁用；外部 Skill 功能可能受限")
    return Diagnostic("PASS", "Hook 设置", "只拦截副作用工具；受信任 Skill 动态命令可用")


def _state(project_root: Path) -> Diagnostic:
    try:
        reasons = validate_state(load_state(project_root))
    except WorkStateError as error:
        return Diagnostic("FAIL", "状态", str(error))
    if reasons:
        return Diagnostic("FAIL", "状态", "；".join(reasons))
    return Diagnostic("PASS", "状态", "goal.md、spec.md 与 work.md 一致")


def _python() -> Diagnostic:
    if sys.version_info < (3, 9):
        return Diagnostic("FAIL", "Python", "需要 Python 3.9+")
    return Diagnostic("PASS", "Python", sys.version.split()[0])


def _svn() -> Diagnostic:
    executable = shutil.which("svn")
    if executable is None:
        return Diagnostic("WARN", "SVN", "当前机器未安装 SVN；部署到 SVN 项目前需补充验证")
    result = subprocess.run(
        [executable, "--version", "--quiet"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return Diagnostic("WARN", "SVN", "无法读取 SVN 版本")
    return Diagnostic("PASS", "SVN", result.stdout.strip())


def diagnose(project_root: Path) -> tuple[Diagnostic, ...]:
    return (_layout(project_root), _settings(project_root), _state(project_root), _python(), _svn())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    diagnostics = diagnose(args.project_root.resolve())
    for item in diagnostics:
        print(f"[{item.level}] {item.name}: {item.detail}")
    return 1 if any(item.level == "FAIL" for item in diagnostics) else 0


if __name__ == "__main__":
    sys.exit(main())
