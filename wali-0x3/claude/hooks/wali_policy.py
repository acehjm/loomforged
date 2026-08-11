#!/usr/bin/env python3
"""Small, liveness-preserving policy hook for wali-0x3.

The policy protects implementation scope and irreversible effects.  It does
not require project-management metadata to be valid before that metadata can
be repaired, and it never turns a PostToolUse warning into an unrecoverable
state.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from wali_work import (
    GOAL_FILE,
    STATE_DIR,
    WORK_FILE,
    Goal,
    Task,
    WorkState,
    WorkStateError,
    checkpoint_reasons,
    load_goal,
    load_state,
    validate_state,
)


STATE_FILES = {GOAL_FILE.as_posix(), WORK_FILE.as_posix(), (STATE_DIR / "handoff.md").as_posix()}
CONTROL_PREFIXES = (".claude/", "claude/", ".svn/")
LOCAL_SVN_MUTATIONS = {"add", "delete", "del", "remove", "rm", "move", "mv", "copy", "cp", "update", "up", "resolve"}
REMOTE_SVN_MUTATIONS = {"commit", "ci", "lock", "unlock", "mkdir", "propset", "propdel", "import"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    ask: bool = False


def _relative_path(project_root: Path, raw_path: str) -> str | None:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def _scope_matches(path: str, scope: str) -> bool:
    normalized = scope.replace("\\", "/").strip().strip("`")
    if normalized == path:
        return True
    if not any(token in normalized for token in ("*", "?", "[")):
        return path.startswith(normalized.rstrip("/") + "/")
    return fnmatch.fnmatchcase(path, normalized)


def _active_task(state: WorkState) -> Task | None:
    return next((task for task in state.tasks if task.id == state.active_task), None)


def _state_path(project_root: Path, tool_input: dict[str, object]) -> str | None:
    raw = str(
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    return _relative_path(project_root, raw) if raw else None


def _safe_split(command: str) -> list[str] | None:
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _dangerous_local_command(command: str) -> bool:
    compact = re.sub(r"\s+", " ", command.strip().lower())
    patterns = (
        r"(?:^|[;&|]\s*)rm\s+[^\n]*(?:-rf|-fr)",
        r"(?:^|[;&|]\s*)git\s+reset\s+--hard(?:\s|$)",
        r"(?:^|[;&|]\s*)git\s+clean\s+[^\n]*-[^\s]*f",
        r"(?:^|[;&|]\s*)svn\s+revert(?:\s|$)",
        r"(?:^|[;&|]\s*)svn\s+cleanup\b[^\n]*(?:--remove-unversioned|--remove-ignored)",
    )
    return any(re.search(pattern, compact) for pattern in patterns)


def _external_write(command: str) -> bool:
    for segment in re.split(r"(?:&&|\|\||[;\n])", command):
        arguments = _safe_split(segment.strip())
        if not arguments:
            continue
        program = Path(arguments[0]).name.lower()
        lowered = [argument.lower() for argument in arguments[1:]]
        if program in {"ssh", "scp", "sftp", "ftp"}:
            return True
        if program == "git" and lowered[:1] in (["push"], ["send-email"]):
            return True
        if program == "svn" and lowered[:1] and lowered[0] in REMOTE_SVN_MUTATIONS:
            return True
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
        if program == "curl":
            if any(item in lowered for item in ("-d", "--data", "--data-raw", "--data-binary", "-f", "--form", "-t", "--upload-file")):
                return True
            for index, argument in enumerate(lowered):
                if argument in {"-x", "--request"} and index + 1 < len(lowered):
                    return lowered[index + 1] not in {"get", "head", "options"}
    return False


def _svn_local_targets(project_root: Path, command: str) -> tuple[str, tuple[str, ...]] | None:
    arguments = _safe_split(command)
    if not arguments or Path(arguments[0]).name != "svn" or len(arguments) < 2:
        return None
    operation = arguments[1].lower()
    if operation not in LOCAL_SVN_MUTATIONS:
        return None
    raw_targets = arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments[2:]
    targets: list[str] = []
    skip_next = False
    for argument in raw_targets:
        if skip_next:
            skip_next = False
            continue
        if argument in {"--accept", "--depth", "-r", "--revision"}:
            skip_next = True
            continue
        if argument.startswith("-"):
            continue
        relative = _relative_path(project_root, argument)
        if relative is None:
            return operation, ()
        targets.append(relative)
    return operation, tuple(targets)


def _project_state(project_root: Path) -> tuple[Goal | None, WorkState | None, list[str]]:
    try:
        goal_text = (project_root / GOAL_FILE).read_text(encoding="utf-8")
        goal = load_goal(project_root, text=goal_text)
    except (OSError, WorkStateError) as error:
        return None, None, [str(error)]
    try:
        state = load_state(project_root, goal_text=goal_text)
    except WorkStateError as error:
        return goal, None, [str(error)]
    return goal, state, validate_state(state)


def _decide_bash(project_root: Path, command: str) -> Decision:
    if not command.strip():
        return Decision(False, "Bash 命令不能为空")
    if _dangerous_local_command(command):
        return Decision(False, "命令包含破坏性本地操作；请由用户明确执行或拆成可审计动作")
    external_write = _external_write(command)
    svn = _svn_local_targets(project_root, command)
    if not external_write and svn is None:
        # Common local commands do not depend on project-management state.
        return Decision(True)
    try:
        goal = load_goal(project_root)
    except WorkStateError:
        return Decision(False, "当前 Goal 不可读，不能授权有副作用的命令")
    if external_write:
        if not goal.allow_external_writes:
            return Decision(False, "当前 Goal 未授权外部写入")
        return Decision(True, "命令会写入外部系统，请核对目标后确认", ask=True)
    if svn is not None:
        operation, targets = svn
        try:
            state = load_state(project_root)
            state_reasons = validate_state(state)
        except WorkStateError:
            state = None
            state_reasons = ["状态不可读"]
        if state is None or state_reasons or state.phase != "work":
            return Decision(False, f"只有 work phase 可以执行 svn {operation}")
        task = _active_task(state)
        if task is None or task.status != "working":
            return Decision(False, "本地 SVN 变更要求 active_task 处于 working")
        invalid = [
            target
            for target in targets
            if not any(_scope_matches(target, scope) for scope in task.scopes)
        ]
        if not targets or invalid:
            return Decision(False, "SVN 目标必须是 active_task Scope 内的精确路径")
    return Decision(True)


def decide_tool(project_root: Path, payload: dict[str, object]) -> Decision:
    tool_name = str(payload.get("tool_name", ""))
    raw_input = payload.get("tool_input", {})
    if not isinstance(raw_input, dict):
        return Decision(False, "tool_input 必须是对象")
    tool_input = raw_input
    path = _state_path(project_root, tool_input)

    # Governance state is always repairable, even when it is missing or invalid.
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and path in STATE_FILES:
        return Decision(True)

    if tool_name in {"Read", "Glob", "Grep", "WebFetch", "WebSearch"}:
        if path is not None and _relative_path(project_root, path) is None:
            return Decision(False, "读取路径不在项目内")
        return Decision(True)
    if tool_name == "Bash":
        return _decide_bash(project_root, str(tool_input.get("command", "")))
    if tool_name in {"Skill", "Agent", "AskUserQuestion"}:
        return Decision(True)
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        goal, state, reasons = _project_state(project_root)
        if path is None:
            return Decision(False, "写入路径不在项目内")
        if goal is None:
            return Decision(False, "Goal 状态不可读；请先修复 docs/wali-0x3/goal.md")
        if reasons:
            return Decision(False, "工作状态需要修复；当前只允许修改 goal.md、work.md 或 handoff.md")
        if path == "CLAUDE.md" or path.startswith(CONTROL_PREFIXES):
            return Decision(False, f"项目任务不得修改 wali-0x3 控制面：{path}")
        if state is None or state.phase != "work":
            phase = state.phase if state is not None else "invalid"
            return Decision(False, f"{phase} phase 不允许修改实现：{path}")
        task = _active_task(state)
        if task is None or task.status != "working":
            return Decision(False, "实现写入要求 active_task 处于 working")
        if not any(_scope_matches(path, scope) for scope in task.scopes):
            return Decision(False, f"写入超出 active_task Scope：{path}")
        return Decision(True)
    # Tools outside the configured hook matcher remain governed by Claude's own
    # permission system. If invoked here explicitly, do not invent a denial.
    return Decision(True)


def _decision_output(decision: Decision) -> None:
    if decision.allowed and not decision.ask:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask" if decision.ask else "deny",
                    "permissionDecisionReason": decision.reason,
                }
            },
            ensure_ascii=False,
        )
    )


def _run_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是对象")
        decision = decide_tool(project_root, payload)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        decision = Decision(False, f"WALI Hook 输入无效：{error}")
    _decision_output(decision)
    return 0


def _run_post_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是对象")
        tool_name = str(payload.get("tool_name", ""))
        raw_input = payload.get("tool_input", {})
        tool_input = raw_input if isinstance(raw_input, dict) else {}
        path = _state_path(project_root, tool_input)
        if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and path in STATE_FILES:
            _goal, _state, reasons = _project_state(project_root)
            if reasons:
                print(
                    json.dumps(
                        {
                            "systemMessage": "WALI 状态需要修复：\n- " + "\n- ".join(reasons)
                        },
                        ensure_ascii=False,
                    )
                )
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(json.dumps({"systemMessage": f"WALI PostHook 无法检查结果：{error}"}, ensure_ascii=False))
    return 0


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
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("hook")
    subparsers.add_parser("post-hook")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--checkpoint", choices=("work", "verify", "done"))
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "hook":
        return _run_hook(project_root)
    if args.command == "post-hook":
        return _run_post_hook(project_root)
    return _run_check(project_root, args.checkpoint)


if __name__ == "__main__":
    sys.exit(main())
