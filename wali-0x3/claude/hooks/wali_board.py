#!/usr/bin/env python3
"""Serve the read-only WALI project board.

The browser polls a single aggregate endpoint every second. This
process never writes project state and deliberately exposes only
reader-facing task, issue, goal, and agent fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from wali_graph import GraphLoadError, frontmatter, load_graph


STATE_NAMES = ("goal.md", "spec.md", "todo.md", "issues.md", "handoff.md")
ROLE_ORDER = ("coordinator", "architect", "developer", "reviewer", "tester")
TASK_PRIORITY = {
    "working": 0,
    "review": 1,
    "blocked": 2,
    "pending": 3,
    "done": 4,
}
MAX_RUNTIME_EVENTS = 20


class BoardStateError(RuntimeError):
    """Raised when a trustworthy board snapshot cannot be assembled."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise BoardStateError("项目状态暂时无法读取") from error


def _plain_markdown(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("`", "")
    value = re.sub(r"^\s*[-*+]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _section_text(markdown: str, heading: str) -> str:
    """Return the first paragraph below an exact Markdown heading."""

    lines = markdown.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == heading),
        None,
    )
    if start is None:
        return ""

    collected: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        if stripped.startswith("|"):
            break
        if stripped:
            collected.append(stripped)
        elif collected:
            break
    return _plain_markdown(" ".join(collected))


def _snapshot_revision(project_root: Path) -> str:
    digest = hashlib.sha256()
    state_root = project_root / "docs" / "wali-0x3"
    paths = [state_root / name for name in STATE_NAMES]
    paths.append(project_root / ".svn" / "wali-policy" / "supervision.json")
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except FileNotFoundError:
            digest.update(b"\0")
        except OSError as error:
            raise BoardStateError("项目状态暂时无法读取") from error
    return digest.hexdigest()


def _load_runtime(project_root: Path) -> dict[str, Any]:
    path = project_root / ".svn" / "wali-policy" / "supervision.json"
    if not path.exists():
        return {"available": False, "agents": {}, "events": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "agents": {},
            "events": [],
            "degraded": True,
        }
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or not isinstance(payload.get("agents"), dict)
        or not isinstance(payload.get("events"), list)
    ):
        return {
            "available": False,
            "agents": {},
            "events": [],
            "degraded": True,
        }
    return {
        "available": True,
        "agents": payload["agents"],
        "events": payload["events"][-MAX_RUNTIME_EVENTS:],
    }


def _role_for_agent(name: str) -> str:
    normalized = name.strip().lower()
    for role in ROLE_ORDER:
        if (
            normalized == role
            or normalized.startswith(role + "-")
            or normalized.endswith("-" + role)
        ):
            return role
    return "agent"


def _agent_matches_owner(agent: str, owner: str) -> bool:
    agent_name = agent.strip().lower()
    owner_name = owner.strip().lower()
    if not agent_name or not owner_name:
        return False
    return (
        agent_name == owner_name
        or agent_name.startswith(owner_name + "-")
        or agent_name.endswith("-" + owner_name)
        or owner_name.startswith(agent_name + "-")
        or owner_name.endswith("-" + agent_name)
        or _role_for_agent(agent_name) == owner_name
    )


def _task_payload(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "owner": task.owner,
        "status": task.status,
        "necessity": task.necessity,
        "dependencies": list(task.dependencies),
        "verifier": task.verifier,
    }


def _issue_payload(issue: Any) -> dict[str, Any]:
    return {
        "id": issue.id,
        "description": issue.description,
        "severity": issue.severity,
        "status": issue.status,
        "owner": issue.fixer,
        "tasks": list(issue.task_ids),
    }


def _agent_task(agent: str, tasks: list[dict[str, Any]], active_task: str) -> dict[str, Any] | None:
    owned = [task for task in tasks if _agent_matches_owner(agent, task["owner"])]
    if not owned:
        return None
    owned.sort(
        key=lambda task: (
            task["id"] != active_task,
            TASK_PRIORITY.get(task["status"], 99),
            task["id"],
        )
    )
    return owned[0]


