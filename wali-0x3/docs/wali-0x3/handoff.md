---
updated: 2026-07-26T15:46:39+08:00
goal_id: G-001
phase: clarifying
active_task: none
goal_confirmation: pending
clarification_round: 0
stop_intent: continue
supervision_event: none
recovery_action: none
recovery_evidence: ""
state_digest: "f7ca9fa4c27ecdcc2a6303e10e780e6d0de1537c36d3cd3a8e0f4ac10920e238"
---

# 可恢复交接

> 本文件是会话恢复游标，始终覆盖为最新快照，不保存进度日志。`goal.md` 对 Goal 和阶段契约具有最终权威，`spec.md` 对开发与测试规范具有最终权威；本文件中的阶段字段只是便于恢复的镜像。

`state_digest` 由 `wali_policy.py handoff-digest` 生成，绑定完整 Goal（含 AC 状态与证据）、完整规范化 Spec、任务图、交接正文和工作副本状态。更新交接正文后最后刷新该值；计算时只排除 `state_digest` 自身和 Goal 的 `stop_intent`，因此可以先完成交接再把停止意图改为 `handoff`。

## 当前状态

- 当前阶段：`clarifying`
- 活动任务：无
- Goal 确认：`pending`
- Goal 定义摘要：未生成
- 停止意图：`continue`；需要中断但尚未完成时改为 `handoff`
- 退出结果：`none`；当前不是 Goal 退出
- 当前编写权：只能更新 `goal.md`、`spec.md` 与 `handoff.md`
- 下一个转段条件：用户明确确认 Goal + Spec 联合确认包

## 澄清游标

- 输入类型：待判断
- 已完成轮次：0
- 最后纳入的用户回答：无
- 当前已确认理解：尚未建立
- Spec 形成方式：待判断；无资料时开放式访谈，有资料时规格压力测试，资料明确但仍有关键空白时使用 hybrid
- 下一轮高影响问题：待从用户输入、规格和代码现状中提取
- 仍未解决的假设或冲突：待核对

## 最近完成

- 已建立固定 `spec.md`、Goal + Spec 联合确认和 `discovery` / `pressure_test` / `hybrid` 三种收敛入口。
- 已补齐 Goal 退出机制，区分 handoff、blocked、completed、cancelled、superseded 与 aborted。
- 已实现成功收尾前置校验、提交后 delivering 冻结、新 Goal 全新治理代次、全阶段 Spec 身份一致和 Requirement → AC → Task → Evidence 证据不变量。
- 已将 SVN 工作副本根识别改为基于 `svn info`，普通子目录中的有副作用动作、直接读取 SVN 状态的 baseline/carry/audit、摘要和 Stop 均拒绝。
- 已接入人维护的原生 `svn:ignore` / `svn:global-ignores`：状态读取清空个人客户端 `global-ignores`，只有属性链没有本地修改的项目本地产物不进入 baseline、carry、handoff 摘要、Stop 或提交差异，普通未版本化项和属性变化继续审计；WALI 不自动 `propset`。
- 已将知识分层纠正为“跨项目参考—项目资料”：Refs 保存低频变化的 WALI 说明、共享开发模板和企业内部代码检查基线，并由 `refs/INDEX.md` 按角色与场景路由。项目特有资料仍保留在项目 `docs/`，采用结论和例外编译进 `spec.md`。
- 已实现 Skill 的“项目内定义 → Goal 授权 → Task `所用 Skill` → 实际动作检查”链路；工作图验证未授权 Skill 并派生 Skill → Task 方法边，Reviewer 也具备受约束的 Skill 工具。
- 已实现 Agent 监督与异常恢复协议、本地运行事件记录、异常恢复交接校验，以及 `TeammateIdle`、`TaskCompleted`、`StopFailure` 三类 Hook。
- 已新增按需启用、默认只读且不拥有 Goal/Spec 的 Architect Agent。
- 已为五个角色配置 model/effort：Coordinator `opus/high`、Architect `opus/xhigh`、Reviewer `opus/high`、Developer 与 Tester `sonnet/high`；主会话默认也使用 `opus/high`，并明确 Agent Teams 的 effort 继承限制。
- 已将 `CLAUDE.md` 从 237 行压缩为 84 行，删除重复的无条件 collaboration/supervision Rules；详细操作与兼容说明改为按需 Refs，工程和测试 Rules 继续按路径加载。
- 已将 `goal.md` 模板从 173 行压缩为 130 行，保留人类需要确认的事实、未知项、目标、范围、AC、检查方式和确认包，移除重复的转段与退出手册。
- 已增加 `wali_schema: 1`、兼容能力清单和 fail-closed 版本检查；Policy、Stop 与监督事件都不会接受未知或缺失 schema，也不会静默迁移。
- 已将监督并发控制改为持久文件配合操作系统建议锁；内核会在正常结束或崩溃时释放锁，诊断元数据不参与所有权判断，存活持锁者不可强占，也不再需要递归的陈旧锁回收标记。
- 已提取共享 `wali_svn.py` 公共边界，Stop 与监督不再导入 Policy 私有 SVN 函数。按用户决定，五个测试文件继续保留在 `claude/hooks/` 原位。

