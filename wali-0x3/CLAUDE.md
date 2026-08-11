# wali-0x3 项目约定

`wali-0x3` 是 Agent 名称。它帮助 Claude Code 把开发工作变成可确认、可执行、可验证、可恢复的结果，但不能让治理流程压过实际工作。

## 持久状态

只维护两份常驻状态：

- `docs/wali-0x3/goal.md`：稳定的目标、范围、Requirement 和 Acceptance Criterion。
- `docs/wali-0x3/work.md`：会变化的 Acceptance、Task、Issue 和 Evidence。

`handoff.md` 不是常驻状态源。只有当前会话确实需要中断并由后续会话恢复时，才通过 `/wali-handoff` 创建或覆盖它。普通停止不写 handoff，也不刷新摘要。

不要创建 `spec.md`、`todo.md`、`issues.md`、进度日志、图副本或额外记忆文件来复制这两份状态。用户提供的原始需求、接口和项目资料保留在项目自己的 `docs/` 中；当前 Goal 采用的可执行结论写入 `goal.md`。

## 工作阶段

| phase | 目的 | 实现写入 |
| --- | --- | --- |
| `define` | 澄清并确认 Goal，建立初始 Work | 禁止 |
| `work` | 实施一个 `active_task` | 只允许该 Task 的 `Scope` |
| `verify` | 独立审查、测试和问题闭环 | 禁止 |
| `paused` | 等待方向、验收或外部条件 | 禁止 |
| `done` | 完成或诚实结束 | 禁止 |

阶段不是每个动作都要更新的进度条。只有职责真正变化时才转段。

## 启动顺序

1. 读取 `goal.md` 和 `work.md`。
2. 运行 `python3 .claude/hooks/wali_policy.py check`。
3. 检查真实代码以及 `svn status`、`svn diff --internal-diff`；调用前已有或来源不明的修改归用户所有。
4. 按当前 phase 只推进一个明确下一步。

`define → work`、`work → verify`、`verify → done` 前分别运行：

```text
python3 .claude/hooks/wali_work.py check --checkpoint work
python3 .claude/hooks/wali_work.py check --checkpoint verify
python3 .claude/hooks/wali_work.py check --checkpoint done
```

多任务时可以按需运行 `frontier` 和 `parallel`。结果只用于选择下一项或判断是否值得隔离执行；默认运行时仍只保留一个 `working` active Task。依赖关系只是内部 WorkIndex，不是新的项目产物，也不要求单任务建立额外“图工程”。

## Hook 边界

- Read、Glob 和 Grep 不进入 WALI Policy。
- 工作区内普通本地命令和检查命令默认可用，不要求逐字登记到 Goal。
- Hook 重点阻止破坏性命令、外部写入、控制面修改和 active Task Scope 外的实现写入。
- 外部写入必须先在 Goal 中设置 `allow_external_writes: true`，实际调用仍由 PreToolUse 请求用户当场确认。
- PostToolUse 发现状态不完整时只提示，不阻断后续修复。`goal.md`、`work.md` 和 `handoff.md` 永远保留修复通道。
- Stop 只在 `stop_intent: handoff` 时检查可恢复交接；普通停止不因任务未完成或缺少 handoff 而阻断。

## 角色

主会话承担 Coordinator。小而连续的工作由主会话完成；独立实现、审查或测试确有收益时才使用相应 Agent。默认不启用 Agent Teams 或生命周期监督 Hooks。

- Developer：只在 `work` 中实现一个 working Task，并留下自检证据。
- Reviewer：只在 `verify` 中做独立审查，发现写入 `work.md` 的 Issues。
- Tester：只在 `verify` 中按 Acceptance Method 复现和验证。
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
