# WALI Agent 监督与异常恢复规则

Agent 运行状态和 WALI Task 业务状态是两套不同状态机，不能互相冒充：

```text
WALI Task：pending → working → review → done
运行状态：spawned → running → waiting / idle / completed
                         └→ needs_attention / failed
```

Agent 完成一次运行，只表示它已经返回控制权；对应 Task 必须先有执行证据并进入 `review`，经过独立验证后才能成为 `done`。运行异常也不能自动把 Task 改成 `blocked`、`done` 或创建替代实现。

## 事件检查

- Agent Teams 的共享任务标题必须包含且只能包含一个稳定 WALI Task ID，例如 `[T-001] 实现支付校验`。
- `TaskCompleted` 在 `implementing`/`inspecting` 中只接受当前 `active_task`。Task 仍为 `working`、缺少执行证据、工作图无效或引用其他 Task 时，以退出码 2 拒绝完成。
- `TeammateIdle` 只检查当前 Task 的实际负责人。负责人仍持有 `working` Task 时，以退出码 2 要求其报告状态，并带证据转为 `review` 或记录真实阻断；不相关的 Architect、Reviewer 或其他顾问可以正常 idle。
- `StopFailure` 没有决策控制，只记录失败类型、transcript 路径、消息摘要和当前 Goal/phase/Task；不得声称它阻止了异常退出。只有能绑定当前 `active_task` 的失败才设置强制恢复要求；没有活动任务的 Coordinator/顾问失败只作为诊断事件，不虚构 Task 状态。
- 运行事件只写入 SVN 本地元数据 `.svn/wali-policy/supervision.json`，不创建第六份项目状态，不进入 SVN。并发 Hook 通过本地锁和原子替换避免写坏事件记录。

## 状态检查

Coordinator 使用以下来源交叉判断，不以单一超时直接宣称 Agent 卡死：

1. Claude Code 的 `/tasks`、Agent 面板或后台 Agent View。
2. `python3 .claude/hooks/wali_supervision.py --project-root . status`。
3. 对应 transcript 的最后动作和错误。
4. 当前 Task、Goal phase、SVN 状态和真实差异。

没有新输出不必然是异常；长时间命令、权限等待和用户输入等待必须先分类。确认可能停滞时，只发送一次明确状态探测，要求返回当前步骤、最后成功动作、阻断、已产生差异和下一步。

## 恢复顺序

1. `waiting_input` / `waiting_permission`：交给用户处理，不生成替代 Agent，不把 Agent 消息当成用户授权。
2. 偏离方向但会话仍可用：向原 Agent 发送纠正信息，优先复用原 Agent ID 和 transcript。
3. `needs_attention`：检查 Task 状态与证据，要求原 Agent完成 `working → review`，或记录可验证阻断。
4. `failed` / 异常退出：
   - 保存事件 ID、transcript、最后成功动作和错误类型；
   - 运行 SVN 差异审计，保护用户修改，并确认失败 Agent 是否留下活动范围内的部分实现；
   - 在完成审计前冻结对应 Task 和路径所有权，不让替代 Agent 覆盖；
   - 优先恢复原 Agent；无法恢复时才生成替代 Agent，并交付同一 Task ID、Spec、允许范围、现有差异、失败原因和下一验证步骤；
   - 不自动回退、删除或提交任何修改。
5. 替代或恢复后的 Agent 只有在 Task 带证据进入 `review` 并触发有效 `TaskCompleted` 后，才把本地恢复要求标记为已解决。

若会话需要在与当前 `active_task` 绑定的恢复完成前交接，`handoff.md` 必须记录：

- `supervision_event`：当前失败事件 ID。
- `recovery_action`：`resume`、`replace`、`wait_user` 或 `terminate_goal`。
- `recovery_evidence`：已检查的 transcript/SVN 状态、路径处置和下一责任人。

Stop Hook 会拒绝缺少这三项的异常恢复交接。完成恢复后，将字段重置为 `none` / `none` / 空字符串。
