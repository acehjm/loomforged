---
name: wali-start
description: 通过开放式访谈或规格压力测试，把输入收敛为经用户联合确认的 WALI Goal 与 Spec，再建立可执行工作图。
argument-hint: "<需求描述、规格路径或对上一轮问题的回答>"
disable-model-invocation: true
---

# 目标

将 `$ARGUMENTS` 与当前对话收敛为用户真正理解并明确确认的一组 Goal + Spec。Goal 说明意图、范围、状态和验收摘要；Spec 说明规范需求、行为、接口/数据/错误约束与测试判定。无论用户是否提供规格，都必须形成 `spec.md`；但不将“用户给了规格”当作“规格已经完整”，也不要求用户一次性按模板写完所有字段。

本 Skill 是可恢复的状态机。每次调用都从 `goal.md`、`spec.md` 和 `handoff.md` 读取上一轮游标，纳入新信息后只推进一个合法转段。

# 始终适用的边界

- 开始时读取 `CLAUDE.md`、五个 WALI 状态文件、用户在项目 `docs/` 指定的资料、相关代码和项目配置；只做读取型 SVN 检查。
- `clarifying` 阶段只允许更新固定存在的 `goal.md`、`spec.md` 和 `handoff.md`。不改 `todo.md`、`issues.md` 或实现，不创建其他产物。
- 不运行会默认生成上下文、计划、进度、规格或图文件的黑盒流程。可采用其访谈和拆解方法，但持久化只由 WALI 写入当前契约允许的文件。
- Skill、Agent、脚本或工具的名称不决定权限。它们之后的每个实际工具动作仍必须符合当前 `allowed_effects`、`write_scope` 和四个布尔开关。
- 只能调用 `allowed_capabilities` 中列出且定义位于项目内的声明式能力；含 lifecycle hook、动态 shell 或绕过权限配置的能力默认拒绝。这个规则适用于任何现有或未来 Skill，不维护名称黑名单。
- 现有 Goal 为 `active`、`waiting_user` 或 `blocked` 时，不静默覆盖。先说明新输入是对当前 Goal 的补充、变更还是新 Goal；关系不明时请用户决定。

# 状态机

## A. 建立澄清契约

新 Goal 或会改变已确认 Goal 的输入，先进入下列状态：

```yaml
status: draft
phase: clarifying
active_task: none
goal_confirmation: pending
goal_confirmation_evidence: ""
goal_definition_digest: ""
allowed_effects:
  - read_workspace
  - ask_user
  - update_goal_draft
  - update_spec_draft
  - update_handoff
allowed_capabilities:
  # 只列出本 Goal 确实需要的项目内声明式 Skill/Agent
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/spec.md
  - docs/wali-0x3/handoff.md
preexisting_changes:
carry_epoch: 0
carried_history:
carried_changes:
stop_intent: continue
waiting_for: none
waiting_detail: ""
blocked_reason: ""
exit_outcome: none
exit_reason: ""
exit_evidence: ""
exit_change_disposition: none
superseded_by: none
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
```

将输入分类并记入 `goal.md`：

- `vague`：只有意图、想法或问题，采用 `source_mode: discovery` 的开放式访谈，从目标用户、场景、期望结果、边界、失败语义和验收证据逐步收敛。
- `spec`：用户提供了接口文档、需求或规格，采用 `source_mode: pressure_test`，验证缺失、歧义、冲突、代码不一致和不可测试条款，不照抄输入。
- `incremental`：对现有已确认 Goal 的补充或变更。如果会影响范围、AC、检查方式或风险，必须撤销原确认并重新澄清。

输入既有明确条款又有关键空白时使用 `source_mode: hybrid`。三条路径最终都必须把来源、结论和约束编译为同一结构的 `spec.md`，原始文档只作为来源证据，不成为与 Spec 竞争的第二权威来源。

