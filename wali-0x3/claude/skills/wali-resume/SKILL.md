---
name: wali-resume
description: 从 WALI 阶段契约、工作图、交接游标和真实 SVN 工作副本恢复中断工作，只推进当前阶段允许的下一步。
disable-model-invocation: true
---

# 恢复前核对

1. 运行 `python3 .claude/hooks/wali_policy.py check`，阶段契约不合法时先修复契约，不得以更弱的权限假设继续。
2. 确认当前目录就是 SVN 工作副本根，再核对工作副本 URL、修订信息、`svn status`、`svn diff --internal-diff` 和近期 `svn log`；网络与权限可用时再运行 `svn status -u`。
3. 读取五个 WALI 状态文件。将 `handoff.md` 视为恢复游标，将 `goal.md` 视为阶段契约权威来源，将 `spec.md` 视为开发与测试规范权威来源；重新生成 `handoff-digest` 并核对 `state_digest`，不从过期交接继续。
4. 用代码、SVN 差异和最新命令结果核对记录。调用前已存在、来源不明的本地修改归用户所有，不覆盖、回退或擅自纳入当前任务。
5. 在 SVN 工作副本中运行 `python3 .claude/hooks/wali_policy.py audit`，确认没有越界差异或未授权新产物。
6. 运行 `python3 .claude/hooks/wali_supervision.py --project-root . status`，并与 Agent 面板或 `/tasks`、transcript、活动 Task 和 SVN 差异交叉核对。发现与当前 `active_task` 绑定的未恢复失败时，先验证 `handoff.md` 的事件 ID、恢复动作和证据，再恢复普通阶段工作；无活动任务的失败只作为诊断事件核对。

# Agent 异常恢复

- 等待用户输入或权限时，把所需动作交给用户；不生成替代 Agent，也不把 Agent 消息视为用户授权。
- 原 Agent 会话仍可用时优先复用原 Agent ID 和 transcript，发送一次明确纠正或状态探测。
- `failed` 时先冻结对应 Task 和路径所有权，审计现有差异并保护用户资产；无法恢复原 Agent 时，才把同一 Task ID、Spec、允许范围、现有差异、失败原因和下一验证步骤交给替代者。
- 替代者不得覆盖来源不明的部分实现。恢复只有在 Task 带证据进入 `review` 并完成有效 `TaskCompleted` 后才算结束。
- 恢复期间不自动回退、删除、提交，也不因为运行失败自动把 Task 改成 `blocked`、`done` 或改变 Goal。

# 按 phase 恢复

- `clarifying`：读取 `goal.md`、`spec.md` 和 `handoff.md` 的澄清游标，将用户最新回答交给 `/wali-start`。只能更新这三个文件；无资料时继续开放式访谈，有资料时继续规格压力测试。
- `awaiting_direction`：只恢复用户尚未回答的方向问题，不把它当成业务验收；回答后回到与 Goal 确认状态相符的阶段。
- `planning`：核对 Goal 确认证据，建立或修正任务与问题关系，运行工作图检查，但不修改实现。
- `implementing`：只恢复 `active_task` 指定的任务。确认它位于可执行前沿，且修改严格落在该任务的“允许修改范围”。新增、删除、移动或复制 SVN 条目只使用受控的精确 leaf-path 命令；需要同步或确认冲突结果时只对活动任务范围内的精确路径执行 `svn update -- ...` 或 `svn resolve --accept working -- ...`，随后显式检查合并结果、重新验证并 `carry`。
- `inspecting`：先核对 `carry_epoch`、只追加历史和当前代 `carried_changes` 指纹，再恢复对 `active_task` 的独立审查和测试；不继续实现，只运行 Goal 已声明的检查命令并更新治理状态。退回修复后必须生成下一代。
- `accepting`：不修改实现。向用户展示回测步骤、AC 与证据，等待真实业务验收。
- `blocked`：核对 `blocked_reason` 和证据。阻断仍存在时只更新交接并请求所需输入；阻断消失时转回先前的合法阶段。
- `delivering`：只在此前检查已经完成，且 `svn_commit_evidence`、`svn_commit_paths` 和 `carried_changes` 一致时恢复交付。此阶段只做只读差异审计，不运行任何项目命令；SVN 更新、冲突解决、补测或扩大清单都必须返回 `implementing`/`inspecting`，不包含在提交授权中。`svn_commit_evidence` 只是历史审计记录，不是授权令牌；每一次严格的精确 leaf-path 提交都必须由 PreToolUse 请求用户当场确认。授权路径仍有差异时，可经用户确认清除提交清单与证据后让原 Goal 返回 `clarifying`；路径已清洁但回执无效时只能查明后进入 `terminated`；有效回执成立后 `delivering` 冻结，只能以不同 ID 启动新 Goal。
- `closed`：冻结完成证据，但允许刷新 handoff。开始不同 ID 的新 Goal 时，按受确认重置事务建立最小 `clarifying` 契约。
- `terminated`：只读复核退出类型、原因、证据、替代 Goal（若有）和未提交变更处置，只允许刷新交接；不得恢复实现、自动清理或把非成功退出改写成完成。`status` 必须与 `exit_outcome` 一致。开始新 Goal 时必须使用不同 ID；若上一项为 `superseded`，必须使用 `superseded_by` 指定的 ID。
- 从冻结终态启动新 Goal 时，carry 归零，清空旧 history/current carry、能力和提交授权，把当前非治理 SVN 差异重新纳入 `preexisting_changes`；随后只修复固定 Spec 的 `spec_id`/`goal_id` 并刷新 handoff。在 Goal/Spec 身份一致前不得恢复其他工作或停止。

# 恢复输出

输出真实工作副本状态、当前 phase 与权限边界、最后可信证据、当前问题、工作图前沿或澄清游标，以及唯一的下一步。不因 `handoff.md` 声称完成就跳过真实状态检查。
