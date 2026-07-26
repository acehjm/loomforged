---
goal_id: G-001
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
  - Skill:wali-start
  - Skill:wali-resume
  - Skill:wali-inspect
  - Skill:wali-handoff
  - Agent:coordinator
  - Agent:architect
  - Agent:developer
  - Agent:reviewer
  - Agent:tester
write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/spec.md
  - docs/wali-0x3/handoff.md
preexisting_changes:
carry_epoch: 0
carried_history:
carried_changes:
stop_intent: continue
allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
updated: YYYY-MM-DD
waiting_for: none
waiting_detail: ""
blocked_reason: ""
exit_outcome: none
exit_reason: ""
exit_evidence: ""
exit_change_disposition: none
superseded_by: none
---

# 目标契约

> 这是“为什么做、做到什么程度、当前处于什么状态”的唯一权威来源；规范性开发与测试契约由 `spec.md` 承担。当 `phase: clarifying` 时，Agent 只能读取工作区、提问并更新本文件、`spec.md` 与 `handoff.md`；不得创建其他产物或修改实现。

`allowed_capabilities` 只列出本 Goal 可调用、且项目内可检查的声明式 Skill/Agent。能力若带 lifecycle hook、动态 shell、预加载其他能力、绕过权限配置，或定义不在项目内，即使名称在列表中也会被拒绝；Task 的 `所用 Skill` 还必须是这份清单的子集。新增 Skill 文件本身不构成授权，Skill 只提供方法，不扩大 phase、effect 或 scope。`Agent:architect` 仅授权按需只读建议，不授予 Goal/Spec 或实现写入权。`preexisting_changes` 保护调用前用户修改；`carry_epoch` 标识当前冻结代次，`carried_changes` 保存当前代，`carried_history` 只追加旧代，允许修复后重新冻结而不能抹掉审计轨迹；`stop_intent: handoff` 只表示带可信交接暂停，不表示 Goal 退出。停止前还必须刷新 `handoff.md.state_digest`，使交接绑定完整 Goal、完整 Spec、交接正文、任务图与工作副本，而不是只靠人工填写“已更新”。

## 1. 输入与澄清状态

- 输入类型：待判断（`vague` / `spec` / `incremental`）
- 原始输入或规格来源：待记录
- 规格形成方式：待判断（`discovery` / `pressure_test` / `hybrid`）
- 当前澄清轮次：0
- 当前结论：尚未建立可供用户确认的 Goal

## 2. 已确认事实

<!-- 只记录用户明确给出、规格文档可直接证明或代码现状可验证的事实。 -->

- 待澄清。

## 3. 高影响未知项

只保留会改变范围、架构、兼容性、验收方式或交付风险的问题。每轮优先询问 1–3 个相关问题，已回答的问题不再重复询问。

| ID | 问题 | 为什么影响结果 | 状态 | 答案或依据 |
| --- | --- | --- | --- | --- |
<!-- | Q-001 | 需要用户决定的问题 | 它会改变什么 | open | 待回答 | -->

## 4. 决策记录

| ID | 决策 | 依据 | 影响的范围或 AC |
| --- | --- | --- | --- |
<!-- | D-001 | 已确认的方向 | 用户回答、规格条款或可验证代码事实 | 范围 / AC-01 | -->

## 5. 目标与背景

### 目标

<!-- 用一句话描述最终可观察结果，不要只写实施动作。 -->

### 背景

<!-- 说明为什么现在要做、现状与期望状态的差距。 -->

## 6. 范围与约束

### 范围

- <!-- 允许产生的行为变化和可修改区域。 -->

### 不在范围内

- <!-- 明确本轮不处理的事项。 -->

### 约束

- 不得删除、跳过或弱化测试来获得通过结果。
- 不得覆盖用户已有修改或擅自扩大 Goal。
- 未经明确授权，不得执行 SVN 提交、部署或其他外部写入。
- <!-- 技术、兼容性、安全、时间或依赖约束。 -->

## 7. 验收标准

类型只使用 `automatic` 或 `human`；状态只使用 `pending` 或 `verified`。本表保留可读摘要和运行时状态，规范性需求、精确判定规则与验证方法以 `spec.md` 为准。`verified` 必须填写真实证据。

| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
<!-- | AC-01 | automatic | 可通过命令或独立检查验证的结果 | pending | 待补充 |
| AC-02 | human | 用户真实业务回测结果可接受 | pending | 待用户验收 | -->

## 8. 检查方式

`Bash` 只能执行本表中用完整行内代码标记明确列出的项目命令；读取型的 SVN 和文件检查命令除外。

| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
<!-- | 单元测试 | `项目真实命令` | 退出码 0，相关测试全部通过 | -->

## 9. Goal + Spec 联合确认包

在请用户确认前，Coordinator 必须将下列内容汇总成一次可审阅的快照：

- 目标与背景。
- 范围、非目标和约束。
- `spec.md` 中逐项 Requirement、行为边界、接口/数据/错误约束和验收判定规则。
- 当前 Goal 适用的项目 Rules/Refs、版本、适用范围和选择结果。
- `goal.md` 中逐项验收状态模型与检查方式。
- 已确认决策、仍保留的假设与风险。
- 预计的第一个可验证垂直增量。

当前确认状态：`pending`。只有用户明确表示确认后，才能运行 `wali_policy.py digest`，把输出写入 `goal_definition_digest`，将 `goal_confirmation` 改为 `confirmed`，并在 `goal_confirmation_evidence` 记录对话依据。摘要同时绑定 Goal 的稳定定义和完整规范化 Spec，以及用户修改基线和能力清单；任何一方之后发生实质变化，策略都会要求清空确认并返回 `clarifying`。验收状态和证据可以继续更新，不会改变已确认的定义。沉默、未反对、Agent 自行概括都不算确认。