在 SVN 工作副本中运行 `python3 .claude/hooks/wali_policy.py baseline`，将输出的路径、内容与 SVN 属性指纹保存到 `preexisting_changes`。命令会排除当前已授权的 WALI 状态文件。其余记录只在对应内容和属性保持不变时被视为用户既有资产；之后的任何变化仍会被 SVN 差异审计报告。如果已确认 Goal 必须修改其中某个用户文件，先请用户明确授权接管该路径；改变这份基线会使 Goal 定义摘要失效并要求重新确认。

## B. 提取事实并分析缺口

1. 分别记录“已确认事实”、“合理但未确认的假设”和“冲突”，不把推断写成用户决定。
2. 读取现有代码、测试和配置，验证规格假定的接口、数据、兼容性和真实命令。
3. 对 `spec` 输入逐项做五类压力测试：缺失、歧义、内部冲突、与实际代码冲突、无法形成可判定测试。规格详细不等于可验收。
4. 核对用户在项目 `docs/` 提供的资料路径、版本或日期、适用范围和真实代码，把采用结论写入 `spec.md`。同时读取 `refs/INDEX.md`，按角色和场景识别跨项目稳定资料与通用 Rules。项目特殊约束继续留在 `docs/` 并由 Spec 规范化，不复制进共享 Ref。
5. 将问题按影响排序：先处理会改变用户结果、范围、数据或架构、兼容性、安全和验收的问题。
6. 可安全逆转、不影响 Goal 的细节由 Coordinator 给出默认建议，明确标为假设，不用琐碎问题消耗用户。
7. 只有跨模块边界、接口/数据迁移、重要质量属性或高代价技术分歧会实质改变 Goal/Spec 时，才按需调用已获授权的只读 Architect。它只返回作用力、方案比较、验证/迁移/回滚建议和待确认项；Coordinator 负责整合，Architect 不直接写 Goal、Spec 或额外设计产物。

## C. 多轮询问

每轮只询问 1–3 个主题相关、当前影响最大的问题。每个问题应说明：

- 需要用户决定什么。
- 不同答案会改变什么。
- 若有推荐方案，说明推荐理由和代价。

收到回答后：

1. 先将回答合并到 Goal 的已确认事实、决策记录、范围或 AC 摘要，并同步写入 Spec 的 Requirement、行为边界或判定规则。
2. 把已回答问题标记为 `resolved`，不再重复提问。
3. 更新 `handoff.md` 的轮次、最后纳入回答、下一轮问题和仍存在的冲突，并在本轮状态写入结束后用 `handoff-digest` 刷新 `state_digest`。
4. 重新评估高影响未知项；如果仍存在，只进入下一轮询问，不提前规划或编码。

## D. 编译 Spec 并生成联合确认包

没有未解决的高影响问题后，先完成 `spec.md`，再向用户展示一份自包含的 Goal + Spec 联合确认包：

1. 一句话 Goal 和背景。
2. 范围、非范围和约束。
3. `spec.md` 中逐项 `R-XXX` Requirement、来源和关联 AC。
4. 行为、边界、接口、数据、错误、质量与兼容约束；不适用项也要说明理由。
5. 每个 AC 唯一对应的规范性判定规则与验证方法，以及从项目真实配置发现的精确检查命令。
6. 已确认决策、保留假设和已知风险。
7. 预计的第一个可验证垂直增量，但此时不写 `todo.md`。
8. 一个明确确认请求：请用户共同确认 Goal 与 Spec、指出需修改处，或补充仍缺失的条件。

请求确认时仍保持 `status: draft`、`phase: clarifying`、`goal_confirmation: pending`。不得把“已经总结”当作“已经确认”。

## E. 处理用户确认

只有用户对当前确认包给出明确肯定，才能执行以下变更；pending → confirmed 的 PreToolUse 仍必须请求用户核对该次原子写入，`goal_confirmation_evidence` 本身不充当授权令牌：

1. 运行 `python3 .claude/hooks/wali_policy.py digest`，将输出写入 `goal_definition_digest`；该摘要绑定稳定 Goal 定义、完整规范化 Spec、用户修改基线与能力清单，不绑定后续会变化的验收状态和证据。
2. 在 `goal_confirmation_evidence` 记录时间、确认对象和可追溯的对话依据；不伪造用户原话。
3. 将 Goal 转入 `planning`，并严格改为以下契约：

