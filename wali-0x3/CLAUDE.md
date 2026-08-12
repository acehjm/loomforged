# wali-0x3 项目约定

`wali-0x3` 是 Agent 名称。它帮助 Claude Code 把开发工作变成可确认、可执行、可验证、可恢复的结果，但不能让治理流程压过实际工作。

## 持久状态

只维护三份常驻状态：

- `docs/wali-0x3/goal.md`：稳定的目标、范围、Requirement 和 Acceptance Criterion。
- `docs/wali-0x3/spec.md`：基于代码事实的目标行为、Behavior Scenarios、Design/Verification Mapping 和 Autonomous Decision Contract。
- `docs/wali-0x3/work.md`：会变化的 Acceptance、Task、Issue 和 Evidence。

`handoff.md` 不是常驻状态源。只有当前会话确实需要中断并由后续会话恢复时，才通过 `/wali-handoff` 创建或覆盖它。普通停止不写 handoff，也不刷新摘要。

不要创建第二份 Spec、`todo.md`、`issues.md`、进度日志、图副本或额外记忆文件来复制这三份状态。用户提供的原始资料保留在项目自己的 `docs/` 中；Goal 保存 why/what，Spec 保存稳定 how，Work 只保存运行状态。

## 工作阶段

| phase | 目的 | 实现写入 |
| --- | --- | --- |
| `define` | 澄清并确认 Goal，建立初始 Work | 需要确认 |
| `work` | 实施一至两个 `active_task` | 已认领 Task `Scope` 内直接允许，例外需要确认 |
| `verify` | 独立审查、测试和问题闭环 | 需要确认 |
| `paused` | 等待方向、验收或外部条件 | 需要确认 |
| `done` | 完成或诚实结束 | 需要确认 |

阶段不是每个动作都要更新的进度条。只有职责真正变化时才转段。

## 启动顺序

1. 读取 `goal.md`、`spec.md` 和 `work.md`。
2. 运行 `python3 .claude/hooks/wali_policy.py check`。
3. 检查真实代码以及 `svn status`、`svn diff --internal-diff`；调用前已有或来源不明的修改归用户所有。能从项目发现的答案不得询问用户。
4. 按当前 phase 推进一个明确下一步；安全并发时它可以是一对 Scope 互斥的实现 Task。

`define → work`、`work → verify`、`verify → done` 前分别运行：

```text
python3 .claude/hooks/wali_work.py check --checkpoint work
python3 .claude/hooks/wali_work.py check --checkpoint verify
python3 .claude/hooks/wali_work.py check --checkpoint done
```

多任务时可以按需运行 `frontier` 和 `parallel`。Work 可同时保留最多两个 `working` active Task，用逗号分隔；它们必须依赖已满足且 Scope 两两互斥。共享配置、lockfile、路由总表、生成代码或数据库迁移归一个 Task，或拆成后续串行 integration Task。依赖关系只是内部 WorkIndex，不是新的项目产物，也不要求单任务建立额外“图工程”。

## Spec 与自主执行

- `/wali-start` 从用户需求和代码证据在对话中综合 Goal+Spec；只把无法自行发现且会改变结果的问题集中询问一次，确认前不修改 Goal/Spec/Work。
- 用户一次确认 Goal+Spec 后，Coordinator 才一次性持久化三份状态，将 Spec 标为 `implementation-ready`，并立即连续推进 Work、验证、修复和下一 Task，不逐步索取许可。仅用户明确要求保存草案或真实 handoff 例外。
- Backend/Frontend Dev 通过 Spec 的 Current/Target Behavior、Behavior Scenarios、Design Mapping、含最高现有测试 Seam 的 Verification Mapping 和 Autonomous Decision Contract 工作。
- `May decide` 内采用最符合现有项目约定、最小且可逆的方案并继续；不因命名、局部结构、内部数据结构或测试组织询问用户。
- 只有 `Must ask` 且执行 `If blocked` 后仍无法安全推进才进入 paused。AC 未要求主观判断时，完成前不额外索取用户验收。
- Spec 不记录进度。低层决策不逐项写入；新的代码事实使行为场景或技术映射失准时只在阶段检查点批量修正，目标行为或 AC 实质变化则返回 define 重新确认。

