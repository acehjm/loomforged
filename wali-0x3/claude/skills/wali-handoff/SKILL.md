---
name: wali-handoff
description: 仅在确实需要跨会话恢复时创建最小、可信的 wali-0x3 交接游标。
disable-model-invocation: true
---

普通停止不要调用本 Skill。

显式交接时：

1. 运行 `wali_policy.py check`，检查真实代码、测试结果、`svn status` 和 `svn diff --internal-diff`。
2. 先使 `work.md` 与真实 Task、Issue、Acceptance 和 Evidence 一致。
3. 创建或覆盖 `docs/wali-0x3/handoff.md`：

```markdown
---
goal_id: G-XXX
phase: work
active_task: T-XXX
updated: <ISO 时间>
---

# Handoff

## Current State

- 已完成、当前差异、最近验证和风险。

## Next Step

- 一个具体、可执行的下一步。
```

4. handoff 不复制完整 Goal/Spec/Work，不写摘要哈希，不追加进度历史。
5. 最后把 `work.md` 的 `stop_intent` 设为 `handoff`，运行 `wali_stop.py --project-root .`。
6. 在对话中输出同一份精简交接。恢复后由 `/wali-resume` 将 `stop_intent` 改回 `continue`。