def _runtime_agent_state(runtime_agents: dict[str, Any], name: str) -> dict[str, Any]:
    exact = runtime_agents.get(name)
    if isinstance(exact, dict):
        return exact
    candidates = [
        state
        for candidate, state in runtime_agents.items()
        if isinstance(state, dict)
        and _agent_matches_owner(str(candidate), name)
    ]
    if not candidates:
        return {}
    candidates.sort(key=lambda state: str(state.get("last_event_at", "")), reverse=True)
    return candidates[0]


def _agent_payloads(
    tasks: list[dict[str, Any]],
    runtime: dict[str, Any],
    active_task: str,
) -> list[dict[str, Any]]:
    runtime_agents = runtime.get("agents", {})
    names: list[str] = [
        str(name) for name in runtime_agents if str(name).strip()
    ]
    names.extend(
        task["owner"]
        for task in tasks
        if task["owner"] and task["owner"] not in {"none", "待分配", "-"}
    )
    names = list(dict.fromkeys(names))
    for role in ROLE_ORDER:
        if not any(_role_for_agent(name) == role for name in names):
            names.append(role)

    payloads: list[dict[str, Any]] = []
    for name in names:
        role = _role_for_agent(name)
        task = _agent_task(name, tasks, active_task)
        runtime_state = _runtime_agent_state(runtime_agents, name)
        payloads.append(
            {
                "name": name,
                "role": role,
                "task": (
                    {
                        "id": task["id"],
                        "title": task["title"],
                        "status": task["status"],
                    }
                    if task
                    else None
                ),
                "runtimeState": str(runtime_state.get("runtime_state", "")),
                "lastEventAt": str(runtime_state.get("last_event_at", "")),
                "recoveryRequired": bool(
                    runtime_state.get("recovery_required", False)
                ),
            }
        )
    role_rank = {role: index for index, role in enumerate(ROLE_ORDER)}
    payloads.sort(
        key=lambda agent: (
            role_rank.get(agent["role"], len(ROLE_ORDER)),
            agent["name"],
        )
    )
    return payloads