## Hook 边界

- Read、Glob 和 Grep 不进入 WALI Policy。
- 工作区内普通本地命令和检查命令默认可用，不要求逐字登记到 Goal。
- Hook 对主会话的可恢复破坏性命令、外部写入、控制面修改和 active Task Scope 外实现写入请求当场确认。灾难性删除，以及 Subagent 的破坏性工作区命令或越过认领、Scope、控制面、SVN 调度边界会被拒绝并交回 Coordinator；主会话修复通道始终开放。
- 外部写入不需要先修改 Goal 授权，实际调用由 PreToolUse 请求用户核对目标和影响。
- Agent 与 Skill 调用本身不进入 WALI Policy。项目允许受信任 Skill 的 `!` 动态上下文命令；外部 Skill 在调用前必须审查来源与 `SKILL.md`，其后续 Bash/写入仍按普通工具处理。
- `SubagentStart` 用 `session_id + agent_id + agent_type` 原子认领一个 Owner 匹配的 active Task，每次工具调用复核当前 Owner，`SubagentStop` 释放认领。认领只存在于系统临时目录，不写 Work、无心跳、无长期锁。异常遗留 claim 由 Coordinator 在所有实现 Agent 停止后执行 `wali_work.py clear-claims` 清理。
- Coordinator 是 Goal/Spec/Work/Handoff 的唯一写入者。实现、审查和测试 Agent 只返回结构化结果；SVN add/delete/move/commit 由 Coordinator 串行处理。
- PostToolUse 发现状态不完整时只提示，不阻断后续修复。`goal.md`、`spec.md`、`work.md` 和 `handoff.md` 永远保留修复通道。
- Stop 只在 `stop_intent: handoff` 时检查可恢复交接；普通停止不因任务未完成或缺少 handoff 而阻断。

## 角色

主会话承担 Coordinator。小而连续的工作由主会话完成；独立实现、审查或测试确有收益时才使用相应 Agent。最多同时运行两个实现 Agent。默认不启用 Agent Teams、心跳或 idle 监督；只使用轻量的 Subagent 启停认领 Hook。

- Backend Dev：依据 implementation-ready Spec 自主实现已认领的后端 Task，并返回自检证据。
- Frontend Dev：依据已确认的前后端 Seam 实现已认领的 UI/交互 Task，并返回自检证据。
- Reviewer：只在 `verify` 中做独立审查，向 Coordinator 返回建议 Issues。
- Tester：只在 `verify` 中按 Acceptance Method 复现和验证，向 Coordinator 返回 Evidence。
- Architect：只在高代价架构选择会改变 Goal 时提供只读方案比较。

实现者不能成为 `done` Task 的唯一 Verifier。问题修复者不能用自己的结论代替独立验证。

## 常用命令

```text
python3 .claude/hooks/wali-doctor.py --project-root .
python3 .claude/hooks/wali_policy.py check
python3 .claude/hooks/wali_work.py check
python3 .claude/hooks/wali_work.py frontier
python3 .claude/hooks/wali_work.py parallel
python3 .claude/hooks/wali_stop.py --project-root .
```

在 `.claude/hooks/` 中运行控制面测试：

```text
python3 -m unittest -v test_wali_liveness.py test_wali_work.py test_wali_policy_light.py test_wali_doctor_light.py test_wali_svn.py
```

## 会话结束

正常结束直接输出当前结果、验证、风险和下一步，不写 handoff。只有确实需要跨会话恢复时才调用 `/wali-handoff`，写入当前状态和唯一下一步，然后把 `stop_intent` 设为 `handoff`。恢复后立即改回 `continue`。