```yaml
status: active
phase: planning
active_task: none
goal_confirmation: confirmed
goal_definition_digest: "<digest 命令输出>"
allowed_effects:
  - read_workspace
  - ask_user
  - update_goal
  - update_todo
  - update_issues
  - update_handoff
allowed_capabilities:
  # 保留用户确认时的精确清单
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/todo.md
  - docs/wali-0x3/issues.md
  - docs/wali-0x3/handoff.md
preexisting_changes:
  # 保留 clarifying 阶段记录的真实路径与指纹条目
carry_epoch: 0
carried_history:
carried_changes:
stop_intent: continue
waiting_for: none
waiting_detail: ""
blocked_reason: ""
exit_outcome: none
exit_reason: ""
exit_evidence: ""
exit_change_disposition: none
superseded_by: none
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
```

如果用户修改了确认包，先将修改纳入 Goal，检查是否引入新的高影响问题；有问题就继续 `clarifying`，不把“带修改意见的回复”当作确认。任何已确认定义的实质变更都必须清空确认依据和摘要后重新澄清。

## F. 规划并交出可实施入口

只在 `planning` 中：

1. 选择可靠完成 Goal 的最简单执行方式：主会话、单个 Subagent、Agent Teams 或顺序执行。
2. 从 `spec.md` 的 Requirement → AC 关系出发，在 `todo.md` 建立单会话可验证的垂直任务；每项标明 AC、依赖、负责人、必要性、精确写入范围、所用 Skill（无则写“无”）和任务验收条件，形成 Requirement → AC → Task → Evidence。Task 中的 `Skill:<name>` 必须已经列入 Goal 的 `allowed_capabilities`；它只建立方法关系，不扩大权限。
3. 保留 `issues.md` 中仍有效的问题；不为了新 Goal 静默删除未关闭记录。
4. 运行阶段契约和工作图检查，计算当前可执行前沿与安全并行候选。
5. 更新 `handoff.md`，记录 SVN 基线、调用前已有本地修改、真实项目命令、工作图摘要和第一项可执行任务，并用 `handoff-digest` 刷新 `state_digest`。
6. 选定一个前沿任务后，才将 Goal 转入 `implementing`，将 `active_task` 设为该 `T-XXX`，`write_scope` 使用 `@active_task`。本 Skill 到此交出，不在同一步内偷偷实施代码。

只有用户才能决定的高影响问题不伪装成 `blocked` 或 `accepting`：转入 `awaiting_direction`，设置 `waiting_for: direction` 与具体 `waiting_detail`，只保留 `goal.md` 和 `handoff.md` 的写入权。用户回答后回到与确认状态相符的 `clarifying` 或后续阶段。

# 输出

根据当前状态只输出其中一种：

- 下一轮 1–3 个高影响问题，附影响与推荐。
- 完整 Goal + Spec 联合确认包和明确确认请求。
- 用户确认后的规划结果：执行方式、工作图检查、第一个活动任务及其精确写入范围。

不得在高影响未知项未解决、Goal + Spec 未联合确认或阶段契约检查未通过时开始编码。

用户要求取消当前 Goal、用新 Goal 替代当前 Goal，或安全/策略冲突使其不应继续时，不补写虚假完成证据。先让 `status` 与 `exit_outcome` 同为 `cancelled`、`superseded` 或 `aborted`，记录原因、证据和未提交变更处置，必要时记录替代 Goal ID，再请求用户当场确认进入 `terminated`。`blocked` 和 `stop_intent: handoff` 只是可恢复暂停，不是退出。冻结终态启动新 Goal 时不得继承旧 carry、能力或提交授权；使用不同 Goal ID 建立全新治理代次，把当前非治理 SVN 差异重新纳入 `preexisting_changes`，再修复固定 Spec 身份与 handoff。
