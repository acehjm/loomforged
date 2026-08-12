---
title: wali-0x3 核心设计
status: implemented
---

# wali-0x3 核心设计

`wali-0x3` 是 Agent 名称。设计目标是在 Claude Code 中提供足够的目标、范围、证据和恢复纪律，同时保持工作流活性。

## 1. 设计约束

### 实际工作优先

治理只有在减少错误、越权或恢复成本时才值得存在。普通读取、搜索、测试和停止不应被项目管理元数据阻断。

### 例外必须可恢复

可恢复或需要判断的例外优先请求用户确认，只有灾难性操作才拒绝。每次拒绝都必须留下至少一个可执行修复动作。PostHook 发生在副作用之后，因此只能报告和引导修复，不能把已经变更的状态锁死。

### 稳定定义与运行状态分离

- `goal.md` 保存稳定的目标、范围和验收契约。
- `spec.md` 保存由代码事实支撑的稳定实现契约和自主决策边界。
- `work.md` 保存会变化的 Task、Issue、Acceptance 和 Evidence。
- `handoff.md` 只在真实交接时生成。

### Hooks 保护不可逆边界

Policy 关注 Scope、控制面、破坏性命令和外部写入。项目命令的选择与参数属于 Agent 的执行判断，不使用完整字符串白名单代替判断。

## 2. 状态接口

`goal.md` frontmatter 只保存稳定契约字段：

```yaml
agent: wali-0x3
goal_id: G-001
confirmed: true
```

`spec.md` frontmatter 只保存 Goal 关联和就绪状态：

```yaml
agent: wali-0x3
goal_id: G-001
status: implementation-ready
```

`work.md` frontmatter 保存运行字段：

```yaml
goal_id: G-001
phase: work
active_task: T-001
stop_intent: continue
waiting_for: none
outcome: none
```

因此 Task 或阶段切换只需修改 Work，不会连带重写稳定 Goal/Spec。Developer 的实现接口是 Goal 的 why/what、Spec 的 Current/Target Behavior、Design/Verification Mapping 和 Autonomous Decision Contract；Work 只提供当前游标。Policy 内部实现不应把额外锁、摘要、代次或能力边暴露给每个调用者。

## 3. 深模块

### WorkState

`wali_work.py` 把三份 Markdown 解析为一个 `WorkState`，提供：

- `validate_state`
- `checkpoint_reasons`
- `frontier`
- `safe_parallel_pairs`

依赖遍历是内部实现。Requirement、Design、AC、Verification、Task 和 Evidence 的关系校验不被包装成用户必须维护的“图工程”。

### Policy

Policy 的外部接口是一次工具动作：

```text
action + Goal + active Task → allow / ask / deny
```

它不会在每次动作中执行完整完成判断，也不写前置快照。状态缺失或不完整时，治理文件修复始终允许；其他实现写入请求当场确认，不形成死锁。

PreToolUse 的高频门禁仍只解析 Goal/Work frontmatter 和 active Task 行，不读取 Spec，不遍历 Requirement、AC、Issue 或依赖环。Spec 完整性只在低频诊断和显式检查点验证，避免把更丰富的规格重新变成每次工具调用的性能税。Bash 会覆盖常见显式文件变更，但任意程序内部的隐藏副作用超出命令文本可可靠推断的范围；需要硬边界时使用独立工作区或操作系统沙箱。

### Stop

Stop 的默认接口是 allow。只有调用者显式设置 `stop_intent: handoff` 时，才验证 handoff 游标。这样“暂停并恢复”仍可信，但普通回答结束不会制造治理写入。

## 4. 检查点而非持续强一致

完整关系校验发生在：

- Goal+Spec 确认并进入 work 前。
- 实现交给独立验证前。
- Goal 完成前。

状态文件的一次中间编辑可以暂时不完整；PostHook 给出修复提示，下一次编辑继续开放。检查点必须完整通过。

## 5. 自主决策接口

Spec 把“何时问用户”变成显式接口，而不是让每个 Agent 临场猜测：

- `May decide`：可逆、低影响且遵循现有约定的内部实现与测试选择，Agent 直接决定。
- `Must ask`：用户可见语义、Acceptance 冲突、不可逆数据迁移、重大安全/费用风险和不可安全回滚的外部副作用。
- `Must not`：扩大业务范围、弱化验证、覆盖用户修改或伪造事实。
- `If blocked`：先从代码、测试、配置、历史和文档取证，只带一个真正阻塞的问题回来。

用户确认 Goal+Spec 后，Coordinator 自动推进 Task 和检查点。新的代码事实若只修正技术映射，可在契约内更新 Spec 并继续；改变 Goal/AC 时才返回 define。这样交互次数由真实决策点决定，而不是由 Task 数量决定。

## 6. 多任务适用条件

只有以下场景使用 Task 依赖和并行计算：

- 至少两个可独立推进的 Task。
- Task 存在真实先后依赖。
- 多个写入者需要证明 Scope 互斥。

`parallel` 输出只是并发候选，不是权限。默认运行时仍只维护一个 working active Task；真正并发还需要调用者提供隔离工作区或等价的任务身份边界。单任务不创建图、Mermaid 或并行候选。

## 7. 外部副作用

外部写入不使用持久授权开关。PreToolUse 对实际命令直接返回 `ask`，由用户核对目标和影响；一次确认不自动授权后续外部动作。

Skill/Agent 调用本身直接允许。项目启用受信任 Skill 的 `!` 动态上下文命令；这类命令在 Skill 加载阶段执行，不是模型发起的普通 Bash 工具调用，因此信任边界位于“调用该 Skill”之前。外部 Skill 必须先审查来源和定义；Skill 后续发起的普通工具动作仍按 Policy 分级。

## 8. 失败与恢复

- 状态无效：允许修复 Goal/Spec/Work/Handoff 和运行本地诊断命令；其他实现写入请求当场确认。
- Agent 失败：核对 transcript、Work 和真实差异；不使用默认生命周期监督锁。
- 等待用户：进入 paused，记录 `waiting_for`，不伪装成完成。
- 取消或安全中止：进入 done，并用 outcome 记录 `cancelled` 或 `aborted`。
- 跨会话暂停：显式生成最小 handoff；普通停止不生成。

## 9. 性能预算

- Read/Glob/Grep 不启动 Policy 子进程。
- PreToolUse 不全量重建 WorkIndex。
- PostToolUse 不执行全仓 SVN 审计和状态快照。
- Agent 启动只必读 Goal、Spec 与 Work，不读取重复规格副本。
- handoff 不绑定哈希，也不因每个代码变更失效。

如果后续功能需要重新把多文件强一致、完整命令白名单或持续图校验放回主路径，必须先用真实故障率和成本数据证明收益。
