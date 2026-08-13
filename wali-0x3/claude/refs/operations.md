# wali-0x3 运行与恢复

## 阶段

```text
define → work ↔ verify → done
          ↓        ↓
        paused ← paused
```

- `define`：在对话中形成并确认稳定 Goal+Spec；确认后与 Work 一次性持久化。
- `work`：实施一至两个 working active Task。
- `verify`：独立审查、测试和问题闭环。
- `paused`：等待方向、验收或外部条件。
- `done`：完成、取消或安全中止；由 `outcome` 说明结果。

检查点命令：

```text
python3 .claude/hooks/wali_work.py check --checkpoint work
python3 .claude/hooks/wali_work.py check --checkpoint verify
python3 .claude/hooks/wali_work.py check --checkpoint done
```

## Task 与 Issue

Task 状态：`pending → working → review → done`；无法推进时可用 `blocked`。Issue 状态：`open → fixing → verify → closed`。

Task 的 Scope 必须是明确项目相对路径。Work 最多同时列出两个 active Task，二者依赖必须已满足且 Scope 互斥。实现 Agent 通过启停 Hook 认领 Owner 匹配的 Task，只返回结构化结果；Wali 核对真实差异后批量写 Work。实现者留下自检 Evidence 后进入 review；独立 Verifier 验证后才能 done。多任务依赖只在 WorkIndex 中计算，不创建图文件。

异常退出且 Stop Hook 未释放 claim 时，Wali 等其他实现 Agent 全部停止后运行 `wali_work.py clear-claims --all-agents-stopped`，再重新分派。该参数是对“全部停止”的显式确认；不要在实现 Agent 运行时清理认领。

## 恢复与交接

普通会话从 `goal.md + spec.md + work.md + 真实差异` 恢复，不依赖 handoff。只有显式 `stop_intent: handoff` 时，`handoff.md` 才必须包含镜像 Goal ID、phase、active task、真实更新时间、Current State 和唯一 Next Step。

PostHook 报告状态不完整时，`goal.md`、`spec.md`、`work.md` 和 `handoff.md` 始终允许修复。不要通过回退用户代码恢复治理状态。

## SVN

- 读取：`svn status`、`svn diff --internal-diff`、`svn info`、`svn log`。
- 本地调度：实现 Agent 不执行 SVN 调度；Wali 在核对返回结果后，串行执行 active Task Scope 内的精确路径调度。其他路径请求用户确认。
- `svn commit` 是外部写入，PreToolUse 直接请求用户当场确认，不要求先改 Goal。
- 提交授权不包含 update、冲突解决、部署或其他远程动作。

WALI 不自动回退、清理、提交，也不自动修改 `svn:ignore` 属性。
