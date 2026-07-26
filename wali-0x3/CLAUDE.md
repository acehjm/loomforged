# wali-0x3 项目约定

本项目使用 WALI（Work · Assign · Loop · Inspect）组织 Claude Code 开发工作。目标是让每项工作可分派、可检查、可恢复、可验收，而不是尽可能多地启动 Agent。

本仓库当前是可见存档形态，配置目录刻意保留为 `claude/`，不得在这里改回 `.claude/`。实际接入 Claude Code 时由使用者自行改名；文中的 `.claude/...` 表示部署后的运行路径。

## 1. 权威状态与写入原则

`docs/wali-0x3/` 下的五个文件共同保存项目级状态：

- `goal.md`：Goal、澄清与确认记录、验收条件、检查方式和当前阶段契约的唯一权威来源。
- `spec.md`：每个开发 Goal 固定存在的规范性开发与测试契约，保存 Requirement、行为、接口/数据/错误约束和验收判定规则。
- `todo.md`：任务、依赖、所有权、修改范围、状态和执行证据。
- `issues.md`：审查、测试和用户问题的闭环记录。
- `handoff.md`：始终覆盖为最新状态的恢复游标，不保存进度历史，不重复定义 Goal。

默认不创建这五份状态之外的上下文、计划、进度、记忆或图副本文件。`spec.md` 不是可选副产物，也不由外部 Skill 自行命名生成；它由 WALI 在固定路径维护。其他产物只有被已确认 Goal 纳入范围、且当前阶段允许创建时才能创建。

项目级知识按职责分层：`rules/` 保存必须遵守的规范性约束，`refs/` 保存模板、详细接口资料、兼容矩阵、示例和设计背景，`skills/` 保存可重复流程。Refs 不是运行状态，也不自动成为授权；Coordinator 只将当前 Goal 实际适用的 Rule/Ref 标识、版本和选择结果写入 `spec.md`。

## 2. 会话启动

开始或恢复任务时：

1. 确认当前目录就是 SVN 工作副本根，再读取工作副本 URL、修订信息、`svn status`、`svn diff --internal-diff` 和近期 `svn log`；网络与权限可用时再用 `svn status -u` 检查远端过期项。
2. 读取五个 WALI 状态文件。
3. 运行 `python3 .claude/hooks/wali_policy.py check`，按 `phase` 决定当前可以做什么。
4. 运行 `python3 .claude/hooks/wali_supervision.py --project-root . status`，将 Agent 运行事件与 WALI Task 状态交叉核对；存在未恢复失败时，先按恢复协议处理。
5. 用真实代码、SVN 差异和最新命令结果核对记录。冲突时以可验证事实为准，但修正记录仍必须符合当前写入范围。
6. 将调用前已存在或来源不明的本地修改视为用户资产：不覆盖、不回退、不擅自纳入当前任务。
7. 在新 Goal 的 `clarifying` 开始时运行 `wali_policy.py baseline`，将调用前已有 SVN 变更的路径、内容与属性指纹写入 `preexisting_changes`。只有指纹保持不变时，差异审计才会将它视为未触碰的用户资产。

## 3. Goal 先于计划

用户不需要一次性写出完整 Goal 或 Spec。Coordinator 根据输入采用两条入口，但收敛到同一套结果：模糊或缺失需求使用开放式访谈；用户已提供接口文档、需求或规格时使用规格压力测试，检查缺失、歧义、冲突、代码不一致和不可测试条款。两条路径都必须形成固定的 `spec.md`，再与 Goal 联合确认：

```text
提取已确认事实
→ 分开假设、缺失、歧义和冲突
→ 每轮询问 1–3 个最高影响问题
→ 将回答纳入事实与决策记录
→ 编译规范化 Spec
→ 生成 Goal + Spec 联合确认包
→ 获得用户明确确认
→ 再拆分任务和开始实现
```

即使用户已提供规格文档，也必须检查缺失、歧义、内部冲突、与实际代码的冲突，以及每项要求是否真正可验收。还要识别本 Goal 适用的项目 Rules 和 Refs，核对版本、适用范围与真实代码；已经回答的问题不重复询问，可逆且不影响 Goal 的细节可由 Coordinator 提出并标记为假设。

