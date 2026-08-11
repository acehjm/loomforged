---
name: wali-resume
description: 从 goal.md、work.md 和可选 handoff.md 恢复 wali-0x3 工作。
disable-model-invocation: true
---

1. 读取 `goal.md` 和 `work.md`，运行 `wali_policy.py check`。
2. 检查真实代码、`svn status` 和 `svn diff --internal-diff`；不把文档声明当成代码事实。
3. 只有 `stop_intent: handoff` 时才读取 `handoff.md`。核对 Goal ID、phase、active task、时间、Current State 和 Next Step；不接受与实时状态冲突的游标。
4. 恢复开始后将 `stop_intent` 改回 `continue`。普通会话不维护 handoff。
5. 按 phase 推进：
   - `define`：继续澄清或确认 Goal。
   - `work`：优先恢复 `active_task` 的 Scope；若 Task 已不再 `working`，优先修复 Work 状态，必要例外请求确认。
   - `verify`：独立审查和测试，默认不改实现；需要修复时优先把 Task/Issue 状态写回 `work.md` 后返回 `work`。
   - `paused`：只处理 `waiting_for` 指向的方向、验收或外部条件。
   - `done`：只读复核；新工作使用新 Goal ID 返回 `define`。
6. 多任务时按需运行 `wali_work.py frontier`，不要把手工 handoff 或旧输出当成调度权威。

输出当前 phase、真实差异、最后可信 Evidence、问题和唯一下一步。
