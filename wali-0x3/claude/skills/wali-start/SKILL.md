---
name: wali-start
description: 把用户输入和代码事实编译为经确认的 Goal、实现就绪 Spec 与可连续执行的 Work。
argument-hint: "<需求描述、资料路径或对上一轮问题的回答>"
disable-model-invocation: true
---

# 目标

把 `$ARGUMENTS`、当前对话和真实代码编译为 `goal.md + spec.md`，集中确认一次后建立 `work.md` 并立即进入连续开发。`wali-0x3` 是 Agent 名称；不要给它编造版本名。

# 先发现，后提问

1. 读取现有 Goal、Spec、Work、用户指定资料、相关源码、测试、配置、接口与 SVN 差异。
2. 能从代码、测试、配置、历史或适用文档查明的事项必须自行查明，不询问用户。
3. 先形成完整草案，再识别只有用户能决定且会改变结果的阻塞问题。非阻塞、可逆、低影响细节采用符合现有项目约定的明确默认值。
4. 若有阻塞问题，在一轮中集中询问 1–3 个，并为每个问题给出证据、互斥选项、影响和建议默认值。不要逐字段访谈。
5. 若没有阻塞问题，直接展示一次 Goal+Spec 确认包；用户已有清晰规格时通常不增加澄清轮次。

# 编译 Goal

`goal.md` 只回答 why/what：目标与背景、In/Out/Constraints、`R-XXX` Requirement、`AC-XXX` Criterion 和精确验证方法。不得混入进度或低层实现细节。

# 编译 Implementation-Ready Spec

`spec.md` 回答 how，并且必须建立在代码证据上：

1. `Current System`：入口、现有行为、必须保持的约束及对应文件/测试/命令证据。
2. `Target Behavior`：正常流程、错误与边界、兼容行为和 Non-goals。
3. `Design Mapping`：每个 Requirement 至少映射一个 `D-XXX`；说明接口、数据流、状态变化、失败处理和精确 Affected Areas。
4. `Verification Mapping`：每个 AC 对应测试层级、关键场景和可执行命令或复现步骤。
5. `Autonomous Decision Contract`：采用模板默认契约，并补充当前项目特有的 May decide / Must ask / Must not / If blocked。
6. `Open Questions`：只有真正阻塞开发的问题；成为 `implementation-ready` 前必须全部解决并写为 `none`。

保留模板中的二级标题、表头及自主契约四个英文标签，它们是 `wali_work.py` 的稳定接口。

不要为了显得完整发明架构。低风险局部任务只需足够实施的最小设计；高代价接口、迁移、安全或可靠性选择才调用 Architect 并记录方案取舍。

Define 期间保持：

```yaml
# goal.md
agent: wali-0x3
confirmed: false

# spec.md
agent: wali-0x3
status: draft

# work.md
phase: define
active_task: none
stop_intent: continue
waiting_for: none
outcome: none
```

# 建立 Work

向用户展示的确认包必须自包含地概括 Goal、目标行为、设计映射、验证计划、自主边界和仍需用户决定的事项。用户明确确认的是 Goal+Spec 整包；沉默和 Agent 自己总结都不是确认。

确认后：

1. 为 Goal 分配稳定 `G-XXX` ID；同步写入 Goal、Spec、Work，将 `confirmed` 设为 `true`、Spec status 设为 `implementation-ready`。
2. 在 `work.md` 为每个 AC 建立运行状态。
3. 从 Design/Verification Mapping 生成产生可观察结果所需的最少 Task。每项 Task 包含关联 AC、状态、依赖、精确 Scope、Owner、Evidence 和 Verifier。
4. 单任务不需要额外依赖设计；多任务才使用 `frontier`/`parallel` 检查。
5. 选择一个可执行 Task，将它设为 `working`，把 Work 的 `phase` 改为 `work`、`active_task` 改为该 ID。
6. 运行 `python3 .claude/hooks/wali_work.py check --checkpoint work`，同时验证 Spec 与活动 Task。
7. 立即继续实现，不因为“规格已确认”而停下来等待下一条用户消息。

# 自主执行纪律

- 落在 `May decide` 的选择由 Agent 决定并继续，不询问，不把低层选择逐项追加到 Spec。
- 新代码事实使 Design/Verification Mapping 不准确、但不触发 `Must ask` 时，Agent 可一次性修正 Spec、重跑检查并继续，不重新请求确认。
- 触发 `Must ask` 时，先执行 `If blocked`；仍无法安全推进才进入 `paused`，只询问一个阻塞问题。
- Goal、用户可见行为或 AC 实质变化必须返回 define 并重新确认 Goal+Spec。
- Spec 不记录进度；运行状态和 Evidence 只写 Work，普通动作不写治理文件。

# 输出

只输出当前真正需要的一项：一轮阻塞问题、Goal+Spec 确认包，或最终开发结果。确认后的中间 Task 默认自动推进，不逐项请求用户许可。