## 当前工作

- 当前任务：根据用户输入共同建立可确认的 Goal 与固定 Spec
- 负责人：Coordinator
- 允许的行为：读工作区、提问、更新 Goal 草案、Spec 草案和本交接

## Agent 监督与恢复

- 当前运行事件：无；`supervision_event: none`
- 当前恢复动作：无；`recovery_action: none`
- 当前恢复证据：无
- 监督状态来源：Claude `/tasks`/Agent 面板、transcript、`wali_supervision.py status`、WALI Task 和 SVN 差异交叉核对
- 异常处置：优先恢复原 Agent；替代前冻结 Task/路径所有权并审计已有差异，不自动清理、覆盖或提交

## SVN 与工作副本

- 工作副本 URL：待记录
- 工作副本修订：待记录（若为混合修订，记录范围）
- 当前存档说明：本设计目录自身由 Git 保存；这里只验证文件与 Hook，不把 Git 当成目标运行时。部署后的 Agent 环境只支持 SVN。
- 基准修订号：待记录
- 调用前已存在的本地修改：待记录，视为用户资产
- 当前 SVN 差异：待记录
- 当前 carry 代次：0
- carry 历史：无；每次修复后生成新代，上一代不可覆盖并转入 `carried_history`
- 当前代阶段继承指纹：无；实现转入检查前由 `wali_policy.py carry` 生成
- 文件所有权：`goal.md`、`spec.md` 和 `handoff.md` 由 Coordinator 维护；实现文件未授权

## 最近验证

| 时间 | 命令/方法 | 退出结果 | 摘要 | 关联 AC/任务 |
| --- | --- | --- | --- | --- |
| 2026-07-26T15:46:39+08:00 | `python3 -m unittest -q test_wali_graph.py test_wali_policy.py test_wali_stop.py test_wali_supervision.py test_wali_svn.py`；Policy、工作图、设置 JSON、Python 编译与 `git diff --check` | 0 | 162 项回归通过；可信原生 Ignore、属性链变更回退审计、本地产物分类和既有控制面行为有效 | WALI 控制面 |

## 已知问题与风险

- 当前模板 Goal + Spec 尚未经具体项目用户确认，不得拆分实施任务或编码。
- 已为静态共享参考建立 `refs/templates/` 与 `refs/compliance/` 两个集合及扩展说明，尚未预置具体模板或检查条目。它们不是 Skill：Developer 读取前者和后者，Reviewer 只读取后者；项目特殊要求仍由 `docs` 与 Spec 定义。
- Agent Teams teammate 的 `effort` 继承 lead，不采用各自 Agent frontmatter；只需 Architect 使用 `xhigh` 时必须把它作为独立 Subagent。实际模型和 effort 还可能受命令行、环境变量或组织上限覆盖，应以运行界面显示为准。
- 当前 Git 存档环境没有安装 SVN CLI，因此原生 Ignore 的命令组合通过替代进程结果和 XML 行为测试验证；部署时仍须按兼容清单在真实 SVN 1.9+ 工作副本核对。
- 本存档继续把五个测试文件放在 `claude/hooks/`；它们不在 Hook 配置中，不会自动执行，但会随部署包保留。该取舍是用户明确决定，不再迁移。

## 工作图摘要

- 当前可执行任务：无；澄清阶段不建立实施任务。
- 安全并行候选：无。
- 本轮关系变化：无。

## 恢复步骤

1. 确认当前目录就是 SVN 工作副本根，运行只读的 `svn info`、`svn status`、`svn diff --internal-diff` 并核对近期 `svn log`。
2. 读取五个 WALI 状态文件，并运行 `wali_supervision.py status`；活动任务存在未恢复失败时先按事件 ID、恢复动作和证据处理。
3. 在 `clarifying` 阶段不改动 `todo.md`、`issues.md` 或实现；将用户最新回答纳入 Goal 的事实与决策，并同步编译进 `spec.md` 的 Requirement、行为和判定规则。
4. 选择 1–3 个最高影响未知项继续询问；无高影响未知项时，生成 Goal + Spec 联合确认包。
5. 只在用户明确确认联合确认包后转入 `planning`。