联合确认包至少包含目标、背景、范围、非范围、约束、逐项 Requirement、行为与接口/数据/错误契约、验收判定规则、精确检查方式、决策、保留风险和第一个可验证增量。沉默、未反对、Agent 自行概括都不是用户确认；从 `pending` 转为 `confirmed` 时，PreToolUse 必须再次请求用户核对当前 Goal 与 Spec。`goal_definition_digest` 同时封存两者，Spec 实质变化也必须撤销确认并返回澄清。用户业务验收从 `accepting` 进入 `delivering` 或 `closed` 时同样需要当场确认，Agent 可写的证据字段不能自证授权。

## 4. 阶段契约

`goal.md` frontmatter 中的下列字段共同定义当前权限，不能只看 `phase`：

```text
status + phase + active_task + goal_confirmation + goal_confirmation_evidence
+ goal_definition_digest + allowed_effects + allowed_capabilities + write_scope
+ preexisting_changes + carry_epoch + carried_history + carried_changes + stop_intent
+ exit_outcome + exit_reason + exit_evidence + exit_change_disposition + superseded_by
+ allow_new_artifacts + allow_implementation_changes
+ allow_external_writes + allow_svn_commit
```

`.claude/hooks/wali_policy.py` 对每个 phase 使用固定配置，任意增加 effect、放大路径或开启布尔开关都会导致检查失败。

| phase                | status         | 进入条件                         | 可写内容                                      | 实现/新产物/外部写/提交               |
| -------------------- | -------------- | ---------------------------- | ----------------------------------------- | --------------------------- |
| `clarifying`         | `draft`        | 新 Goal、规格待补全或已确认 Goal/Spec 发生实质变更 | `goal.md`、`spec.md`、`handoff.md`          | 全部禁止                        |
| `awaiting_direction` | `waiting_user` | 存在只有用户能决定的高影响方向问题            | `goal.md`、`handoff.md`                    | 全部禁止                        |
| `planning`           | `active`       | 用户明确联合确认 Goal + Spec 且已记录依据 | `goal.md`、`todo.md`、`issues.md`、`handoff.md` | 全部禁止                        |
| `implementing`       | `active`       | 选定一个可执行 `active_task`        | Goal 阶段转换、任务/问题/交接、`@active_task` 解析出的路径  | 允许实现、新产物和受控 SVN 工作副本操作；禁止外部写与提交 |
| `inspecting`         | `active`       | 活动任务实现与自检完成                  | Goal 阶段转换、任务/问题/交接                        | 全部禁止；只能运行 Goal 声明的检查        |
| `accepting`          | `waiting_user` | 自动 AC 和必要任务有证据               | `goal.md`、`issues.md`、`handoff.md`        | 全部禁止                        |
| `blocked`            | `blocked`      | 存在有证据且无法安全绕过的真实阻断            | `goal.md`、`handoff.md`                    | 全部禁止；不能借阻断状态提前规划            |
| `delivering`         | `done`         | 用户已验收，检查已在此前阶段完成，且已对精确差异清单明确授权 SVN 提交 | Goal 阶段转换、`handoff.md`、`svn_commit_paths` | 只允许只读复核和精确 SVN 提交；禁止运行项目命令与其他外部写 |
| `closed`             | `done`         | 已完成最终检查；日常冻结，仅可受确认地启动新 Goal | `handoff.md`；仅新 Goal 的 `goal.md` 受控重置       | 全部禁止                        |
| `terminated`         | `cancelled` / `superseded` / `aborted` | 用户取消、被新 Goal 替代，或安全/策略要求中止 | `handoff.md`；仅新 Goal 的 `goal.md` 受控重置      | 全部禁止；不得自动清理或回退           |

