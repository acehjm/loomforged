# wali-0x3 项目约定

本项目使用 WALI（Work · Assign · Loop · Inspect）组织 Claude Code 开发工作。目标是让每项工作可分派、可检查、可恢复、可验收，而不是尽可能多地启动 Agent。

## 会话启动

开始或恢复开发任务时，先完成以下检查：

1. 确认当前目录、分支、`git status` 和近期提交。
2. 读取 `docs/wali-0x3/goal.md`、`todo.md`、`issues.md`、`progress.md`。
3. 用代码、Git 和最新命令结果核对状态文件；不一致时，以真实状态为准并修正文档。
4. 选择最高优先级、依赖已满足的必要任务，一次只推进一个可验证增量。

如果状态文件仍是模板或用户提出了新目标，先建立目标契约，不要直接编码。

## WALI 顺序

- **Work**：明确目标、范围、约束、验收标准、检查方式、停止条件和用户确认项。
- **Assign**：先选执行方式，再拆解任务并明确负责人、依赖和允许修改范围。
- **Loop**：开发、自检、独立审查、测试、记录问题、修复和回归。
- **Inspect**：逐项把验收条件映射到真实证据；不满足时回到 Loop。

## 执行方式

始终选择能可靠完成任务的最简单方式：

1. 强上下文关联或小改动：主会话直接完成。
2. 独立调查、审查或测试，只需返回结论：使用 Subagent。
3. 任务边界清楚、并行收益明显且角色需要持续沟通：才使用 Agent Teams。
4. 同一文件修改或强顺序依赖：顺序执行；必要时再使用 Worktree 隔离。

不得为了展示团队能力而创建完整团队。并行执行前必须声明文件所有权，避免多个 Agent 无计划地修改同一文件。

## 角色

角色定义位于 `.claude/agents/`：

- `coordinator`：目标契约、执行方式、任务和状态协调、完成判断。
- `developer`：实现、自检和问题修复。
- `reviewer`：独立审查；默认只修改 `docs/wali-0x3/issues.md` 等治理文件，不直接修实现。
- `tester`：测试设计、复现、自动化测试和回归验证。

普通主会话按本文件承担 Coordinator 职责；需要以隔离的专用 Coordinator 系统提示启动时，使用 `claude --agent coordinator`。Coordinator 可以调用 `.claude/agents/` 中的角色，但仍须遵守“最简单执行方式”原则。

实现者不得作为唯一检查者。需要独立判断时，交给新的 Reviewer 或 Tester 上下文。

## 持久状态

- `goal.md`：完整目标契约和验收条件。
- `todo.md`：任务、依赖、所有权、状态和证据。
- `issues.md`：审查、测试及用户问题的闭环记录。
- `progress.md`：下一会话恢复所需的最小交接信息。

任务状态只使用 `pending → working → review → done`，无法推进时使用 `blocked`。代码修改完成只能进入 `review`；验证通过后才能进入 `done`。

问题状态只使用 `open → fixing → verify → closed`。未关闭的 `blocker` 会阻断目标完成。

目标状态：

- `draft`：目标仍在建立或等待确认，Stop Hook 不阻塞。
- `active`：当前阶段正在执行，Stop Hook 检查状态一致性。
- `waiting_user`：等待会改变实现方向的用户决定，或自动门禁满足后等待业务验收；必须填写 `waiting_for` 和 `waiting_detail`。
- `blocked`：存在已记录且无法自行解决的真实阻断；必须填写 `blocked_reason`。
- `done`：自动证据和用户验收均已完成；Stop Hook 仍会复核任务、问题和证据，不能靠改状态绕过。

不得用虚假的 `blocked`、`waiting_user` 或状态降级绕过检查。

## 验证与完成

- 先从仓库配置发现真实的构建、测试、Lint 和类型检查命令；不得臆造命令。
- 不得删除、跳过或弱化测试来获得通过结果。
- 运行与风险相称的检查，并在当前对话和状态文件中记录命令、退出结果、摘要与时间。
- 检查实际 Git 变更，确认没有越过目标范围或覆盖用户已有改动。
- 没有命令结果、差异检查、独立审查/测试和问题关闭证据，不得宣称完成。
- 自动条件满足后，将目标设为 `waiting_user`；只有用户真实回测通过后才能设为 `done`。

`/goal` 用于持续推进有明确终点的当前阶段；`/loop` 只用于等待 CI、部署、评论等外部状态，不用于反复驱动普通编码。

本仓库当前可用的 WALI 配置检查命令：

- `python3 .claude/hooks/test_wali_stop.py -v`：运行 Stop Hook 回归测试。
- `python3 .claude/hooks/wali_stop.py --project-root .`：检查当前 WALI 状态。
- `python3 -m json.tool .claude/settings.json`：验证项目设置 JSON。

业务项目的构建、测试和静态检查命令必须在初始化目标时从该项目的真实配置中发现，并写入 `goal.md` 与 `progress.md`；上述命令不替代业务项目验证。

## 会话结束

结束前运行必要验证，更新 `todo.md`、`issues.md` 和 `progress.md`，保留可继续工作的代码状态，并在对话中给出验收证据、剩余事项、风险和下一步。是否提交、推送或执行其他外部写操作，遵循用户授权和项目规则。
