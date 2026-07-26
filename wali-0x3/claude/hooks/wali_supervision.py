#!/usr/bin/env python3
"""Supervise Claude agents without conflating runtime and WALI task state.

The hook validates lifecycle events against the Markdown-derived work graph.
Runtime events are recorded only in SVN working-copy metadata, never as a new
project artifact. StopFailure is observational because Claude Code does not
give that event decision control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from wali_graph import (
    GraphLoadError,
    Task,
    frontmatter,
    has_evidence,
    load_graph,
    validate_graph,
)
from wali_policy import (
    PolicyError,
    _svn_working_copy_root,
    _verified_svn_root,
    load_contract,
)


SUPERVISED_PHASES = {"implementing", "inspecting"}
COMPLETABLE_TASK_STATES = {"review", "done"}
MAX_EVENTS = 200
STATE_VERSION = 1
RECOVERY_ACTIONS = {"resume", "replace", "wait_user", "terminate_goal"}


class SupervisionError(RuntimeError):
    """Raised when supervision metadata cannot be trusted or updated."""


@dataclass(frozen=True)
class EventDecision:
    allowed: bool
    message: str = ""
    wali_task_id: str = ""
    runtime_state: str = ""
    recovery_required: bool = False


def _value(mapping: dict[str, object], key: str) -> str:
    return str(mapping.get(key, "") or "").strip()


def _stable_task_ids(payload: dict[str, object]) -> tuple[str, ...]:
    source = " ".join(
        (
            _value(payload, "task_id"),
            _value(payload, "task_subject"),
        )
    )
    return tuple(dict.fromkeys(re.findall(r"\bT-\d+\b", source.upper())))


def _agent_matches_owner(agent_name: str, owner: str) -> bool:
    agent = agent_name.strip().lower()
    expected = owner.strip().lower()
    if not agent or not expected or expected in {"none", "-", "待分配"}:
        return False
    return (
        agent == expected
        or agent.startswith(expected + "-")
        or agent.endswith("-" + expected)
    )


def _active_context(
    project_root: Path,
) -> tuple[dict[str, object], Task | None, list[str]]:
    try:
        contract = load_contract(project_root)
        graph = load_graph(project_root)
    except (PolicyError, GraphLoadError) as error:
        return {}, None, [str(error)]
    graph_reasons = validate_graph(graph)
    active_task = _value(contract, "active_task")
    task = next((candidate for candidate in graph.tasks if candidate.id == active_task), None)
    if (
        _value(contract, "phase") in SUPERVISED_PHASES
        and active_task not in {"", "none"}
        and task is None
    ):
        graph_reasons.append(f"active_task {active_task} 不存在")
    return contract, task, graph_reasons


def _task_completed_decision(
    project_root: Path, payload: dict[str, object]
) -> EventDecision:
    contract, task, reasons = _active_context(project_root)
    phase = _value(contract, "phase")
    active_task = _value(contract, "active_task")
    if phase not in SUPERVISED_PHASES or active_task in {"", "none"}:
        return EventDecision(True, runtime_state="completed")
    if reasons:
        return EventDecision(
            False,
            "TaskCompleted 前工作图无效：" + "；".join(reasons),
            active_task,
            "needs_attention",
            True,
        )

    referenced = _stable_task_ids(payload)
    if referenced != (active_task,):
        return EventDecision(
            False,
            f"TaskCompleted 必须且只能关联 active_task {active_task}",
            active_task,
            "needs_attention",
            True,
        )
    assert task is not None
    if task.status not in COMPLETABLE_TASK_STATES:
        return EventDecision(
            False,
            f"{active_task} 仍是 {task.status or '未知状态'}；完成运行任务前必须写入执行证据并转为 review，不能把 Agent 结束等同于 WALI Task 完成",
            active_task,
            "needs_attention",
            True,
        )
    if not has_evidence(task.evidence):
        return EventDecision(
            False,
            f"{active_task} 缺少执行结果/证据，不能完成运行任务",
            active_task,
            "needs_attention",
            True,
        )
    return EventDecision(
        True,
        wali_task_id=active_task,
        runtime_state="completed",
        recovery_required=False,
    )


def _teammate_idle_decision(
    project_root: Path, payload: dict[str, object]
) -> EventDecision:
    contract, task, reasons = _active_context(project_root)
    phase = _value(contract, "phase")
    active_task = _value(contract, "active_task")
    teammate = _value(payload, "teammate_name")
    if phase not in SUPERVISED_PHASES or active_task in {"", "none"}:
        return EventDecision(True, runtime_state="idle")
    if reasons:
        return EventDecision(
            False,
            "TeammateIdle 前工作图无效：" + "；".join(reasons),
            active_task,
            "needs_attention",
            True,
        )
    assert task is not None
    if not _agent_matches_owner(teammate, task.owner):
        return EventDecision(True, runtime_state="idle")
    if task.status == "working":
        return EventDecision(
            False,
            f"{teammate or task.owner} 仍负责 working 任务 {active_task}，不能进入 idle；请报告当前步骤，并将任务带证据转为 review，或记录真实阻断后再停止",
            active_task,
            "needs_attention",
            True,
        )
    if task.status == "blocked":
        if not has_evidence(task.evidence):
            return EventDecision(
                False,
                f"blocked 任务 {active_task} 缺少阻断证据，不能进入 idle",
                active_task,
                "needs_attention",
                True,
            )
        return EventDecision(
            True,
            wali_task_id=active_task,
            runtime_state="waiting",
            recovery_required=True,
        )
    if task.status in COMPLETABLE_TASK_STATES and not has_evidence(task.evidence):
        return EventDecision(
            False,
            f"{active_task} 缺少执行结果/证据，不能进入 idle",
            active_task,
            "needs_attention",
            True,
        )
    return EventDecision(
        True,
        wali_task_id=active_task,
        runtime_state="idle",
        recovery_required=False,
    )


def evaluate_event(project_root: Path, payload: dict[str, object]) -> EventDecision:
    """Return the deterministic decision for one supported lifecycle event."""

    event_name = _value(payload, "hook_event_name")
    if event_name == "TaskCompleted":
        return _task_completed_decision(project_root, payload)
    if event_name == "TeammateIdle":
        return _teammate_idle_decision(project_root, payload)
    if event_name == "StopFailure":
        contract, _task, _reasons = _active_context(project_root)
        active_task = _value(contract, "active_task")
        if active_task == "none":
            active_task = ""
        return EventDecision(
            True,
            wali_task_id=active_task,
            runtime_state="failed",
            recovery_required=bool(active_task),
        )
    return EventDecision(False, f"不支持的监督 Hook 事件：{event_name or '空'}")


def _event_record(
    project_root: Path,
    payload: dict[str, object],
    decision: EventDecision,
) -> dict[str, object]:
    try:
        contract = load_contract(project_root)
    except PolicyError:
        contract = {}
    last_message = _value(payload, "last_assistant_message")
    timestamp = datetime.now(timezone.utc).isoformat()
    base = {
        "timestamp": timestamp,
        "hook_event": _value(payload, "hook_event_name"),
        "session_id": _value(payload, "session_id"),
        "teammate_name": _value(payload, "teammate_name"),
        "native_task_id": _value(payload, "task_id"),
        "wali_task_id": decision.wali_task_id,
        "goal_id": _value(contract, "goal_id"),
        "phase": _value(contract, "phase"),
        "runtime_state": decision.runtime_state,
        "recovery_required": decision.recovery_required,
        "error": _value(payload, "error")[:160],
        "transcript_path": _value(payload, "transcript_path"),
        "message_digest": (
            hashlib.sha256(last_message.encode("utf-8")).hexdigest()
            if last_message
            else ""
        ),
    }
    canonical = json.dumps(base, ensure_ascii=False, sort_keys=True)
    base["event_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return base


def _registry_path(project_root: Path) -> Path | None:
    try:
        svn_root = _svn_working_copy_root(project_root)
    except PolicyError as error:
        raise SupervisionError(str(error)) from error
    if svn_root is None:
        return None
    if svn_root != project_root.resolve() or not _verified_svn_root(project_root):
        raise SupervisionError("监督事件必须从可验证且可写的 SVN 工作副本根记录")
    return project_root / ".svn" / "wali-policy" / "supervision.json"


def _empty_registry() -> dict[str, object]:
    return {"version": STATE_VERSION, "events": [], "agents": {}, "tasks": {}}


def _read_registry(path: Path) -> dict[str, object]:
    if not path.exists():
        return _empty_registry()
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SupervisionError(f"监督状态文件无效：{error}") from error
    if not isinstance(registry, dict) or registry.get("version") != STATE_VERSION:
        raise SupervisionError("监督状态文件版本无效")
    if not isinstance(registry.get("events"), list):
        raise SupervisionError("监督事件列表无效")
    if not isinstance(registry.get("agents"), dict) or not isinstance(
        registry.get("tasks"), dict
    ):
        raise SupervisionError("监督状态索引无效")
    return registry


def _write_registry(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / "supervision.lock"
    acquired = False
    for _attempt in range(40):
        try:
            lock_path.mkdir()
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
    if not acquired:
        raise SupervisionError("监督状态正被另一个 Hook 更新")

    temporary_path: Path | None = None
    try:
        registry = _read_registry(path)
        events = list(registry["events"])
        events.append(event)
        registry["events"] = events[-MAX_EVENTS:]

        teammate = str(event.get("teammate_name", ""))
        session_id = str(event.get("session_id", ""))
        agent_key = teammate or session_id
        if agent_key:
            agents = dict(registry["agents"])
            agents[agent_key] = {
                "runtime_state": event.get("runtime_state", ""),
                "last_event_at": event.get("timestamp", ""),
                "session_id": session_id,
                "wali_task_id": event.get("wali_task_id", ""),
                "recovery_required": event.get("recovery_required", False),
                "transcript_path": event.get("transcript_path", ""),
            }
            registry["agents"] = agents

        task_id = str(event.get("wali_task_id", ""))
        if task_id:
            tasks = dict(registry["tasks"])
            tasks[task_id] = {
                "runtime_state": event.get("runtime_state", ""),
                "last_event_at": event.get("timestamp", ""),
                "event_id": event.get("event_id", ""),
                "agent": agent_key,
                "recovery_required": event.get("recovery_required", False),
            }
            registry["tasks"] = tasks

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix="supervision-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(registry, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError as error:
            raise SupervisionError(f"无法写入监督状态：{error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        try:
            lock_path.rmdir()
        except OSError:
            pass


def record_event(project_root: Path, event: dict[str, object]) -> bool:
    """Append a local event when a valid SVN metadata location is available."""

    path = _registry_path(project_root)
    if path is None:
        return False
    _write_registry(path, event)
    return True


def recovery_handoff_reasons(
    project_root: Path, *, svn_root_already_verified: bool = False
) -> list[str]:
    """Require an explicit recovery plan before handing off a failed task."""

    try:
        path = (
            project_root / ".svn" / "wali-policy" / "supervision.json"
            if svn_root_already_verified
            else _registry_path(project_root)
        )
        if path is None or not path.exists():
            return []
        registry = _read_registry(path)
        contract = load_contract(project_root)
    except (SupervisionError, PolicyError) as error:
        return [f"无法校验 Agent 恢复状态：{error}"]

    active_task = _value(contract, "active_task")
    task_state = registry["tasks"].get(active_task)
    if not isinstance(task_state, dict) or not task_state.get("recovery_required"):
        return []

    event_id = str(task_state.get("event_id", ""))
    handoff_path = project_root / "docs" / "wali-0x3" / "handoff.md"
    if not handoff_path.exists():
        return ["Agent 异常恢复需要 handoff.md"]
    try:
        metadata = frontmatter(handoff_path.read_text(encoding="utf-8"))
    except OSError as error:
        return [f"无法读取 Agent 异常恢复交接：{error}"]

    reasons: list[str] = []
    if metadata.get("supervision_event", "") != event_id:
        reasons.append(
            f"handoff.md 的 supervision_event 必须记录当前失败事件 {event_id}"
        )
    action = metadata.get("recovery_action", "")
    if action not in RECOVERY_ACTIONS:
        reasons.append(
            "handoff.md 的 recovery_action 必须是 resume、replace、wait_user 或 terminate_goal"
        )
    if not has_evidence(metadata.get("recovery_evidence", "")):
        reasons.append("handoff.md 必须记录可执行的 recovery_evidence")
    return reasons


def run_hook(project_root: Path, payload: dict[str, object]) -> int:
    decision = evaluate_event(project_root, payload)
    event = _event_record(project_root, payload, decision)
    try:
        record_event(project_root, event)
    except SupervisionError as error:
        if _value(payload, "hook_event_name") == "StopFailure":
            print(f"WALI 无法记录 StopFailure：{error}", file=sys.stderr)
            return 0
        print(f"WALI Agent 监督状态不可用：{error}", file=sys.stderr)
        return 2

    if not decision.allowed:
        print(f"WALI Agent 监督未通过：{decision.message}", file=sys.stderr)
        return 2
    return 0


def _run_hook_from_stdin(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        print(f"WALI Agent 监督 Hook 输入无效：{error}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("WALI Agent 监督 Hook 输入必须是对象", file=sys.stderr)
        return 2
    return run_hook(project_root, payload)


def _run_status(project_root: Path) -> int:
    try:
        path = _registry_path(project_root)
        registry = _empty_registry() if path is None else _read_registry(path)
    except SupervisionError as error:
        print(f"WALI Agent 监督状态不可用：{error}")
        return 1

    try:
        contract = load_contract(project_root)
        active_task = _value(contract, "active_task")
        phase = _value(contract, "phase")
    except PolicyError:
        active_task = ""
        phase = ""
    print(f"WALI Agent 监督状态：phase={phase or 'unknown'} active_task={active_task or 'none'}")
    tasks = registry["tasks"]
    agents = registry["agents"]
    if not tasks and not agents:
        print("暂无已记录的运行事件。")
        return 0
    for task_id, state in sorted(tasks.items()):
        assert isinstance(state, dict)
        recovery = "需要恢复" if state.get("recovery_required") else "无需恢复"
        print(
            f"- {task_id}: {state.get('runtime_state', 'unknown')}，{recovery}，"
            f"agent={state.get('agent') or 'unknown'}，"
            f"event={state.get('event_id') or 'unknown'}，"
            f"last={state.get('last_event_at') or 'unknown'}"
        )
    unbound_agents = [
        (name, state)
        for name, state in sorted(agents.items())
        if isinstance(state, dict) and not state.get("wali_task_id")
    ]
    for name, state in unbound_agents:
        print(
            f"- agent {name}: {state.get('runtime_state', 'unknown')}，"
            f"last={state.get('last_event_at') or 'unknown'}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    parser.add_argument("command", choices=("hook", "status"))
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if args.command == "hook":
        return _run_hook_from_stdin(project_root)
    return _run_status(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
