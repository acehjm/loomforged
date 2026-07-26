# wali-0x3 项目约定

WALI（Work · Assign · Loop · Inspect）用于让 Claude Code 开发工作可分派、可检查、可恢复、可验收。

本仓库是可见存档，配置目录必须保留为 `claude/`；使用者部署到目标项目时自行改名为 `.claude/`。目标运行环境只使用 SVN，文中的 `.claude/...` 均指部署路径。

## 权威状态

`docs/wali-0x3/` 中五个文件共同保存项目状态：

- `goal.md`：意图、范围、AC、确认状态和当前阶段契约。
- `spec.md`：Requirement、行为、接口/数据/错误约束和验收判定规则。
- `todo.md`：任务、依赖、负责人、修改范围和执行证据。
- `issues.md`：审查、测试和用户问题的闭环。
- `handoff.md`：覆盖式恢复游标，不保存进度历史。

`goal.md` 必须声明当前支持的 `wali_schema: 1`。默认不创建其他上下文、计划、进度、记忆或图副本；额外产物必须已被确认的 Goal 纳入范围并由当前阶段授权。

Rules 保存跨项目硬约束，Refs 保存跨项目稳定、按角色和场景读取的 WALI 说明、开发模板与代码检查基线，Skills 保存可重复流程。具体项目的需求、接口、模块和特殊约束保留在项目 `docs/`，其可执行结论编译进 `spec.md`。这些层都不自动改变 Goal、phase、effect 或写入范围。

## 启动与恢复

1. 确认当前目录是 SVN 工作副本根，读取 `svn info`、`svn status`、`svn diff --internal-diff` 和近期 `svn log`；可用时再运行 `svn status -u`。
2. 读取五个 WALI 状态文件。
3. 运行 `python3 .claude/hooks/wali_policy.py check`。
4. 运行 `python3 .claude/hooks/wali_supervision.py --project-root . status`。
5. 用真实代码、SVN 差异和最新验证结果核对记录；差异仍只能按当前权限修正。
6. 把调用前已有或来源不明的修改视为用户资产，不覆盖、不回退、不擅自纳入任务。
7. 新 Goal 开始澄清时运行 `wali_policy.py baseline`，记录受保护的既有差异指纹。

## 核心约束

- Goal 与 Spec 先于计划。模糊需求使用开放式访谈，已有资料使用规格压力测试；两者都由 `/wali-start` 收敛为固定 `spec.md`，经用户联合确认后才能规划和实现。
- 每次行动前读取完整阶段契约。`phase` 只是索引，实际权限由契约字段、活动任务和 Hook 共同决定。
- 阶段转换必须原子更新完整契约并通过 Policy；不得单独修改 `phase`、scope 或布尔开关。
- Skill、Agent、脚本和工具只提供能力，不提供授权。副作用未知、能力未授权或写入越界时默认拒绝。
- Graph Engineering 工作图只从五个 Markdown 状态文件派生；不创建图数据库、GraphRAG 索引或持久图副本。
- 主追踪链为 Requirement → AC → Task → Evidence。Task 和 Issue 必须按状态机闭环，完成任务必须有执行证据和独立验证者。
- 一个 Agent 同时只拥有一个主要任务；并行写入必须使用范围互斥的独立 SVN 工作副本。
- Agent 运行状态不等于 WALI Task 状态。失败后先冻结任务和路径、审计已有差异并优先恢复原 Agent，不自动清理、覆盖、提交或生成替代实现。
- 项目级 Ignore 由人维护的版本化 `svn:ignore` / `svn:global-ignores` 属性定义。WALI 清空个人客户端 `global-ignores` 后读取完整状态，只把属性链没有本地修改的原生 `ignored` 本地产物排除在交付差异外；它不自动执行 `propset`。
- 实现转入检查前必须运行 `carry`；修复后建立新代，不覆盖旧代证据。
- 不删除、跳过或弱化测试，不伪造证据，不声称未经验证的完成。
- SVN 提交只在 `delivering`、用户已验收且逐个精确 leaf path 当场授权时允许；提交授权不包含 update、冲突解决、部署或其他外部写入。
- `handoff` 和 `blocked` 是可恢复暂停，不是完成或退出；取消、替代和安全中止使用 `terminated` 并记录变更处置。

