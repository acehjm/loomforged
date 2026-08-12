---
name: wali-resume
description: 从 goal.md、spec.md、work.md 和可选 handoff.md 恢复 wali-0x3 工作。
disable-model-invocation: true
---

1. 读取 `goal.md`、`spec.md` 和 `work.md`，运行 `wali_policy.py check`。
2. 检查真实代码、`svn status` 和 `svn diff --internal-diff`；不把文档声明当成代码事实。
3. 只有 `stop_intent: handoff` 时才读取 `handoff.md`。核对 Goal ID、phase、active task、时间、Current State 和 Next Step；不接受与实时状态冲突的游标。
4. 恢复开始后将 `stop_intent` 改回 `continue`。普通会话不维护 handoff。
5. 按 phase 推进：
   - `define`：根据当前对话、代码事实与已有 draft 重建 Goal+Spec 候选包，只询问无法自行发现的阻塞问题。不边探索边增量重写三份状态；用户确认后才一次性写入并进入 work，除非用户明确要求保存新草案。
   - `work`：依据 Autonomous Decision Contract 恢复 `active_task` 中的一至两项。核对每个 Task 的真实差异和 Evidence；旧的临时 claim 不是恢复权威，重新调用实现 Agent 时由 Hook 在新会话重新认领。只有确认当前没有实现 Agent 运行时，才可用 `wali_work.py clear-claims --all-agents-stopped` 清理异常遗留认领。若 Task 已不再 `working/review`，优先修复 Work 状态。
   - `verify`：独立审查和测试，默认不改实现；需要修复时优先把 Task/Issue 状态写回 `work.md` 后返回 `work`。
   - `paused`：只处理 `waiting_for` 指向的方向、验收或外部条件。
   - `done`：只读复核；新工作使用新 Goal ID 返回 `define`。
6. 多任务时按需运行 `wali_work.py frontier` 与 `parallel`，不要把手工 handoff、旧 claim 或旧输出当成调度权威。

恢复后连续推进，不重新请求已经确认的 Goal+Spec，也不逐 Task 征求许可。只有 `Must ask` 事项才暂停。

输出当前 phase、真实差异、最后可信 Evidence、问题和唯一下一步。
