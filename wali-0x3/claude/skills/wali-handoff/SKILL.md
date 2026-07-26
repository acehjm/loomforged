---
name: wali-handoff
description: 在会话结束或需要交接时，在当前 phase 权限内保存最小、可信、可恢复的 WALI 游标。
disable-model-invocation: true
---

1. 先确认当前目录就是 SVN 工作副本根，运行阶段契约检查，再运行本 phase 允许的必要验证。检查工作副本 URL、修订信息、`svn status` 和 `svn diff --internal-diff`。
2. 运行 `python3 .claude/hooks/wali_supervision.py --project-root . status`，把 Agent 面板或 `/tasks`、transcript、活动 Task 和 SVN 差异一起核对。存在与当前 `active_task` 绑定的未恢复失败时，先确认对应 Task/路径已冻结并完成差异审计；无活动任务的失败只作为诊断事件记录。
3. 严格按 `allowed_effects` 更新状态：`clarifying` 只能改固定的 `goal.md`、`spec.md` 和 `handoff.md`；其他阶段也不得为了交接扩大写入范围。
4. 覆盖重写 `handoff.md` 的当前快照，不追加成进度日志。它必须记录：
   - Goal ID、phase、active task、Goal + Spec 联合确认状态和退出状态。
   - 当前阶段允许的行为与下一个转段条件。
   - 最近完成、当前工作、最近验证、SVN 基线与差异、调用前已存在的用户修改。
   - 问题、风险、工作图前沿和唯一的下一步。
   - `clarifying` 时另记轮次、最后纳入回答、下一轮问题和未解决冲突。
   - `carry_epoch`、只追加的 `carried_history`、当前代 `carried_changes`、当前提交清单（若有）、交付回执状态、`stop_intent`，以及退出原因/证据/变更处置（若有）。
   - 存在与当前 `active_task` 绑定的未恢复 Agent 失败时，记录精确 `supervision_event`、`recovery_action`（`resume`、`replace`、`wait_user` 或 `terminate_goal`）和非占位 `recovery_evidence`；恢复完成后重置为 `none` / `none` / 空字符串。
5. 在允许修改 `todo.md` 或 `issues.md` 的 phase 中，使任务、问题、证据和实际代码一致。不能用交接总结代替独立复验。
6. 运行工作图检查和 `wali_policy.py audit`。如果发现越界修改或类似上下文、计划、进度、图副本的未授权新产物，不把它们默认纳入项目；报告来源并按用户指示处理。
7. 需要方向性决策时进入 `awaiting_direction`，不能借 `blocked` 或 `accepting` 扩大写入；自动条件满足后等待业务回测时才转入 `accepting`。只有用户验收证据充分，且 prospective 成功终态已通过完整工作图、required Task、独立 Evidence、blocker 与 SVN 差异校验时，才能进入 `delivering` 或 `closed`。
8. 更新完交接正文和其他获准状态后，运行 `wali_policy.py handoff-digest`，把输出写入 `handoff.md` frontmatter 的 `state_digest`。该摘要绑定 Goal、完整 Spec、任务图和工作副本；不能复制旧值或在摘要后继续改动相关状态。
9. 工作未完成但需要结束当前会话时，先刷新 `state_digest`，再将 `stop_intent` 设为 `handoff`，并确保 `handoff.md` frontmatter 的 Goal、phase、active task、确认状态和真实更新时间与 `goal.md` 完全一致。恢复工作后将其改回 `continue`。这是可恢复暂停，不是完成声明。活动任务存在未恢复失败却缺少恢复三字段时，Stop 必须拒绝交接。
10. `delivering` 不等于默认允许提交。只有此前检查已经完成，且当前 carry 代、`svn_commit_paths` 精确 leaf 文件清单和可追溯的 `svn_commit_evidence` 同时成立，才能设置 `allow_svn_commit: true`。`svn_commit_evidence` 只用于追踪，不是授权令牌；每次提交仍必须由 PreToolUse 返回 `ask`，让用户当场核对命令和路径。`allow_external_writes` 仍为 false，阶段内禁止项目命令，只接受严格独立的精确路径 `svn commit`；不自动执行 update、发布或其他远程写入。PreToolUse 必须证明每个目标提交前确有差异，PostToolUse 必须从成功响应取得唯一提交修订号并生成绑定提交前证据、当前授权、路径和指纹的本地回执；空提交或没有真实修订号时不得生成。授权路径仍有差异时可受确认撤销提交准备；路径已清洁但回执无效时不得返回原 Goal；有效回执成立后 `delivering` 冻结。
11. 在对话中输出与文件一致的交接摘要：当前 phase、命令与结果、剩余事项、风险、权限边界和下一步。
12. `handoff` 与 `blocked` 都是可恢复暂停。只有成功满足全部条件才以 `completed` 退出；取消、替代或安全中止必须进入 `terminated`，让 `status` 与 `exit_outcome` 精确一致，记录类型、原因、证据及未提交变更处置，并由用户当场确认。实施中选择保留/交接当前差异时，先用 `carry` 冻结当前合法内容；未冻结差异不得进入终态。退出本身不得触发自动清理或回退。