阶段转换必须一次更新完整契约字段组，并在下一个动作前通过策略检查。策略只接受定义好的相邻闭环或明确恢复路径，不能从实现直接跳过独立检查和用户验收进入终态；不得单独修改 `phase` 或布尔开关。`accepting → closed/delivering` 的写入前校验会直接检查完整工作图、自动与人工 AC、required Task、独立 Evidence、blocker 和实时 SVN 差异，不能先写成成功再等 Stop 补救。

## 5. 转段流程

```text
clarifying
   │ 用户明确联合确认 Goal + Spec
   ▼
planning
   │ 工作图合法，选定前沿任务
   ▼
implementing ◄── 发现问题/需要修复 ── inspecting
   │ 实现与自检完成               │ 独立检查通过
   └────────────────────────────┘
                                  │ 所有 automatic AC 完成
                                  ▼
                              accepting
                                  │ 用户业务验收
                   ┌──无需提交──────┴──已授权提交──┐
                   ▼                               ▼
                 closed                    delivering（提交后终态）
```

澄清或执行中需要用户选择方向时进入 `awaiting_direction`；自动验收完成后等待业务回测才进入 `accepting`。任何未关闭阶段都可因真实阻断进入 `blocked`。阻断消失后返回与当前证据相符的阶段。用户发出会改变已确认 Goal 的新要求时，撤销 Goal 确认并返回 `clarifying`。

`handoff` 和 `blocked` 都是可恢复暂停，不是退出。成功退出必须是 `completed`；取消、替代和安全中止统一进入 `terminated`，并记录退出类型、理由、证据、替代 Goal（若有）和未提交变更处置。进入非成功终态必须由用户当场确认，退出本身从不授权删除、回退或清理已有修改。

终态冻结当前 Goal，但不永久锁死系统。开始下一项工作时，只允许以不同的 Goal ID 发起受确认的重置事务；若上一 Goal 是 `superseded`，新 ID 必须与 `superseded_by` 一致。新契约必须回到最小 `clarifying` 权限，`carry_epoch` 归零、`carried_history`/`carried_changes` 和旧能力授权清空，当前全部非治理 SVN 差异重新写成不可修改的 `preexisting_changes`。随后只开放 Spec 身份修复通道，把固定 `spec.md` 更新为 `SPEC-<新 Goal ID>`，在 Goal/Spec 身份一致并刷新 handoff 前 Stop 始终拒绝；旧 Goal 的 carry 不能静默转成新 Goal 的实现授权。

## 6. WALI 与工作图

- **Work**：通过开放式访谈或规格压力测试建立 Goal、Spec、Requirement、范围、约束、AC、检查方式和退出条件。
- **Assign**：先选择最简单可靠的执行方式，再拆分任务、声明依赖、负责人和精确修改范围。
- **Loop**：实现、自检、独立审查、测试、记录问题、修复和回归。
- **Inspect**：逐项把 AC 映射到真实证据；不满足时回到 Loop，不用总结代替验证。

这里采用的是 Graph Engineering，而不是 GraphRAG：五个状态文件中的稳定 ID 和关系字段构成可执行工作图。Goal 包含 Requirement，Requirement 定义 AC，Task 实现 AC 并声明依赖、修改范围与可选 Skill，Evidence 证明 AC/Task，Issue 阻断或影响 Task/AC，负责人和独立验证者建立责任关系，Skill → Task 表示方法关联。检查器据此验证 Requirement → AC → Task → Evidence 主链、Skill 是否已获 Goal 授权、引用、依赖、阻断、范围重叠、当前任务和证据完整性；任何标记为 `verified` 的 AC 必须已有真实证据，任何 `done` Task 必须已有执行证据和不同于负责人的独立验证者，`verified` automatic AC 至少关联一个已完成的 required Task。图只在内存中从 Markdown 派生，不创建图数据库、向量检索或持久图副本。

任务只能从当前可执行前沿认领。策略层一次只授权一个 `active_task`；并行候选用于编排判断，真正并行写入必须使用各自独立的 SVN 工作副本和阶段契约。根级通配范围以及 `.claude/**`、存档形态的 `claude/**`、`CLAUDE.md` 控制面范围不能成为普通任务写入范围。

## 7. 执行方式与角色

