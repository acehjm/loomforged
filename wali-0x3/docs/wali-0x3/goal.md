---
wali_schema: 1
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

本文件回答“为什么做、做到什么程度、现在允许做什么”。规范性实现与测试依据写入 `spec.md`；阶段转换和退出细节由 Policy Hook 校验，操作说明按需读取 `.claude/refs/operations.md`。

## 1. 输入与澄清状态

- 输入类型：待判断（`vague` / `spec` / `incremental`）
- 原始输入或规格来源：待记录
- 规格形成方式：待判断（`discovery` / `pressure_test` / `hybrid`）
- 当前澄清轮次：0
- 当前结论：尚未建立可供用户确认的 Goal

## 2. 已确认事实

<!-- 只记录用户明确说明、来源资料直接证明或代码现状可验证的事实。 -->

- 待澄清。

## 3. 高影响未知项

每轮只保留会改变范围、架构、兼容性、验收方式或交付风险的 1–3 个问题。

| ID | 问题 | 为什么影响结果 | 状态 | 答案或依据 |
| --- | --- | --- | --- | --- |
<!-- | Q-001 | 需要用户决定的问题 | 它会改变什么 | open | 待回答 | -->

## 4. 决策记录

| ID | 决策 | 依据 | 影响的范围或 AC |
| --- | --- | --- | --- |
<!-- | D-001 | 已确认方向 | 用户回答、规格条款或代码事实 | 范围 / AC-01 | -->

## 5. 目标与背景

### 目标

<!-- 用一句话描述最终可观察结果，不要只写实施动作。 -->

### 背景

<!-- 说明现状、期望状态以及为什么现在需要改变。 -->

## 6. 范围与约束

### 范围

- <!-- 允许产生的行为变化和可修改区域。 -->

### 不在范围内

- <!-- 本轮明确不处理的事项。 -->

### 约束

- 不删除、跳过或弱化测试来获得通过结果。
- 不覆盖用户已有修改，不擅自扩大 Goal。
- 未经明确授权，不执行 SVN 提交、部署或其他外部写入。
- <!-- 技术、兼容性、安全、时间或依赖约束。 -->

## 7. 验收标准

类型只使用 `automatic` 或 `human`，状态只使用 `pending` 或 `verified`。精确判定规则在 `spec.md`；`verified` 必须填写真实证据。

| ID | 类型 | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
<!-- | AC-01 | automatic | 可通过命令或独立检查验证的结果 | pending | 待补充 |
| AC-02 | human | 用户真实业务回测结果可接受 | pending | 待用户验收 | -->

## 8. 检查方式

项目命令必须以完整行内代码精确记录；读取型 SVN 和文件检查命令除外。

| 检查 | 命令或方法 | 通过条件 |
| --- | --- | --- |
<!-- | 单元测试 | `项目真实命令` | 退出码 0，相关测试全部通过 | -->

## 9. Goal + Spec 联合确认

确认前汇总目标与背景、范围与非目标、约束、Requirement、行为与接口/数据/错误契约、验收判定规则、检查方式、适用 Rules/Refs、决策、风险和第一个可验证增量。

当前确认状态：`pending`。用户明确确认后运行 `wali_policy.py digest`，写入 `goal_definition_digest`、`goal_confirmation: confirmed` 和可追溯的 `goal_confirmation_evidence`。Goal 或 Spec 的稳定定义变化后必须撤销确认并返回 `clarifying`；沉默和 Agent 自行概括不算确认。
