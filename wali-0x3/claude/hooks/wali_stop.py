#!/usr/bin/env python3
"""Stop policy for wali-0x3.

Ordinary session completion is never held hostage by project paperwork.  A
strict recoverability check runs only when the user or agent explicitly asks
for a handoff cursor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from wali_work import STATE_DIR, WorkStateError, frontmatter, load_state, validate_state


HANDOFF_FILE = STATE_DIR / "handoff.md"
PLACEHOLDERS = {"", "none", "n/a", "pending", "待补充", "待恢复", "待确定"}


def _meaningful_section(text: str, heading: str) -> bool:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return False
    content: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("## "):
            break
        stripped = line.strip().strip("- ")
        if stripped:
            content.append(stripped)
    return any(item.lower() not in PLACEHOLDERS for item in content)


def _valid_timestamp(value: str) -> bool:
    if not value or "YYYY" in value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def handoff_reasons(project_root: Path) -> list[str]:
    try:
        state = load_state(project_root)
    except WorkStateError as error:
        return [str(error)]
    reasons = validate_state(state)
    path = project_root / HANDOFF_FILE
    if not path.exists():
        return reasons + ["显式交接前必须创建 handoff.md"]
    try:
        text = path.read_text(encoding="utf-8")
        metadata = frontmatter(text, "handoff.md")
    except (OSError, WorkStateError) as error:
        return reasons + [str(error)]
    expected = {
        "goal_id": state.goal.id,
        "phase": state.phase,
        "active_task": state.active_task,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            reasons.append(f"handoff.md 的 {key} 必须与 goal.md 一致")
    if not _valid_timestamp(metadata.get("updated", "")):
        reasons.append("handoff.md 必须记录真实 updated 时间")
    if not _meaningful_section(text, "## Current State"):
        reasons.append("handoff.md 必须记录 Current State")
    if not _meaningful_section(text, "## Next Step"):
        reasons.append("handoff.md 必须记录唯一 Next Step")
    return list(dict.fromkeys(reasons))


def evaluate_stop(project_root: Path) -> list[str]:
    try:
        state = load_state(project_root)
    except WorkStateError:
        # An absent or malformed optional control plane must not make Claude
        # unable to end a normal session. PreToolUse retains the repair channel.
        return []
    if state.stop_intent != "handoff":
        return []
    return handoff_reasons(project_root)


def _run_hook(project_root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        print(json.dumps({"systemMessage": f"WALI Stop 输入无效：{error}"}, ensure_ascii=False))
        return 0
    if payload.get("stop_hook_active") or payload.get("background_tasks") or payload.get("session_crons"):
        return 0
    reasons = evaluate_stop(project_root)
    if reasons:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "WALI 显式交接尚不可恢复：\n- " + "\n- ".join(reasons),
                },
                ensure_ascii=False,
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", action="store_true")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.hook:
        return _run_hook(root)
    reasons = handoff_reasons(root)
    if reasons:
        print("WALI handoff 检查未通过：")
        for reason in reasons:
            print(f"- {reason}")
        return 1
    print("WALI handoff 检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