始终选择能可靠完成任务的最简单方式：

1. 强上下文关联或小改动：主会话直接完成。
2. 独立调查、审查或测试，只需返回结论：使用 Subagent。
3. 任务边界清楚、并行收益明显且角色需持续沟通：才使用 Agent Teams。
4. 同一文件或强顺序依赖：顺序执行；确需隔离时使用独立 SVN 工作副本。

角色定义位于 `.claude/agents/`：

- `coordinator`：开放式访谈/规格压力测试、Goal + Spec 联合确认、阶段转换、工作图和退出判断。
- `architect`：按需启用的只读技术顾问；只在跨模块边界、接口/数据迁移、重要质量属性或高代价技术分歧会改变规范时提供方案比较与验证建议，不拥有 Goal/Spec，也不直接实现。
- `developer`：只在 `implementing` 中实施当前活动任务、自检和修复问题。
- `reviewer`：只在 `inspecting` 中进行独立审查，默认不修实现。
- `tester`：只在 `inspecting` 中从可观察结果和反例进行独立验证。

实现者不得成为唯一检查者。主会话默认承担 Coordinator 职责。

角色模型与思考深度使用稳定家族别名和显式 `effort`：

| 角色 | 默认模型 | 默认 effort | 选择依据 |
| --- | --- | --- | --- |
| Coordinator | `opus` | `high` | 长程规划和多 Agent 编排需要强判断，同时避免整个团队默认进入高成本档 |
| Architect | `opus` | `xhigh` | 只处理高影响、跨边界和难以逆转的技术决策 |
| Reviewer | `opus` | `high` | 独立发现遗漏、边界和高代价缺陷 |
| Developer | `sonnet` | `high` | 兼顾复杂编码能力、速度和成本 |
| Tester | `sonnet` | `high` | 需要严谨反例推演，但主要结论仍由可重复实验提供 |

项目 `settings.json` 同时把默认主会话设为 `opus/high`，覆盖“主会话直接承担 Coordinator、但没有通过 Agent 定义启动”的情况。不为当前角色固定使用 Haiku，也不把 `max` 固化到 frontmatter；`max` 只用于 `xhigh` 仍不足、失败代价极高且用户接受额外延迟/成本的单次任务。普通 Subagent 采用自身 `model`/`effort`；Agent Teams teammate 采用角色定义的 `model`，但 `effort` 继承 lead。若只需 Architect 使用 `xhigh`，优先单独调用它，而不是把整个团队一起升档。命令行、环境变量或组织上限可能覆盖/压低项目设置和 frontmatter，运行时以 Claude Code 显示的实际模型和 effort 为准。

给角色扩展 Skill 时，不能只新增目录。完整接入同时要求：

1. 在 `.claude/skills/<name>/SKILL.md` 提供声明式定义，使用安全 frontmatter，并设置 `disable-model-invocation: true`。
2. 相关 Agent 的 `tools` 包含 `Skill`；其身份说明定义何时使用、期望输出和停止条件，但不复制 Skill 的完整步骤。
3. 在联合确认前把 `Skill:<name>` 纳入当前 Goal 的 `allowed_capabilities`；确认后新增或替换能力属于 Goal 定义变化，必须返回 `clarifying`。
4. 在需要它的 Task 的 `所用 Skill` 中建立 Skill → Task 方法边。若只是角色固有方法且无需独立 Skill，可写“无”。
5. Skill 的每个真实动作仍受 phase、effect、`write_scope` 和 SVN 审计约束。

如果新 Skill 只细化现有角色方法，不改变职责、工具、输出或权限，不必为每个名称改写 Agent；使用上述通用调用契约即可。只有它改变角色边界或交接协议时，才更新 Agent 定义。通用代码审查可作为 Reviewer 的按需 Skill；合规审计还必须由 Spec 指明适用标准、版本、范围和判定规则，不能让一个无项目依据的“合规 Skill”自行发明标准。Developer 的语言/框架 Skill 同理：它提供实现方法，Spec、Rules 和现有代码仍决定约束。

## 8. 能力不等于权限

