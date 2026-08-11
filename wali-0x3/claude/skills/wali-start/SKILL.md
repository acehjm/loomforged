---
name: wali-start
description: 把用户输入收敛为经确认的 wali-0x3 Goal，并建立最小可执行 Work。
argument-hint: "<需求描述、资料路径或对上一轮问题的回答>"
disable-model-invocation: true
---

# 目标

把 `$ARGUMENTS` 和当前对话收敛到 `goal.md`，并在用户确认后于 `work.md` 建立最小执行入口。`wali-0x3` 是 Agent 名称；不要给它编造版本名。

# Define

1. 读取现有 `goal.md`、`work.md`、用户指定资料、相关代码和真实项目配置。
2. 输入模糊时做开放式访谈；用户已有规格时检查缺失、歧义、冲突、代码不一致和不可测试条款。
3. 每轮只问 1–3 个会改变结果的高影响问题。回答留在对话中即可；不要为了每轮问答重写 handoff。
4. 将稳定结论写入 `goal.md`：目标与背景、In/Out/Constraints、`R-XXX` Requirement、`AC-XXX` Criterion 和精确验证方法。
5. 可安全逆转的低影响细节作为显式假设，不把所有决定推给用户。
6. 向用户展示自包含确认包。沉默和 Agent 自己总结都不是确认。

Define 期间保持：

```yaml
# goal.md
agent: wali-0x3
confirmed: false

# work.md
phase: define
active_task: none
stop_intent: continue
waiting_for: none
outcome: none
```

# 建立 Work

用户明确确认后：

1. 为 Goal 分配稳定 `G-XXX` ID，将 `confirmed` 设为 `true`。
2. 在 `work.md` 为每个 AC 建立运行状态。
3. 只建立产生可观察结果所需的 Task。每项 Task 包含关联 AC、状态、依赖、精确 Scope、Owner、Evidence 和 Verifier。
4. 单任务不需要额外依赖设计；多任务才使用 `frontier`/`parallel` 检查。
5. 运行 `python3 .claude/hooks/wali_work.py check --checkpoint work`。
6. 选择一个可执行 Task，将它设为 `working`，把 Work 的 `phase` 改为 `work`、`active_task` 改为该 ID。

只有高影响方向仍需用户决定时，进入 `paused` 并设置 `waiting_for: direction`。不要用额外状态文件代替用户回答。

# 输出

只输出当前真正需要的一项：下一轮问题、Goal 确认包，或确认后的首个活动 Task。不要在 Goal 未确认时实施代码。