## 阶段摘要

| phase | 主要目的 | 写入边界 |
| --- | --- | --- |
| `clarifying` | 访谈、压力测试、形成 Goal + Spec | `goal.md`、`spec.md`、`handoff.md` |
| `awaiting_direction` | 等待高影响方向选择 | Goal 与 handoff |
| `planning` | 建立工作图与首个前沿任务 | WALI 治理文件 |
| `implementing` | 实施一个 `active_task` | 治理文件与任务精确范围 |
| `inspecting` | 独立审查、测试和问题闭环 | 治理文件；不改实现 |
| `accepting` | 等待用户业务验收 | Goal、issues、handoff |
| `blocked` | 记录无法安全绕过的阻断 | Goal 与 handoff |
| `delivering` | 只读复核与精确 SVN 提交 | Goal、handoff、授权路径 |
| `closed` | 无需提交的成功终态 | 仅受控 handoff/新 Goal |
| `terminated` | 取消、替代或安全中止 | 仅受控 handoff/新 Goal |

详细转段、异常恢复、SVN 交付和命令说明按需读取 `.claude/refs/operations.md`；运行能力与降级要求见 `.claude/refs/compatibility.md`。Policy Hook 是权限判定权威，这两份 Ref 只解释操作方式。

## 执行方式与角色

优先使用能可靠完成工作的最简单方式：小而连续的工作由主会话完成；独立调查、审查或测试使用 Subagent；只有边界清晰、并行收益明显且需要持续协作时才使用 Agent Teams。

主会话承担 Coordinator。`architect` 是按需只读顾问；`developer` 只在 implementing 中实现；`reviewer` 和 `tester` 只在 inspecting 中独立验证。身份、模型、effort、工具和停止条件以 `.claude/agents/` 中各角色定义为准，不能由调用者临时扩大。

工程与测试的路径规则位于 `.claude/rules/engineering.md` 和 `.claude/rules/testing.md`。Agent 通过 `.claude/refs/INDEX.md` 按角色与任务场景选择 Ref，并读取 Spec 引用的项目资料；新增同类 Ref 只维护索引，不逐个改写 Agent 身份。

## 常用命令

- `python3 .claude/hooks/wali-doctor.py --project-root .`：只读检查部署环境、Hook、SVN、契约和工作图。
- `python3 .claude/hooks/wali_policy.py check`：检查阶段契约和 schema。
- `python3 .claude/hooks/wali_policy.py audit`：审计 SVN 差异与写入范围。
- `python3 .claude/hooks/wali_graph.py --project-root . check`：检查工作图。
- `python3 .claude/hooks/wali_supervision.py --project-root . status`：查看 Agent 运行与恢复状态。
- `python3 .claude/hooks/wali_stop.py --project-root .`：检查是否可以停止。
- `python3 -m unittest -v test_wali_graph.py test_wali_policy.py test_wali_stop.py test_wali_supervision.py test_wali_svn.py test_wali_doctor.py`：在 `.claude/hooks/` 中运行 WALI 回归测试。

`/goal` 用于持续推进已有明确终点的阶段；`/loop` 只用于等待 CI、部署或评论等外部状态。

## 会话结束

结束前运行当前 phase 允许的验证，更新获授权的状态文件，核对监督状态和 SVN 差异，并把证据、风险、剩余事项和唯一下一步写入 `handoff.md`。最后运行 `wali_policy.py handoff-digest` 刷新 `state_digest`；未完成但需要暂停时再设置 `stop_intent: handoff`。