Skill、Agent、脚本、MCP 或未来能力只提供方法，不自动获得仓库或外部系统写入权。不维护具体 Skill 名称或生成文件名的黑名单，而是统一处理：

```text
运行环境：关闭 Skill 加载期 shell 执行
→ 调用前：能力必须位于项目内并列入 allowed_capabilities
→ frontmatter 只接受安全字段，拒绝预加载 Skill/MCP、memory、lifecycle hook、动态 shell 或绕过权限配置
→ 将后续动作与 allowed_effects、write_scope 和四个开关求交集
→ 副作用不明时默认拒绝
→ 调用后用 SVN 差异审计核对真实结果
```

这条规则直接覆盖会自动创建 `context.md`、计划或其他文件的未知流程：不是因为文件名被列入黑名单，而是因为能力未获显式授权、定义存在加载期副作用，或真实写入不在当前 effect/scope 内。`settings.json` 的 `disableSkillShellExecution` 关闭 Skill 加载期 shell；PreToolUse 检查能力定义和工具动作，PostToolUse 与 Stop 检查阶段契约及 SVN 差异。

项目特有资料按 `.claude/refs/INDEX.md` 分类。硬性依赖版本、禁用库、安全要求和必须使用的模板属于 Rules；详细依赖兼容矩阵、模板正文、API 示例和设计理由属于 Refs；本 Goal 最终选择的版本、模板和例外进入 Spec。普通开发 Goal 不能修改 `rules/`、`refs/`、`skills/` 或 Agent 定义，这些内容属于控制面。

读取型 Bash 也不等于任意 shell：普通文件读取与搜索必须使用结构化 Read/Glob/Grep 工具；Bash 读取白名单只保留无参数 `pwd`、参数模式受限的 WALI 命令和严格 SVN 只读命令。策略拒绝重定向、管道、变量/命令替换、未引用的 brace/glob、反斜线展开、外部配置与外部 diff；`svn diff` 必须显式使用 `--internal-diff`。不靠命令名或 shell 展开绕过路径校验。

在 SVN 工作副本中，PreToolUse 还会把五个 WALI 状态文件的动作前指纹暂存到 `.svn/wali-policy/`；PostToolUse 对照后删除快照，用于发现普通命令的意外越界。该目录属于工作副本本地元数据，不是项目产物，也不进入 SVN。

WALI 是确定性的授权与审计层，不是操作系统沙箱。Hook、SVN 客户端与服务端、用户，以及获准项目命令和它们加载的全部传递代码属于可信计算基础；同一系统用户运行的恶意子进程理论上能够篡改本地快照或回执。只有来源和依赖均可信的命令才可写入 Goal 检查表并在本地执行；不满足这一前提时，Agent 必须停止本地执行，改由用户在隔离环境或 CI 中运行并带回证据。`delivering` 完全禁止项目命令，避免把提交阶段继续暴露给可执行项目代码。本地快照和回执提供一致性证据，但不冒充跨权限安全边界。

## 9. 状态、证据与完成

- Task：`pending → working → review → done`；无法推进时使用 `blocked`。实现者不能跳过独立验证直接设为 `done`。
- Agent 运行状态与 Task 状态分离：Agent 的 `running/waiting/idle/completed/needs_attention/failed` 只描述一次运行，不自动改变 Task。Agent Teams 共享任务标题必须包含且只能包含一个稳定 `T-XXX`，例如 `[T-001] 实现支付校验`。
- Issue：`open → fixing → verify → closed`。修复者不能只凭自检关闭问题。
- Requirement：使用 `R-XXX` 稳定 ID，必须关联至少一个 AC；每个 AC 也必须有 Requirement 和 Spec 判定规则。
- AC：`automatic` 或 `human`，状态为 `pending` 或 `verified`。`verified` 必须有真实证据。

