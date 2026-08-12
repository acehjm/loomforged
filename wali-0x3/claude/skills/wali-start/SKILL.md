---
name: wali-start
description: 把用户输入和代码事实编译为经确认的 Goal、实现就绪 Spec 与可连续执行的 Work。
argument-hint: "<需求描述、资料路径或对上一轮问题的回答>"
disable-model-invocation: true
---

# 目标

把 `$ARGUMENTS`、当前对话和真实代码编译为 Goal+Spec 候选包，集中确认一次后才一次性写入 `goal.md + spec.md + work.md`，并立即进入连续开发。`wali-0x3` 是 Agent 名称；不要给它编造版本名。

# 先发现，后提问

1. 读取现有 Goal、Spec、Work、用户指定资料、相关源码、测试、配置、接口与 SVN 差异。
2. 能从代码、测试、配置、历史或适用文档查明的事项必须自行查明，不询问用户。
3. 先在对话与当前上下文中形成完整候选包，不边思考边写治理文件；再识别只有用户能决定且会改变结果的阻塞问题。非阻塞、可逆、低影响细节采用符合现有项目约定的明确默认值。
4. 若有阻塞问题，在一轮中集中询问 1–3 个，并为每个问题给出证据、互斥选项、影响和建议默认值。不要逐字段访谈。
5. 若没有阻塞问题，直接展示一次 Goal+Spec 确认包；用户已有清晰规格时通常不增加澄清轮次。

# 借鉴 to-spec 的综合法

把 `to-spec` 当作对话综合方法，不当作另一条交付流程：

- Problem Statement 与 Solution 分别编译到 Goal 的背景、目标和可观察结果；Out of Scope 编译到 Goal Scope Out。
- 用紧凑的 `Behavior Scenarios` 代替冗长 User Stories，直接把 Given/When/Then 关联到 Acceptance Criteria。
- Implementation Decisions 编译到 Design Mapping；Testing Decisions 编译到 Verification Mapping。
- 保留精确项目路径，因为 Design Affected Areas 必须能授权 Work Task Scope。
- 默认不发布到 Issue Tracker，不新建重复 PRD/规格文件；只有用户明确要求时才额外发布。

# 编译 Goal

`goal.md` 只回答 why/what：目标与背景、In/Out/Constraints、`R-XXX` Requirement、`AC-XXX` Criterion 和精确验证方法。不得混入进度或低层实现细节。

# 编译 Implementation-Ready Spec

`spec.md` 回答 how，并且必须建立在代码证据上：

1. `Current System`：入口、现有行为、必须保持的约束及对应文件/测试/命令证据。
2. `Target Behavior`：正常流程、错误与边界、兼容行为和 Non-goals。
3. `Behavior Scenarios`：用 Given/When/Then 表达可观察行为，每个 AC 至少由一个正常、错误、边界或兼容场景覆盖。
4. `Design Mapping`：每个 Requirement 至少映射一个 `D-XXX`；说明接口、数据流、状态变化、失败处理和精确 Affected Areas。
5. `Verification Mapping`：每个 AC 选择现有的、能看到最完整用户行为的最高 Seam，并记录该 Seam 的可定位路径/接口、覆盖场景和可执行命令或复现步骤。
6. `Autonomous Decision Contract`：采用模板默认契约，并补充当前项目特有的 May decide / Must ask / Must not / If blocked。
7. `Open Questions`：只有真正阻塞开发的问题；成为 `implementation-ready` 前必须全部解决并写为 `none`。

保留模板中的二级标题、表头及自主契约四个英文标签，它们是 `wali_work.py` 的稳定接口。

不要为了显得完整发明架构。低风险局部任务只需足够实施的最小设计；高代价接口、迁移、安全或可靠性选择才调用 Architect 并记录方案取舍。现有最高测试 Seam 由 Agent 根据代码自主选择；只有必须新建会改变公开行为或引入高代价接口的 Seam 时，才按 Must ask 询问用户。

# 持久化时机

1. 发现、对话综合、集中阻塞问题和确认包展示期间，确认前不修改 `goal.md`、`spec.md` 或 `work.md`。仓库中已有的 draft 模板只是格式种子，不是逐步写入的草稿本。
2. 只有用户明确要求保存草案，或发生真实跨会话 handoff 时，才可在确认前做一次可恢复的 draft 持久化，并保持下列 define 状态。
3. 用户明确确认 Goal+Spec 整包后，在一个编辑回合中一次性写入 Goal、Spec 和 Work，直接建立一致的 implementation-ready/work 状态；不先落盘 Goal、再分轮补 Spec 与 Work。
4. 开发期间 Spec 默认只读。不影响 Goal、用户可观察行为或 AC 的代码事实偏差，在阶段检查点批量修正一次；实质改变则返回 define 重新确认。

仅当第 2 条的例外发生时，持久化草案保持：

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

1. 为 Goal 分配稳定 `G-XXX` ID；在同一写入回合同步持久化 Goal、Spec、Work，将 `confirmed` 设为 `true`、Spec status 设为 `implementation-ready`。
2. 在 `work.md` 为每个 AC 建立运行状态。
3. 从 Design/Verification Mapping 生成产生可观察结果所需的最少 Task。每项 Task 包含关联 AC、状态、依赖、精确 Scope、Owner、Evidence 和 Verifier。
4. 单任务不需要额外依赖设计；多任务才使用 `frontier`/`parallel` 检查。
5. 选择一个可执行 Task，将它设为 `working`，把 Work 的 `phase` 改为 `work`、`active_task` 改为该 ID。
6. 运行 `python3 .claude/hooks/wali_work.py check --checkpoint work`，同时验证 Spec 与活动 Task。
7. 立即继续实现，不因为“规格已确认”而停下来等待下一条用户消息。

# 自主执行纪律

- 落在 `May decide` 的选择由 Agent 决定并继续，不询问，不把低层选择逐项追加到 Spec。
- 新代码事实使 Behavior Scenarios、Design/Verification Mapping 不准确、但不触发 `Must ask` 时，Agent 只在阶段检查点批量修正一次 Spec、重跑检查并继续，不重新请求确认。
- 触发 `Must ask` 时，先执行 `If blocked`；仍无法安全推进才进入 `paused`，只询问一个阻塞问题。
- Goal、用户可见行为或 AC 实质变化必须返回 define 并重新确认 Goal+Spec。
- Spec 不记录进度；运行状态和 Evidence 只写 Work，普通动作不写治理文件。

# 输出

只输出当前真正需要的一项：一轮阻塞问题、Goal+Spec 确认包，或最终开发结果。确认后的中间 Task 默认自动推进，不逐项请求用户许可。
