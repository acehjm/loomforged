# wali-0x3 运行与恢复

## 阶段

```text
define → work ↔ verify → done
          ↓        ↓
        paused ← paused
```

- `define`：形成并确认稳定 Goal。
- `work`：实施一个 working active Task。
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

Task 的 Scope 必须是明确项目相对路径。实现者留下自检 Evidence 后进入 review；独立 Verifier 验证后才能 done。多任务依赖只在 WorkIndex 中计算，不创建图文件。

## 恢复与交接

普通会话从 `goal.md + work.md + 真实差异` 恢复，不依赖 handoff。只有显式 `stop_intent: handoff` 时，`handoff.md` 才必须包含镜像 Goal ID、phase、active task、真实更新时间、Current State 和唯一 Next Step。

PostHook 报告状态不完整时，`goal.md`、`work.md` 和 `handoff.md` 始终允许修复。不要通过回退用户代码恢复治理状态。

## SVN

- 读取：`svn status`、`svn diff --internal-diff`、`svn info`、`svn log`。
- 本地调度：`work` 中 active Task Scope 内的精确路径直接允许；其他路径请求用户确认。
- `svn commit` 是外部写入，PreToolUse 直接请求用户当场确认，不要求先改 Goal。
- 提交授权不包含 update、冲突解决、部署或其他远程动作。

WALI 不自动回退、清理、提交，也不自动修改 `svn:ignore` 属性。