`TaskCompleted` 和 `TeammateIdle` 会阻止“活动 Task 仍为 working、缺证据却完成或空闲”等不一致；`StopFailure` 只能记录失败，不能阻止异常退出。监督事件保存在 SVN 本地元数据 `.svn/wali-policy/supervision.json`，不创建新的项目状态文件。发现失败时先核对 Agent 面板/`/tasks`、transcript、Task、SVN 差异和本地事件；优先恢复原 Agent，替代前冻结对应 Task 与路径所有权并完成差异审计，不自动清理、覆盖或提交。只有绑定当前 `active_task` 的失败才形成强制恢复要求；无活动任务的 Coordinator/顾问失败保留为诊断事件，不虚构 Task 状态。若活动任务恢复尚未完成就交接，`handoff.md` 必须记录事件 ID、恢复动作和可验证证据。

只从项目配置发现真实的构建、测试、Lint 和类型检查命令。要执行的项目命令必须用完整行内代码记号写入 `goal.md` 的“检查方式”表；策略 Hook 只允许读取型命令或与该表完全一致的命令。

不得删除、跳过、弱化测试或伪造证据。没有精确命令与退出结果、SVN 差异审计、独立审查/测试和问题闭环证据，不得声称完成。自动条件满足后进入 `accepting`；只有用户真实业务回测通过且成功收尾校验无错误，才能进入 `delivering` 或 `closed`。`closed` 允许在冻结状态下刷新 handoff，避免 Goal 已关闭但交接摘要仍停留在上一阶段。

## 10. SVN 与外部写入

SVN 提交会直接写入共享仓库，没有独立的本地 Commit 后 Push 阶段。除 `delivering` 外，`allow_svn_commit` 始终为 `false`，而 `allow_external_writes` 在 `delivering` 仍为 `false`。所有有副作用动作、handoff 摘要、Stop 和提交前审计都用 `svn info --show-item wc-root` 发现真实工作副本根，不能用当前目录是否恰好存在 `.svn` 判断；从普通子目录启动、元数据不可验证或无法保存动作快照时直接拒绝，不把失败推迟到提交之后。

`implementing` 中只对状态为 `working` 的 `active_task` 开放两类受控工作副本操作：`svn add/delete/move/copy` 用于调整任务范围内的精确 leaf path 调度状态，`svn update -- <exact-path>...` 与 `svn resolve --accept working -- <exact-path>...` 用于同步或确认任务范围内的冲突处理结果。目录目标、范围外路径、用户保护基线、控制面、其他 resolve 策略和所有未列出的 SVN 变更命令都拒绝。若交付前发现过期或冲突，必须回到或新建合法的 `implementing` 活动任务，精确同步、显式编辑解决冲突、重新验证并 `carry`，不能在 `delivering` 中顺手更新。

进入 `delivering` 前必须：

1. 用户已完成业务验收。
2. 使用 `carry` 生成当前差异代次；每轮修复递增 `carry_epoch`，把上一代只追加到 `carried_history`，并以新 `carried_changes` 冻结当前内容。检查、验收和交付阶段不得静默改变当前代。
3. 用户已对 `svn_commit_paths` 中逐个精确文件明确授权提交；该清单必须覆盖本轮需要提交的实现和 WALI 状态差异。
4. `svn_commit_evidence` 记录可追溯的历史依据；它只是审计记录，不是授权令牌。受影响验证必须已在进入 `delivering` 前完成。

只接受 `svn commit (-m|--message) <literal> -- <exact-leaf-path>...`；拒绝目录目标、`--targets`、`--editor-cmd`、externals、变量展开和串联命令。即使契约和差异校验全部通过，每一次实际提交的 PreToolUse 仍必须返回 `ask`，由用户当场核对命令与路径并确认；Agent 自填的 `svn_commit_evidence` 不能静默放行远程写入。PreToolUse 还要求每个目标都是当前真实差异和 SVN 可证明的 leaf file，并保存逐路径提交前状态；PostToolUse 只在成功工具响应给出唯一提交修订号、授权路径已无差异、现存路径的 `last-changed-revision` 等于本次修订时，才在 `.svn/wali-policy/` 写入绑定 Goal、carry 代次、授权摘要、提交前证据、路径、指纹和统一修订号的本地交付回执。删除路径也绑定同一个真实提交修订号；Stop 会重新核对工作副本、回执和当前授权，空提交不能生成回执。SVN 更新、解决冲突或扩大提交范围不是提交授权的隐含部分。提交前仍有授权差异时，可在用户确认后撤销提交授权、清除 `svn_commit_paths/evidence` 并让原 Goal 回到 `clarifying`；授权路径已清洁但回执无效时只能查明后进入 `terminated`；精确提交与有效回执都完成后，`delivering` 是冻结终态，只能以不同 ID 启动新 Goal。无需提交时使用 `closed`。部署、发布、创建工单等其他外部写入需要独立 effect 和授权，不能复用 SVN 提交权限。