## 10. 转段、暂停与退出机制

- 存在会改变实现方向的未知项时，保持 `clarifying`，继续分轮提问。
- 用户明确联合确认 Goal + Spec 后，转入 `planning`；此时才能创建或更新 `todo.md` 和 `issues.md`。
- 需要用户做方向性决定时，转入 `phase: awaiting_direction`、`status: waiting_user`、`waiting_for: direction`，只保留 Goal 与交接写入权。
- 自动检查通过后等待业务回测时，使用 `waiting_user` + `waiting_for: acceptance`。
- 缺少权限、外部依赖或信息且无法安全绕过时，转入 `blocked` 并记录真实证据。
- 实现完成准备进入 `inspecting` 时，先运行 `wali_policy.py carry`，原子写入递增的 `carry_epoch`、只追加的 `carried_history` 和新一代 `carried_changes`；后续阶段只接受当前代指纹未变化的实现差异。审查发现问题后可回到 `implementing` 修复并生成下一代，不覆盖旧代。
- 用户提出会改变已确认 Goal 的新要求时，清空确认状态和摘要并返回 `clarifying`。
- `stop_intent: handoff` 是会话级可恢复暂停；`phase: blocked` 是 Goal 级可恢复阻断。两者都不等于退出，也不得声称完成。
- Agent 的 `idle`、`completed`、`needs_attention` 或 `failed` 是运行状态，不自动改变 Task、phase 或退出结果。存在与当前 `active_task` 绑定的未恢复失败时必须先审计 transcript、活动范围和 SVN 差异，并在 `handoff.md` 记录监督事件、恢复动作和证据；无活动任务的失败仅作为诊断事件，不虚构 Task 状态。不得自动生成替代实现、清理或提交。
- 成功退出使用 `exit_outcome: completed`，只能发生在用户业务验收和成功收尾校验成立之后；校验必须在写入终态前检查完整工作图、automatic/human AC、required Task、独立 Evidence、blocker 和实时 SVN 差异。无需 SVN 提交时进入 `closed`，需要并获准精确提交时进入 `delivering`。
- 非成功退出统一进入 `phase: terminated`，`status` 与 `exit_outcome` 使用同一个精确值：`cancelled`、`superseded` 或 `aborted`。必须同时记录退出原因、可追溯证据和未提交变更的处置方式；`superseded` 还必须记录替代 Goal ID。
- `exit_change_disposition` 只能是 `preserve`、`handoff` 或 `user_authorized_cleanup`。默认保留用户和 Agent 已有修改；任何清理、回退或删除仍需用户另行明确授权，退出本身不授予破坏性操作权限。
- 实施中退出且选择 `preserve`/`handoff` 时，先运行 `carry` 把当前合法但未完成的差异冻结为当前代，再进入 `terminated`；策略会在 PreToolUse 和 Stop 阶段拒绝带有未冻结实现差异的退出。选择清理时，必须先在原阶段按用户的具体授权完成可审计处置。
- 从任何非终态进入 `terminated`，以及从 `accepting` 进入成功终态，都必须由 PreToolUse 再次向用户请求当场确认。取消、替代和安全中止不得通过补齐假证据伪装成 `completed`。
- `delivering` 在提交前仍有授权差异时，可经用户确认撤销提交准备：清除 `svn_commit_paths`/`svn_commit_evidence`，让原 Goal 回到 `clarifying`。授权路径已清洁但交付回执无效时不得复活原 Goal，必须查明后进入 `terminated`；精确提交和有效回执完成后，`delivering` 与 `closed` 一样冻结。
- `closed`、`terminated` 和已完成交付的 `delivering` 冻结当前 Goal。开始下一项工作只能用不同 Goal ID 发起受确认的重置事务；`superseded` 的新 ID 必须等于 `superseded_by`。新契约必须使用最小 `clarifying` 权限，`carry_epoch: 0`，清空 `carried_history`、`carried_changes`、旧能力和 SVN 提交授权，并把当前全部非治理 SVN 差异重新写入 `preexisting_changes` 作为不可修改的用户保护基线。
- 新 Goal 写入后，身份不一致期间 Policy 只开放固定 `spec.md` 的身份修复，使 `spec_id` 等于 `SPEC-<新 Goal ID>`、`goal_id` 与新 Goal 一致；完成身份修复后还必须刷新 handoff，Stop 才会放行。旧 Goal 的 carry 不会自动成为新 Goal 的实现授权。

## 11. `/goal` 条件草案

```text
/goal 持续工作，直到：
1. 当前阶段的 automatic 验收条件均为 verified 且有真实证据。
2. todo.md 中所有 required 任务为 done，且每个 done Task 都有执行证据和不同于负责人的独立验证者。
3. issues.md 中不存在未关闭的 blocker。
4. 已运行 Goal 规定的构建、测试和静态检查，并展示命令与结果。
5. 已检查 SVN 差异，没有越过当前阶段和活动任务的写入范围。
6. 已逐项展示 Requirement → AC → Task → Evidence 追踪关系；需要业务验收时转入 accepting。
7. 仅在成功条件全部满足时以 completed 退出；用户取消、Goal 被替代或安全策略阻止继续时，以带原因、证据和变更处置的 terminated 退出。
不得删除、跳过或弱化测试，不得擅自扩大范围。暂时无法继续时记录真实阻断并交接，不把暂停冒充退出。
```
