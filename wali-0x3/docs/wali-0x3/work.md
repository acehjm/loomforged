---
goal_id: pending
phase: define
active_task: none
stop_intent: continue
waiting_for: none
outcome: none
---

# Work

> `work.md` 只保存会变化的执行状态。Goal 的 why/what 留在 `goal.md`，稳定实现契约留在 `spec.md`；交接只在真正需要中断会话时写入 `handoff.md`。`active_task` 可为 `none`、一个 Task ID，或两个以逗号分隔的 Task ID；两个 active Task 必须依赖已满足且 Scope 互斥。Task Owner 使用 `backend`、`frontend` 或 `wali`。只有 Wali 写本文件，其他 Agent 返回结构化结果。

## Acceptance

| ID | Status | Evidence | Verifier |
| --- | --- | --- | --- |

## Tasks

| ID | Acceptance | Task | Status | Depends On | Scope | Evidence | Owner | Verifier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Issues

| ID | Task | Acceptance | Severity | Status | Description | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