## 11. WALI 命令

- `python3 .claude/hooks/test_wali_policy.py -v`：运行阶段契约、工具决策和 SVN 差异审计回归测试。
- `python3 .claude/hooks/test_wali_stop.py -v`：运行停止状态回归测试。
- `python3 .claude/hooks/test_wali_graph.py -v`：运行工作图回归测试。
- `python3 .claude/hooks/test_wali_supervision.py -v`：运行 Agent 监督、事件 Hook 和异常恢复回归测试。
- `python3 .claude/hooks/wali_policy.py check`：检查当前阶段契约。
- `python3 .claude/hooks/wali_policy.py audit`：在 SVN 工作副本中检查实际差异、新产物和写入范围。
- `python3 .claude/hooks/wali_policy.py baseline`：输出当前 SVN 变更的项目相对路径、内容与属性指纹，用于保护新 Goal 开始前的用户修改。
- `python3 .claude/hooks/wali_policy.py digest`：生成待联合确认的 Goal 稳定定义与完整 Spec 摘要；用户确认后写入 `goal_definition_digest`，任一方后续实质变化都必须重新澄清。
- `python3 .claude/hooks/wali_policy.py handoff-digest`：生成当前 Goal、Spec、任务图和 SVN 工作副本的恢复状态摘要，更新交接正文后写入 `handoff.md` 的 `state_digest`。
- `python3 .claude/hooks/wali_policy.py carry`：输出递增代次、只追加历史和当前合法差异指纹，原子写入 `carry_epoch`、`carried_history` 与 `carried_changes`。
- `python3 .claude/hooks/wali_stop.py --project-root .`：检查当前是否可停止。
- `python3 .claude/hooks/wali_graph.py --project-root . check`：检查图关系、引用、依赖环和范围冲突。
- `python3 .claude/hooks/wali_graph.py --project-root . frontier`：列出当前可执行任务。
- `python3 .claude/hooks/wali_graph.py --project-root . parallel`：列出安全并行候选。
- `python3 .claude/hooks/wali_graph.py --project-root . mermaid`：按需将派生工作图输出到标准输出，不创建持久副本。
- `python3 .claude/hooks/wali_supervision.py --project-root . status`：读取本地 Agent 运行事件、失败状态和待恢复要求。
- `python3 -m json.tool .claude/settings.json`：验证 Claude Code 设置 JSON。

`/goal` 用于持续推进已有明确终点的当前阶段；`/loop` 只用于等待 CI、部署、评论等外部状态，不用于反复驱动普通编码。

## 12. 会话结束

结束前运行当前 phase 允许的必要检查，更新被授权的状态文件，运行阶段契约、Agent 监督状态和 SVN 差异审计，并在对话中给出与 `handoff.md` 一致的证据、剩余事项、风险、当前权限边界和唯一的下一步。存在与当前活动任务绑定的未恢复失败时，交接必须填写 `supervision_event`、`recovery_action` 和 `recovery_evidence`。最后运行 `wali_policy.py handoff-digest` 刷新 `handoff.md.state_digest`；该摘要绑定完整 Goal、完整 Spec、任务/问题状态、交接正文和非治理文件的工作副本差异。工作尚未完成但需要结束会话时，在刷新摘要后将 `stop_intent` 设为 `handoff`；这表示可恢复暂停，不表示完成或退出。Stop 不只比对镜像字段，还会拒绝摘要已过期或缺少活动任务异常恢复计划的交接。
