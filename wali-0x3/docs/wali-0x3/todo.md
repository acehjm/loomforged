# 任务清单

状态只使用 `pending`、`working`、`review`、`blocked`、`done`。必要性只使用 `required` 或 `optional`。`done` 必须填写执行结果与验证证据。

每个任务 ID 在当前 Goal 内必须唯一。`关联 AC` 和 `依赖` 只填写稳定 ID；多个 ID 使用逗号或 `<br>` 分隔，无依赖时填写“无”。每项任务必须关联至少一个验收条件，并通过 `spec.md` 中的 Requirement → AC 边拥有明确上游需求；依赖不得成环。`允许修改范围` 应使用可以比较的具体路径或 glob；范围不清楚的任务不能判定为安全并行。任务确需项目 Skill 时，在 `所用 Skill` 中填写 `Skill:<name>`；多个值用逗号分隔，无则写“无”。所列 Skill 必须同时出现在 Goal 的 `allowed_capabilities` 中，但这种关联只选择方法，不扩大任务权限。若同步到 Agent Teams 共享任务，标题必须包含且只能包含一个对应稳定 ID，例如 `[T-001] 实现支付校验`；原生任务的 idle/completed/failed 只表示 Agent 运行事件，不替代本表状态和证据。

| ID | 关联 AC | 任务 | 负责人 | 必要性 | 状态 | 依赖 | 允许修改范围 | 所用 Skill | 任务验收条件 | 执行结果/证据 | 独立验证者 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- | T-001 | AC-01 | 描述一个会话内可验证的垂直增量 | developer | required | pending | 无 | `src/example/**` | Skill:project-development / 无 | 可观察的完成条件 | 待补充 | 待分配 | -->

## 任务记录模板

### T-XXX：任务名称

- 关联验收条件 ID：
- 负责人：
- 状态：
- 依赖任务：
- 允许修改范围：
- 所用 Skill：`Skill:<name>` / 无
- 任务验收条件：
- 实施摘要：
- 执行命令与退出结果：
- 相关证据：
- 独立验证者：Reviewer / Tester / 用户
- 已知风险：
- 审查/测试交接：

## 工作图规则

- automatic 验收条件至少由一项任务覆盖。
- 每个 AC 必须在 `spec.md` 中有上游 Requirement 和唯一判定规则，形成 Requirement → AC → Task → Evidence。
- Task 声明的 Skill 必须由当前 Goal 授权；工作图会形成 Skill → Task 方法边，但实际调用仍接受阶段、effect 和 scope 检查。
- Agent 运行状态与 Task 状态分离；`TaskCompleted` 只能证明一次运行返回，不能越过 `review`、独立验证和 Evidence 直接生成 `done`。
- Coordinator 负责接受新增任务和依赖关系；其他角色只提出变更建议。
- 位于当前可执行前沿的任务，必须处于 `pending`、所有依赖均为 `done`，且没有关联的未关闭 `blocker`。
- 两项前沿任务只有修改范围确定互斥时，才可以并行执行。