def _runtime_activity(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    activity: list[dict[str, Any]] = []
    for event in reversed(runtime.get("events", [])):
        if not isinstance(event, dict):
            continue
        agent = str(
            event.get("teammate_name")
            or event.get("session_id")
            or "agent"
        )
        task = str(event.get("wali_task_id") or "")
        state = str(event.get("runtime_state") or "")
        if state == "completed":
            message = f"{agent} 完成一次运行"
        elif state == "idle":
            message = f"{agent} 进入空闲"
        elif state == "waiting":
            message = f"{agent} 正在等待"
        elif state == "failed":
            message = f"{agent} 需要恢复"
        elif state == "needs_attention":
            message = f"{agent} 需要关注"
        else:
            message = f"{agent} 运行状态已变化"
        if task:
            message += f"，关联 {task}"
        activity.append(
            {
                "id": str(event.get("event_id") or ""),
                "timestamp": str(event.get("timestamp") or ""),
                "message": message,
            }
        )
    return activity


def build_state(project_root: Path) -> dict[str, Any]:
    """Build one reader-facing, path-free dashboard snapshot."""

    project_root = project_root.resolve()
    state_root = project_root / "docs" / "wali-0x3"
    goal_text = _read_text(state_root / "goal.md")
    metadata = frontmatter(goal_text)
    try:
        graph = load_graph(project_root, goal_text=goal_text)
    except GraphLoadError as error:
        raise BoardStateError(str(error)) from error

    tasks = [_task_payload(task) for task in graph.tasks]
    issues = [_issue_payload(issue) for issue in graph.issues]
    active_task = str(metadata.get("active_task", "")).strip()
    if active_task in {"", "none"}:
        active_task = ""
    now = next((task for task in tasks if task["id"] == active_task), None)
    runtime = _load_runtime(project_root)
    criteria_total = len(graph.criteria)
    criteria_verified = sum(
        criterion.status == "verified" for criterion in graph.criteria
    )
    open_issues = sum(issue["status"] != "closed" for issue in issues)
    title = _section_text(goal_text, "### 目标")
    if not title:
        title = (
            "目标仍在澄清"
            if str(metadata.get("phase", "")) == "clarifying"
            else "尚未填写目标描述"
        )

    return {
        "ok": True,
        "checkedAt": _utc_now(),
        "revision": _snapshot_revision(project_root),
        "goal": {
            "id": graph.goal_id,
            "title": title,
            "status": graph.goal_status,
            "phase": str(metadata.get("phase", "")),
            "confirmation": str(metadata.get("goal_confirmation", "")),
            "activeTask": active_task,
            "taskCount": len(tasks),
            "openIssueCount": open_issues,
            "criteriaTotal": criteria_total,
            "criteriaVerified": criteria_verified,
        },
        "now": now,
        "tasks": tasks,
        "issues": issues,
        "agents": _agent_payloads(tasks, runtime, active_task),
        "activity": _runtime_activity(runtime),
        "runtime": {
            "available": bool(runtime.get("available")),
            "degraded": bool(runtime.get("degraded")),
        },
    }


class WaliBoardServer(ThreadingHTTPServer):
    """HTTP server carrying immutable route targets."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        project_root: Path,
    ) -> None:
        self.project_root = project_root.resolve()
        self.html_path = (
            self.project_root / "docs" / "wali-0x3" / "wali-board.html"
        )
        super().__init__(address, WaliBoardHandler)


class WaliBoardHandler(BaseHTTPRequestHandler):
    """Serve only the self-contained board and one read-only API."""

    server: WaliBoardServer
    server_version = "WaliBoard/1"

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        length: int,
        *,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        self.end_headers()

    def _send_bytes(
        self,
        payload: bytes,
        content_type: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        cache_control: str = "no-store",
    ) -> None:
        self._headers(
            status,
            content_type,
            len(payload),
            cache_control=cache_control,
        )
        self.wfile.write(payload)

    def _send_known_file(
        self,
        path: Path,
        content_type: str,
        *,
        cache_control: str,
    ) -> None:
        try:
            payload = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_bytes(
            payload,
            content_type,
            cache_control=cache_control,
        )

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        route = urlparse(self.path).path
        if route == "/api/state":
            try:
                state = build_state(self.server.project_root)
                payload = json.dumps(
                    state,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send_bytes(payload, "application/json; charset=utf-8")
            except BoardStateError as error:
                payload = json.dumps(
                    {"ok": False, "error": str(error), "checkedAt": _utc_now()},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send_bytes(
                    payload,
                    "application/json; charset=utf-8",
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return
        if route in {"/", "/wali-board.html"}:
            self._send_known_file(
                self.server.html_path,
                "text/html; charset=utf-8",
                cache_control="no-store",
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[wali-board] {self.address_string()} {format % args}", file=sys.stderr)


def create_server(
    project_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> WaliBoardServer:
    server = WaliBoardServer((host, port), project_root)
    if not server.html_path.is_file():
        server.server_close()
        raise BoardStateError("缺少 WALI 看板 HTML")
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="启动只读 WALI 项目看板")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="项目根目录，默认为当前目录",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--open",
        action="store_true",
        help="启动后在默认浏览器中打开页面",
    )
    args = parser.parse_args()

    try:
        server = create_server(args.project_root, args.host, args.port)
    except (BoardStateError, OSError) as error:
        print(f"WALI 看板无法启动：{error}", file=sys.stderr)
        return 1

    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"WALI 只读看板：{url}")
    print("每 1 秒读取一次项目状态；按 Ctrl-C 停止。")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nWALI 看板已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
