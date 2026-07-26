---
name: wali-0x3-core-design
title: wali-0x3 核心设计
status: implemented
version: 0.14
date: 2026-07-26
---

# wali-0x3 核心设计

## 1. 定位

`wali-0x3` 是一套主要运行在 Claude Code 中、嵌入代码仓库使用的虚拟开发协作与验证机制。

它不以启动更多 Agent 为目标，而是通过目标契约、执行编排、持续验证和状态交接，让一项开发工作真正做到：

> **可分派、可检查、可恢复、可验收。**

完整过程如下：

```text
目标清楚
   ↓
选择合适的执行方式
   ↓
任务有人负责
   ↓
开发持续推进
   ↓
问题得到处理
   ↓
结果经过验证
   ↓
中断后能够恢复
   ↓
有价值的经验得到沉淀
```

`wali-0x3` 不替代 Claude Code 自身的 Agent 能力，而是在这些能力之上建立项目级开发闭环。

## 2. WALI 工作方式

WALI 代表：

> **Work · Assign · Loop · Inspect**

对应中文含义：

> **明确工作、分配任务、循环执行、检查结果。**

```text
Work
明确目标、范围、约束和完成标准
   ↓
Assign
拆解任务，选择执行方式，分配责任
   ↓
Loop
持续开发、审查、测试和修复
   ↓
Inspect
依据真实证据检查目标是否完成
   └──────── 未满足时重新进入 Loop
```

WALI 不只是名称解释，也是每轮开发工作的实际执行顺序。

## 3. 整体运行模型

`wali-0x3` 采用四层运行模型：

```text
第一层：目标层
由 goal.md、spec.md 和 /goal 定义意图、规范与完成条件。

第二层：编排层
由 Coordinator 选择主会话、Subagent 或 Agent Teams，并分派任务。

第三层：执行层
由 Claude Code 原生 Agentic Loop 完成读取、修改、运行和验证。

第四层：治理层
由任务状态、问题清单、Hooks、Reviewer、Tester 和用户共同控制完成。
```

其中，Claude Code 已经负责微观执行循环：读取上下文、使用工具、观察结果并继续调整。`wali-0x3` 不重复设计模型内部循环，而是负责向它提供清晰目标、稳定状态、角色边界和完成检查规则。

## 4. 设计原则

### 4.1 先定义完成，再开始执行

“完成某个功能”不是有效目标。开始执行前必须说明：

- 最终结果是什么。
- 允许修改什么。
- 不允许修改什么。
- 如何证明已经完成。
- 哪些失败会阻断完成。
- 哪些事项必须由用户确认。

### 4.2 默认使用最简单的执行方式

不是所有任务都需要完整团队。只有并行收益明显、任务边界清楚时才启用多 Agent。

能够由单个会话稳定完成的任务，不主动增加协调成本。

### 4.3 文件保存长期状态

会话消息、Agent Teams 共享任务和内部 Todo 可以服务当前运行，但不能成为项目的唯一状态来源。

目标、任务、问题、交接状态和关键证据应保存在代码仓库中，使新的会话能够重新建立上下文。

### 4.4 一次推进一个可验证增量

长时间任务不追求一次完成全部功能。每轮应选择一个明确、可验证、能够留下干净状态的增量。

任何会话结束前，都应尽量保证：

- 当前代码可以构建或至少回到已知状态。
- 半成品有明确记录。
- 下一会话无需猜测之前做了什么。

### 4.5 代码修改不等于任务完成

Developer 完成修改，只代表实现阶段结束。任务还需要经过必要的构建、测试、审查和问题关闭。

### 4.6 完成必须有证据

任何 Agent 都不能只依赖自我声明宣布完成。完成结论应由命令结果、代码差异、测试记录、审查结论和回归结果支持。

### 4.7 检查者与实现者尽量分离

需要独立判断的审查和测试，应尽量由新的上下文执行。刚完成实现的 Agent 容易沿用原有假设，不适合作为唯一检查者。

### 4.8 用户保留最终业务验收权

Agent 可以完成技术检查和自动验收，但真实业务结果是否可接受，最终由用户确认。

### 4.9 记忆只沉淀经过验证的结论

当前进度、临时问题、一次性绕行方案和未经验证的猜测不进入全局记忆。

只有经过开发、审查或测试验证，并具有跨项目复用价值的内容，才作为记忆候选。

## 5. 执行方式选择

Coordinator 在拆解任务前，先判断采用哪种执行方式。

```text
主会话
适合快速修改、强上下文关联、需要持续来回调整的任务。

Subagent
适合独立调查、代码审查、测试分析和只需要返回结论的子任务。

Agent Teams
适合多个角色需要持续并行、共享任务并相互沟通的复杂工作。

顺序执行
适合同一文件修改、前后依赖明显或并行冲突较大的任务。
```

建议判断顺序：

```text
任务能否由主会话直接完成？
   ├── 能：使用主会话
   └── 不能
        ↓
是否只需要独立结果，不需要角色间持续沟通？
   ├── 是：使用 Subagent
   └── 否
        ↓
任务是否可以按模块独立推进，并需要相互协调？
   ├── 是：使用 Agent Teams
   └── 否：重新拆解或顺序执行
```

适合 Agent Teams 的典型情况：

- 前端、后端和测试可以分别负责独立模块。
- 多个 Agent 可以并行验证不同调试假设。
- 多个审查角色需要相互质疑和综合结论。
- 新功能可以按边界清晰的模块拆分。

不适合 Agent Teams 的情况：

- 多个任务需要频繁修改同一文件。
- 工作具有强顺序依赖。
- 任务很小，沟通成本高于执行成本。
- 各角色无法独立验证自己的输出。

如多个会话会修改代码，应优先划分清晰的文件所有权；需要进一步隔离时，再使用独立 SVN 工作副本。独立工作副本只隔离本地修改，不替代提交前的更新、冲突检查和协调。

### 5.1 能力调用与仓库副作用契约

Skill、Agent、脚本和工具是能力来源，不是写入授权来源。Coordinator 不维护某个具体能力或文件名的黑名单，而是对所有当前与未来能力使用同一套副作用契约：

```text
调用前
→ 运行环境关闭 Skill 加载期 shell 执行
→ 能力必须列入 allowed_capabilities，且定义位于项目内
→ frontmatter 只接受安全字段；拒绝预加载 Skill/MCP、memory、lifecycle hook、动态 shell 和绕过权限配置
→ 再与 Goal 范围、任务允许修改范围和用户授权求交集
→ 只有声明式能力及其动作都落在交集内，才直接调用

副作用未知或超出范围
→ 默认拒绝调用
→ 可采用其方法，由 WALI 自己控制写入
→ 确有必要时，将能力本地化、移除加载期副作用并请用户确认能力清单

调用后
→ 检查 svn status 和实际差异
→ 不把自动生成物默认为项目资产
→ 不触碰调用前已存在或来源不明的用户文件
```

为避免将工作副本中原本就存在的用户修改误判为 Agent 越界，新 Goal 开始时由 `wali_policy.py baseline` 为当前 SVN 变更生成路径、内容与 SVN 属性指纹。差异审计只在指纹保持不变时忽略该既有变更；一旦其内容或属性在基线后改变，仍按越界处理。用户确认后的 `goal_definition_digest` 同时绑定这份基线与能力清单，不能在不重新确认 Goal 的情况下事后改写。

项目级本地产物由人维护的版本化 `svn:ignore` 或 `svn:global-ignores` 属性声明。`wali_svn.py` 清空个人客户端的 `global-ignores` 后运行 `svn status --xml --no-ignore`，把项目属性命中且属性链没有本地修改的 `ignored` 项与需审计变化分开。

这些本地产物不进入 baseline、carry、handoff 摘要、Stop 阻断或提交清单，但仍保留在原始状态中供诊断。普通未版本化文件、属性变化、冲突和 externals 继续审计；WALI 不推断规则、不创建 `.svnignore`，也不自动写入 SVN 属性。

WALI 的治理状态默认只允许落入固定的 `goal.md`、`spec.md`、`todo.md`、`issues.md` 和 `handoff.md`。`spec.md` 是每个开发 Goal 的必备规范契约，不是外部 Skill 可自由命名生成的附属文件。额外的上下文、计划、进度、图副本或发布产物，只有在目标契约列入范围或用户明确授权时才能创建。

这个约束同时位于项目规则、Agent 身份和工具 Hook 层。Skill 或 Agent 在加载前先经过通用能力预检，其后的每个实际工具动作继续通过同一阶段契约。因此，即使某个环境没有特定 Skill，或未来换成名称不同但行为相似的能力，约束仍然成立，也不会因未知流程默认生成 `context.md` 等文件。

### 5.2 跨项目参考与项目资料分层

WALI 会被用于许多快速迭代且彼此不同的项目。用户为单个项目提供的需求、规格、接口协议、模块边界、模板、依赖和代码检查要求应保留在该项目的 `docs/`，再把可执行结论编译进固定的 `spec.md`。

真正跨项目稳定的 WALI 说明、开发模板和企业内部代码检查基线可以进入 `refs/`。它们由 `refs/INDEX.md` 按读取角色与触发场景路由，不要求每个项目重复维护，也不把项目特例提升成共享惯例。

```text
跨项目且所有会话都必须知道的稳定事实
→ CLAUDE.md

跨项目且违反就应阻止交付的硬约束
→ rules/

跨项目稳定、按角色与场景查阅的说明、模板和检查基线
→ refs/

跨项目可重复的多步骤方法
→ skills/

本项目用户资料的来源与当前 Goal 的规范化结论
→ 项目 docs/ + spec.md

当前 Goal 实际适用的通用规则、参考和例外
→ spec.md
```

Rule 应短、可判定并尽量通过 `paths` 限定适用范围。Ref 是可直接读取的静态参考，不是 Skill，也不自动产生权限或约束。跨项目通用的开发模板与代码检查基线可以作为 Ref；项目特有的强制模板、依赖版本、供应商接口、模块设计和检查要求仍由用户资料与 Spec 定义。

`refs/INDEX.md` 是共享参考的总路由。Agent 根据读取角色和触发场景选择 Ref；新增同类 Ref 通常只增加文件并维护相应索引，不需要逐个改写 Agent，也不建立 Skill → Task 方法边。

Coordinator 记录项目资料的相对路径、版本或日期、适用范围和采用结论。普通项目迭代不修改 Agents、Rules、Refs 或 Skills；只有 WALI 行为、Claude Code 能力或跨项目惯例稳定变化时，才把共享资料修改作为独立任务审查。

角色扩展同样使用分层接入。把一个 `SKILL.md` 放进目录只是“能力存在”，还不是“能力可用”。完整链路是：

```text
项目内声明式 Skill 定义
→ Agent 的 tools 包含 Skill，并定义使用时机、输出和停止条件
→ 联合确认前写入 Goal.allowed_capabilities
→ 具体 Task 的“所用 Skill”建立 Skill → Task 方法边
→ 每个实际动作继续接受 phase/effect/scope/SVN 检查
```

如果 Skill 只是细化角色已有方法，例如某语言开发方法或通用代码审查，Agent 身份保留通用调用契约即可，不必硬编码每个 Skill 名称。只有新 Skill 改变角色职责、工具、输出或交接协议时才改 Agent 定义。

代码合规基线本身属于 Ref，不需要包装成 Skill。只有形成可重复的多步骤检查方法时才考虑 Skill；即便如此，Spec 仍须明确项目适用的标准、版本、范围和例外，Skill 只执行已确定的基线。

## 6. 目标契约

每轮工作都应建立目标契约，用来约束任务拆解、开发、审查和完成判断。

目标层由两份互补而不竞争的契约组成：`goal.md` 保存意图、范围、阶段、运行时 AC 状态与证据；`spec.md` 保存规范性 Requirement、行为、接口/数据/错误、质量约束和测试判定规则。两者共同至少覆盖：

```text
目标
背景
范围
不在范围内的内容
约束
验收标准
检查方式
暂停与退出条件
需要用户确认的事项
```

### 6.1 用渐进式澄清建立 Goal

这一段吸收的是 Matt Pocock 工程 Skill 体系中的方法链，而不是对某个 Matt Skill 的运行时依赖：先通过 ask/grill 式访谈暴露高影响未知项，再把共识收敛成 spec，随后拆成带依赖和验收条件的 tracer-bullet 任务，最后进入 implement/review/test 闭环。WALI 把这条方法链内化到 `wali-start`、Goal 模板、Coordinator、工作图和策略 Hook；即使环境没有这些外部 Skill，行为仍成立，也不会触发它们默认生成 `context.md` 等产物。

用户的责任是表达问题、意图和已知约束，不是一次性填完 Goal 模板。Coordinator 采用可恢复的多轮澄清流程：

```text
分类输入：模糊需求 / 已有资料 / 已确认 Goal 的增量变更
→ 提取已确认事实
→ 标记假设、缺失、歧义和冲突
→ 每轮询问 1–3 个最高影响问题
→ 将回答纳入事实和决策记录
→ 重新评估剩余未知项
→ 编译规范化 spec.md
→ 生成 Goal + Spec 联合确认包
```

没有规格或只有模糊意图时，Coordinator 使用开放式访谈：先理解目标用户、场景、期望结果和失败影响，再逐步询问范围、边界、约束和证据。已有接口文档、需求或规格时，不重新做漫无目的访谈，而是执行规格压力测试：检查缺失、歧义、内部冲突、与真实代码冲突，以及无法形成测试 oracle 的条款。两条路径可在 `hybrid` 模式合并，最终都编译到相同结构的 `spec.md`。已回答的问题不重复询问；可安全逆转、不改变 Goal 的细节可以作为显式假设，不必把所有细节都推给用户。

### 6.2 确认是实施前的明确事件

联合确认包包含目标、背景、范围、非范围、逐项 Requirement、行为与接口/数据/错误约束、AC 判定规则、检查方式、决策、保留风险和第一个垂直增量。在用户明确确认之前：

- Goal 保持 `draft` 和 `clarifying`。
- 只能更新固定的 `goal.md`、`spec.md` 与 `handoff.md`。
- 不创建实施任务、不修改代码、不创建其他产物。
- 沉默、未反对、Agent 自行概括都不视为确认。

确认后必须记录 `goal_confirmation_evidence`，并将 `wali_policy.py digest` 的结果写入 `goal_definition_digest`，才能进入 `planning`。该字段是审计记录，不是 Agent 自己签发的授权：pending → confirmed 的 PreToolUse 仍会请求用户当场核对完整 Goal + Spec；`accepting` 进入 `delivering`/`closed` 时也会再次请求用户确认真实业务验收。摘要绑定 Goal 稳定定义、完整规范化 Spec、用户修改基线和能力清单，但允许后续更新验收状态与证据。Goal 或 Spec 任一方发生实质变化，都必须清空确认依据与摘要并返回 `clarifying`。

### 6.3 验收标准必须可验证

验收标准应描述可观察结果，而不是模糊过程。例如：

```markdown
## 验收标准

- 用户可以创建并保存审批流程草稿。
- 重新进入页面后可以继续编辑草稿。
- 保存失败时展示明确错误信息。
- 已有审批流程不受影响。
- 项目构建、静态检查和约定测试通过。
- 不存在未关闭的阻断问题。
- 用户完成一次真实业务回测。
```

任务、问题和证据都应能追溯到具体验收条件：

```text
目标 G-01
├── 需求 R-01 → 验收条件 AC-01 → 任务 T-01/T-02 → 证据 E-01
├── 需求 R-02 → 验收条件 AC-02 → 任务 T-03 → 证据 E-02
└── 需求 R-03 → 验收条件 AC-03 → 问题 I-01 → 回归证据 E-03
```

### 6.4 阶段契约是可执行的权限模型

`goal.md` frontmatter 不只记录阶段名称，还定义当前动作的最小权限：

```text
status + phase + active_task
+ goal_confirmation + goal_confirmation_evidence
+ goal_definition_digest
+ allowed_effects + allowed_capabilities + write_scope
+ preexisting_changes + carry_epoch + carried_history + carried_changes + stop_intent
+ exit_outcome + exit_reason + exit_evidence + exit_change_disposition + superseded_by
+ allow_new_artifacts
+ allow_implementation_changes
+ allow_external_writes
+ allow_svn_commit
```

frontmatter 还必须声明 `wali_schema: 1`。Policy 对缺失或未知版本 fail closed，不对旧 Goal 做静默迁移；状态格式升级必须同时修改模板、Policy、兼容说明和回归测试。

系统使用固定 phase profile，覆盖 `clarifying`、`awaiting_direction`、`planning`、`implementing`、`inspecting`、`accepting`、`blocked`、`delivering`、`closed` 和 `terminated`。`awaiting_direction` 专门等待用户选择实现方向，`accepting` 专门等待业务验收，`blocked` 只保存 Goal 与交接，不能借此提前规划；`terminated` 专门表示取消、替代或安全中止，不得伪装成功完成。任意放大 effect、路径或布尔开关都会被判为不一致。阶段转换必须原子化更新完整字段组，并符合显式转换图；实现不能直接跳过 `inspecting` 与 `accepting` 进入成功终态，不能只修改 `phase` 绕过约束。`accepting → closed/delivering` 还要在 PreToolUse 对 prospective Goal 执行完整成功收尾校验，不能先写入成功状态、再把缺失证据留给 Stop 发现。

实现差异采用代次模型：`carry_epoch` 从 0 开始，每次实现或修复准备进入检查时恰好递增 1；上一代 `carried_changes` 以“代次 + 路径 + 指纹”只追加到 `carried_history`，当前实时差异成为新一代 `carried_changes`。因此检查发现问题后可以合法回到 `implementing` 修改同一路径并再次冻结，同时任何 Agent 都不能覆盖旧指纹来抹掉审计轨迹。未变化、但来自其他已完成任务的当前代路径可以原样继承；发生变化或新增的路径仍必须属于当前活动任务。

`settings.json` 的 `disableSkillShellExecution` 关闭 Skill 加载期 shell。PreToolUse Hook 在动作前检查能力定义、工具、effect、路径和开关，并在 SVN 本地元数据 `.svn/wali-policy/` 暂存五个治理文件的动作前指纹；PostToolUse 在可能发生写入后对照并删除快照，再复查契约与 SVN 差异，用于发现正常工具和可信项目命令的意外越界。该快照目录不进入 SVN。

WALI 要求 SVN 1.9+。所有有副作用动作、handoff 摘要与 Stop 都通过 `svn info --show-item wc-root` 发现工作副本边界，因此普通子目录不会因本地没有 `.svn` 而绕过检查。Stop Hook 在会话尝试停止前再次检查阶段、工作图、交接摘要或完成证据；`delivering` 还必须具备成功提交回执。

无效契约只开放前瞻、收窄的恢复通道：重建完整 `clarifying` Goal，或在终态换新 Goal 后只修复固定 Spec 的 Goal/Spec 身份绑定。

这套机制的威胁模型必须说清楚：WALI 是授权与审计层，不是 OS 级安全沙箱。Hook、SVN 客户端与服务端、用户，以及 Goal 明确批准的项目命令及其全部传递代码组成可信计算基础。同一系统用户下的对抗性子进程可以理论上同时伪造本地快照和回执，所以这两者只作为一致性证据，不能宣称为跨权限防篡改边界。项目命令或依赖不可信时，不得在本地执行；应由用户在隔离环境或 CI 中运行并把结果作为外部证据带回。`delivering` 不允许执行任何项目命令，只保留只读复核、治理状态更新和经过逐次用户确认的精确 SVN 提交。

“只读命令”按 shell 实际语义而不是命令名称判断。普通文件读取与搜索统一走结构化 Read/Glob/Grep；Bash 只保留无参数 `pwd`、参数模式受限的 WALI 命令和严格 SVN 只读 schema。策略在 shell 展开前拒绝未引用 brace/glob、反斜线、变量/命令替换、管道与重定向，也拒绝外部配置和外部 diff；`svn diff` 必须显式使用 `--internal-diff`。

### 6.5 `spec.md` 是固定的编译结果，不是输入文档副本

每个开发 Goal 都有一份 `docs/wali-0x3/spec.md`。它解决的是“实现和测试到底依据哪一份规范”的问题：用户提供的接口文档、需求和规格仍保留为来源证据，但 Coordinator 必须把它们与访谈结论、代码事实和明确约束归一化为同一份 Spec。开发者、Reviewer 和 Tester 不在多份原始资料之间自行选择解释。

Goal 与 Spec 的职责边界是：

| 文档 | 负责回答 | 不负责 |
| --- | --- | --- |
| `goal.md` | 为什么做、范围是什么、当前 phase/权限是什么、AC 状态和证据如何 | 不承载完整接口、数据和错误规范 |
| `spec.md` | 系统必须如何表现、Requirement 来源、边界/错误/质量约束、每个 AC 如何判定 | 不维护独立 phase、确认状态或任务进度 |

Spec 使用 `source_mode` 记录形成方式：

- `discovery`：输入模糊，通过开放式访谈形成。
- `pressure_test`：用户已有资料，通过缺失、歧义、冲突、代码一致性和可测试性压力测试形成。
- `hybrid`：已有明确条款，但仍需访谈补齐高影响空白。

Spec 中每项规范需求使用稳定 `R-XXX` ID，并至少关联一个 AC；每个 AC 必须由至少一个 Requirement 支撑，且在 Spec 中恰好有一条判定规则和验证方法。`spec_id` 必须始终等于 `SPEC-<当前 Goal ID>`，Spec 的 `goal_id` 在所有 phase（包括 `pending/clarifying`）都必须与 Goal 一致，重复 frontmatter 键直接拒绝。Goal 不为 Spec 建立第二个确认状态：用户一次确认 Goal + Spec 联合包，`goal_definition_digest` 同时封存 Goal 稳定部分和完整规范化 Spec。确认后的 Spec 只读；任何实质修改必须先回到 `clarifying`。

### 6.6 退出机制区分成功、暂停与非成功终止

“停止当前会话”“工作被阻断”和“Goal 已退出”是三个不同概念：

| 情形 | 状态 | 含义 |
| --- | --- | --- |
| 会话暂时结束 | `stop_intent: handoff` | 可恢复暂停，Goal 仍活动 |
| 外部条件暂不可用 | `phase: blocked` | 可恢复阻断，记录原因后等待 |
| 全部完成 | `exit_outcome: completed` + `closed/delivering` | 成功退出，必须有技术证据和用户验收 |
| 用户取消 | `status/exit_outcome: cancelled` + `terminated` | 非成功退出，不声称完成 |
| 被新 Goal 替代 | `status/exit_outcome: superseded` + `terminated` | 记录不同的 `superseded_by` Goal ID |
| 安全或策略不允许继续 | `status/exit_outcome: aborted` + `terminated` | 保留安全/策略证据，不冒险继续 |

所有非成功退出都必须记录 `exit_reason`、`exit_evidence` 和 `exit_change_disposition`，且 `status` 必须与 `exit_outcome` 精确一致。变更处置只能是保留、交接或用户明确授权的清理；默认保留，且退出状态本身从不授权删除、回退或覆盖用户资产。从任何非终态进入 `terminated` 必须由 PreToolUse 再次请求用户当场核对。Stop 对 `terminated` 不再要求任务和 AC 完成，但仍要求契约合法、五份固定状态存在且 handoff 摘要最新，从而允许诚实退出而不鼓励伪造完成证据。

若退出发生在实施中，`preserve`/`handoff` 不是一句自由文本：Agent 必须先用 `carry` 冻结当前活动任务范围内的合法差异，使 handoff 摘要能够绑定准确内容；未冻结或范围外差异会在进入 `terminated` 的 PreToolUse 和 Stop 审计中被拒绝。若用户选择清理，必须先在原阶段按具体授权完成可审计处置，不能进入终态后再利用退出状态取得删除权限。

`closed`、`terminated` 和具备有效提交回执的 `delivering` 冻结的是当前 Goal，而不是整个系统。开始下一项工作时，终态只开放一个受确认的重置事务：使用不同 Goal ID 重置到最小 `clarifying` 契约；若退出类型是 `superseded`，新 Goal ID 必须等于 `superseded_by`。重置必须将 `carry_epoch` 归零，清空旧 `carried_history`、`carried_changes`、能力与提交授权，并把当前全部非治理 SVN 差异重新指纹化为 `preexisting_changes`，默认作为新 Goal 不可修改的用户资产。身份不一致期间只允许把固定 Spec 更新为新 Goal；身份一致后还必须刷新 handoff，Stop 才会放行。这样旧 Goal 的 carry 不会被重新分类为新 Goal 的实现授权。

`delivering` 的返回路径按真实 SVN 状态区分：授权路径仍有差异时，说明尚未提交，可经用户确认清除提交清单和证据后让原 Goal 返回 `clarifying`；授权路径已清洁但回执缺失或无效时，无法证明是否已经提交，只能查明后进入 `terminated`；精确提交和有效回执都成立后，`delivering` 即冻结终态，不得用原 Goal ID 返回澄清。

## 7. `/goal` 与目标契约

`/goal` 用于让当前 Claude Code 会话持续工作，直到一个可验证条件成立。它适合实现设计、完成迁移、清理问题列表和持续修复测试等具有明确终点的任务。

`goal.md`、`spec.md` 与 `/goal` 的关系是：

```text
goal.md
保存完整、持久的项目意图、阶段和验收状态。

spec.md
保存 Requirement 与规范性开发/测试判定契约。

/goal
把当前阶段可执行、可验证的完成条件交给 Claude Code 持续推进。
```

### 7.1 有效 Goal 的三个组成部分

一个有效的 `/goal` 条件应包含：

```text
可测量的最终状态
例如测试通过、构建退出码为 0、阻断问题为空。

明确的检查方式
例如运行 npm test、读取问题清单、检查本地 `svn diff --internal-diff` 或约定修订范围。

执行约束
例如不得删除测试、不得修改范围外文件、不得降低检查标准。
```

还应包含执行边界，例如最多运行多少回合或在什么情况下停止并报告阻断。

### 7.2 Goal 评估器可见性

`/goal` 的评估器根据当前对话中已经展示的内容判断是否完成。它不会自行读取文件，也不会自行运行命令。

因此，执行 Agent 必须在对话中展示关键证据，包括：

- 实际运行的命令。
- 命令退出结果。
- 测试和构建摘要。
- 目标验收条件与证据的对应关系。
- 未完成事项和阻断原因。

只把测试结果写入仓库文件，而不在当前对话中展示，可能导致 Goal 评估器无法判断。

### 7.3 推荐 Goal 模板

```text
/goal 持续工作，直到满足以下条件：

1. docs/wali-0x3/goal.md 中所有当前阶段的自动验收条件均已满足。
2. docs/wali-0x3/spec.md 中 Requirement → AC 关系和判定规则完整。
3. docs/wali-0x3/todo.md 中所有必要任务已经完成。
4. docs/wali-0x3/issues.md 中不存在未关闭的阻断问题。
5. 只有成功条件全部满足时以 completed 退出；handoff/blocked 仅暂停，取消/替代/安全中止进入 terminated。
4. 执行项目规定的构建、测试和静态检查，并在当前对话中展示命令与结果。
5. 检查本地 SVN 差异；若本轮包含已提交修改，还要检查从基准修订到目标修订的约定范围，确认未修改目标范围之外的内容。
6. 在当前对话中逐项列出验收条件及对应证据。

不得删除、跳过或弱化测试以获得通过结果；不得擅自扩大目标范围。
如达到约定回合上限仍未完成，停止执行并说明剩余任务、已知风险和阻断原因。
```

复杂目标可以拆成多个阶段 Goal，不要求一个 `/goal` 覆盖整个项目生命周期。

## 8. Loop 的三种含义

`wali-0x3` 必须区分三种不同的循环。

### 8.1 Claude Code Agentic Loop

这是 Claude Code 自身的执行循环：

```text
读取上下文
→ 选择工具和动作
→ 修改或执行
→ 观察结果
→ 根据反馈继续调整
```

这一层由 Claude Code 提供，`wali-0x3` 只需要提供目标、上下文、工具边界和验证方式。

### 8.2 WALI 的 Loop

这是项目级开发闭环：

```text
开发
→ 审查
→ 测试
→ 记录问题
→ 修复
→ 回归
→ 再次检查目标
```

WALI 的 Loop 是方法和治理概念，不等同于 Claude Code 的 `/loop` 命令。

### 8.3 Claude Code `/loop`

`/loop` 是会话内的定时重复能力，适合：

- 等待持续集成结果。
- 轮询部署状态。
- 检查新的代码审查或任务评论。
- 查看长时间构建是否结束。
- 定期执行维护检查。

它不应作为普通开发工作的主要驱动方式。

推荐关系：

```text
持续开发直到满足条件
→ /goal

开发过程中的工具执行和反馈调整
→ Agentic Loop

等待外部状态或按时间重复检查
→ /loop

跨会话、长期可靠的定时运行
→ Routine、Desktop Task 或 CI
```

同一阶段不应同时让 `/goal` 和 `/loop` 作为两个独立调度器反复驱动编码。通常先使用 `/goal` 完成本地开发；需要等待外部结果时暂停目标处理并进入 `/loop`；外部条件变化后再继续目标。

## 9. 角色体系

当前保留以下角色：

```text
Coordinator
负责目标澄清、项目资料核对、通用 Rule/Ref 与能力选择、执行方式选择、任务拆解、调度、状态协调和完成判断。

Architect（可选）
负责高影响技术决策的只读分析、方案比较、边界识别和验证建议。

Developer
负责分析、实现、自检和问题修复；可根据任务实例化为前端或后端角色。

Reviewer
负责代码、实现方式、影响范围、工程质量和验收遗漏审查。

Tester
负责测试设计、问题复现、自动化测试和回归验证。
```

角色不是固定岗位编制。Coordinator 根据任务需要决定启用哪些角色。

### 9.1 Coordinator

Coordinator 首先负责选择执行方式，然后才是拆解任务。它不得默认创建完整团队。

主要职责：

- 建立和维护目标契约。
- 核对项目 `docs` 来源，识别适用的通用 Rules/Refs，把路径、版本和采用结论纳入 Spec。
- 判断主会话、Subagent、Agent Teams 或顺序执行。
- 拆解任务、关联必要 Skill 并管理依赖。
- 控制修改冲突和任务所有权。
- 检查任务、问题和证据是否一致。
- 判断自动验收条件是否满足。
- 将长期价值结论提交为全局记忆候选。

Coordinator 不代替 Developer 编写所有代码，也不代替用户做最终业务验收。

### 9.2 Architect（可选）

Architect 不是常驻岗位，也不拥有 Goal 或 Spec。仅在跨模块边界、接口或数据迁移、重要质量属性、高代价技术分歧，或规格与现有结构冲突时由 Coordinator 按需启用。

它以只读方式：

- 分开事实、假设和仍需用户决定的问题。
- 描述当前技术作用力与边界。
- 比较少量可行方案及维持现状的代价。
- 评估接口、数据、错误语义、安全、性能、可靠性、兼容性和演进成本。
- 提出验证、迁移、回滚及对 Requirement、AC、Task 的影响建议。

Architect 不直接修改 Goal、Spec、实现或测试，不创建 ADR、设计图等额外产物，也不成为实现的唯一 Reviewer。是否采纳其建议由 Coordinator 整合；会改变用户结果、范围或规范的决定仍需用户确认。

### 9.3 Developer

Developer 对具体实现增量负责：

- 读取目标、任务、Spec 引用的项目资料，以及 `refs/INDEX.md` 为 Developer 路由的通用 Rules/Refs。
- 认领一个明确任务。
- 分析影响范围并实施修改。
- 运行必要自检。
- 记录修改内容、执行命令和已知风险。
- 将任务交给独立审查或测试。

Developer 不得仅凭代码已修改就将任务标记为最终完成。

### 9.4 Reviewer

Reviewer 尽量使用独立上下文，避免沿用实现者的假设。

它重点检查：

- 是否真正满足对应验收条件。
- 修改是否超出范围。
- 是否存在边界、并发、安全和兼容性问题。
- 是否通过删除测试、弱化校验等方式获得表面成功。
- 是否遗漏必要测试和错误处理。
- 是否满足适用的通用 Rule，项目来源资料是否被 Spec 正确采用，并按 `refs/INDEX.md` 使用 Reviewer 适用的代码检查基线。

发现问题时写入 `issues.md`，默认不直接修改 Developer 的代码。

### 9.5 Tester

Tester 负责从结果和失败场景验证实现：

- 设计并执行必要测试。
- 复现 Reviewer 或用户发现的问题。
- 检查修复是否产生回归。
- 保存测试命令、结果和失败证据。
- 对修复问题进行独立关闭验证。

### 9.6 模型与思考深度

模型决定能力、速度和成本的基础区间，`effort` 决定支持该机制的模型在一次任务中投入多少自适应推理。WALI 使用模型家族别名，不固定具体版本号，使 `opus`、`sonnet` 随当前账号和组织允许范围解析到相应家族的最新可用版本。

默认映射为：

| 角色 | 模型 | effort | 原因 |
| --- | --- | --- | --- |
| Coordinator | `opus` | `high` | 需要长程规划、冲突判断和多 Agent 编排；`high` 为团队提供可靠基线而不默认放大全部 teammate 成本 |
| Architect | `opus` | `xhigh` | 只在跨边界、高影响、难逆转决策中启用，值得投入更深方案比较 |
| Reviewer | `opus` | `high` | 需要独立发现实现者遗漏的高代价缺陷和规范偏差 |
| Developer | `sonnet` | `high` | 复杂编码能力、指令遵循、速度和成本之间的日常平衡 |
| Tester | `sonnet` | `high` | 需要反例与边界推演，但最终结论仍由可重复实验和证据约束 |

项目 `settings.json` 还将默认主会话设为 `opus/high`，因为主会话通常直接承担 Coordinator，却不一定通过 `coordinator` Agent 定义启动。当前角色不默认使用 Haiku，因为它们都对正确性或高影响判断负责；未来若增加只做短小检索、格式化或机械分类的辅助 Agent，可考虑 `haiku/low` 或 `haiku/medium`。`max` 不写入任何固定角色：它可能提高最困难任务的表现，也可能出现收益递减和过度思考，只能在 `xhigh` 仍不足、失败代价极高且用户接受额外延迟和成本时按单次任务启用。

运行方式会改变配置是否生效：

- 普通 Subagent 使用自身 frontmatter 的 `model` 和 `effort`。
- Agent Teams teammate 使用角色定义中的 `model`，但 `effort` 继承 lead，而不是各自 frontmatter。
- 因此，只有 Architect 需要 `xhigh` 时应把它作为独立 Subagent；只有整个团队都值得升档时才提高 lead effort。
- 环境变量、组织 effort 上限或调用时模型参数可能覆盖 frontmatter；实际运行值以 Claude Code 会话标题或 `/model`、`/effort` 显示为准。

思考深度不替代验证，也不是权限。提高 effort 不能扩大 Goal、phase、effect、Skill、文件范围或 SVN 权限，更不能让 Agent 用更长推理自证完成。

## 10. 任务分派与责任认领

目标明确后，Coordinator 将工作拆解为可以执行和验证的任务。

每项任务至少包含：

```text
任务编号
关联目标或验收条件
任务内容
负责人
状态
依赖任务
允许修改范围
所用 Skill（可选）
任务验收条件
执行结果
相关证据
```

任务应尽量：

- 有明确输入和输出。
- 能够独立判断是否完成。
- 修改范围相对集中。
- 与其他任务的依赖关系清楚。
- 避免多个 Agent 无计划地修改相同文件。
- 控制在单个会话可以稳定推进的大小。

当前任务状态：

```text
pending
working
review
blocked
done
```

代码完成后进入 `review`，只有对应验证通过后才进入 `done`。

### 10.1 Graph Engineering：把隐含关系变成可检查工作图

这里引入的是 Graph Engineering：用明确节点、稳定 ID、类型化边和图约束管理研发状态，而不是 GraphRAG。WALI 不引入图数据库或独立工作流服务。五个 WALI Markdown 状态文件仍是唯一真实来源；项目脚本只在内存中把稳定 ID 和关系字段解析为工作图。

当前节点包括：

```text
Goal        G-XXX
需求        R-XXX
验收条件    AC-XXX
任务        T-XXX
问题        I-XXX
Agent       coordinator / developer / reviewer / tester / user
Skill       当前 Task 明确关联的项目能力
证据        从对应节点的证据字段派生
```

当前关系包括：

```text
Goal 包含 Requirement
Requirement 定义 AC
Task 实现 AC
Task 阻塞 Task
Issue 影响 Task 或 AC
Agent 负责或验证 Task
Skill 为 Task 提供方法
Task、AC、Issue 连接其证据
```

关系直接保存在现有表格中：Spec Requirement 的 `关联 AC`、Task 的 `关联 AC`、`依赖`、`负责人`、`独立验证者`、`所用 Skill`、Issue 的 `关联任务` 和证据字段都是图的边，不再另建 `graph.md`。核心追踪链固定为 `Requirement → AC → Task → Evidence`；Issue、依赖、责任和方法边提供风险与协作上下文。

### 10.2 工作图检查

`.claude/hooks/wali_graph.py` 从 Markdown 派生图，并检查：

- 节点 ID 是否重复。
- Requirement 是否关联现有 AC，每个 AC 是否有上游 Requirement。
- 每个 AC 是否在 Spec 中恰好有一条非空判定规则和验证方法。
- 任务或问题是否引用不存在的节点。
- 每项任务是否关联验收条件。
- Task 声明的 Skill 是否使用合法标识并已列入 Goal 的 `allowed_capabilities`。
- 每项 automatic 验收条件是否有任务覆盖。
- `verified` AC 是否已有非占位证据；`done` Task 是否已有执行证据和不同于负责人的 Reviewer、Tester 或用户验证。
- `verified` automatic AC 是否至少关联一个已完成的 required Task，使 Requirement → AC → Task → Evidence 主链真正闭合。
- 任务依赖是否存在环。
- 同时处于 `working` 的任务是否拥有重叠修改范围。
- 阻断问题是否影响候选任务。
- 活动任务是否处于与 phase 对应的 `working`/`review` 状态，依赖是否完成，是否被 blocker 阻断。
- 修改范围是否使用根级通配，或触及 `.claude/**`、存档形态 `claude/**`、`CLAUDE.md` 控制面。

工作图检查接入 Stop Hook，作为状态一致性检查的一部分。它不代替构建、测试、审查或用户验收。

### 10.3 当前可执行前沿

当前可执行前沿由 `pending` 任务组成，并同时满足：

- 所有依赖任务均为 `done`。
- 没有关联的未关闭 `blocker`。
- 任务仍关联有效验收条件。

Coordinator 只从当前前沿选择任务。不得跳过依赖，也不得只因为某个 Agent 空闲就分派不可执行任务。

### 10.4 安全并行候选

位于当前前沿的两个任务，只有允许修改范围可以确定为互斥时，才是安全并行候选。范围为空、含义不明或存在包含关系时直接判为无效或冲突。当前策略一次只授权一个 `active_task`；真正并行写入应使用各自独立的 SVN 工作副本和阶段契约，不能把候选列表当作多任务共同写入授权。

独立 SVN 工作副本只能隔离本地修改，不能把重叠任务变成安全并行任务。

### 10.5 工作图变更

Coordinator 负责接受或拒绝节点和关系变更。Developer、Reviewer 和 Tester 可以提出新增任务、依赖或问题关系，但不得静默改写 Goal、删除验收条件或改变任务边界。

每轮在 `handoff.md` 记录本轮新增、删除或改变的节点与关系，使下一会话能够理解工作图为何变化。

### 10.6 按需查看

工作图不持久化为新的仓库文件。需要检查或查看时运行：

```text
python3 .claude/hooks/wali_graph.py --project-root . check
python3 .claude/hooks/wali_graph.py --project-root . frontier
python3 .claude/hooks/wali_graph.py --project-root . parallel
python3 .claude/hooks/wali_graph.py --project-root . mermaid
```

`mermaid` 只把当前派生图输出到标准输出；是否保存或发布图形由用户决定。

## 11. 问题闭环

Reviewer、Tester 和用户发现的问题统一进入 `issues.md`。

每个问题至少包含：

```text
问题编号
问题来源
关联任务
关联验收条件
问题描述
复现步骤或证据
严重程度
修复负责人
状态
验证结果
```

当前问题状态：

```text
open
fixing
verify
closed
```

```text
发现问题
   ↓
记录问题和证据
   ↓
Coordinator 确认影响和负责人
   ↓
Developer 修复
   ↓
原 Reviewer 或 Tester 重新验证
   ↓
关闭问题
```

阻断问题未关闭时，对应任务和目标不能进入完成状态。

## 12. Inspect 与完成证据检查

Inspect 采用三层验证。

### 12.1 自动检查

适合通过命令、脚本或 Hook 判断：

- 构建是否成功。
- 测试是否通过。
- Lint 和类型检查是否通过。
- 是否修改禁止文件。
- 是否仍有阻断问题。
- 是否存在未处理的格式或生成物问题。

确定性规则应优先使用 Hook 或项目脚本，而不是依赖模型记得执行。当前实现分三层：

- `wali_policy.py hook`：PreToolUse 读取真实工具输入，拒绝超出当前 effect、写入范围或副作用开关的动作。
- `wali_policy.py post-hook`：PostToolUse 在 Bash 或文件工具执行后复查契约和 SVN 差异，使黑盒能力生成的未授权产物可立即暴露。
- `wali_supervision.py hook`：`TaskCompleted` 与 `TeammateIdle` 检查 Agent 运行事件是否与活动 WALI Task、工作图和证据一致；`StopFailure` 只记录失败和恢复要求。
- `wali_stop.py`：Stop Hook 在会话尝试停止时复查阶段契约、SVN 差异、工作图、独立验证和完成证据。
- `wali_svn.py`：集中验证工作副本根、读取不受个人 Ignore 配置影响的完整状态，并分类需审计变化与项目声明的本地产物。

### 12.2 语义检查

适合由 Reviewer、Tester 和 `/goal` 评估器判断：

- 实现是否真正满足业务目标。
- 是否遗漏验收条件。
- 修改方式是否合理。
- 是否存在潜在回归。
- 证据是否足够支持完成结论。

### 12.3 人工验收

用户负责确认：

- 实际业务流程是否可用。
- 交互和结果是否符合预期。
- 风险和取舍是否可以接受。
- 是否允许本轮目标正式关闭。

最终关系：

```text
项目命令与 Hooks
负责硬性通过条件

Reviewer 与 Tester
负责独立检查和反向验证

/goal
负责判断当前阶段是否整体完成

用户
负责最终业务验收
```

## 13. 长时间运行与恢复协议

仅依靠上下文压缩不能保证长期任务可靠推进。`wali-0x3` 通过结构化文件和 SVN 工作副本状态完成跨会话交接。

### 13.1 初始化

第一次进入项目时，Coordinator 先建立 `clarifying` 契约，记录 SVN 基线和调用前已存在的本地修改；随后按输入情况执行开放式访谈、规格压力测试或两者组合，完成 Goal + Spec 联合确认包。只在用户明确确认并生成同时绑定两份契约的摘要后，才进入 `planning`、建立完整但可逐步执行的任务列表、运行工作图检查并选定第一个可验证任务。

### 13.2 增量推进

后续每个会话只承诺完成有限的、可验证的任务增量，不尝试一次完成整个大型目标。

### 13.3 handoff.md

新增 `docs/wali-0x3/handoff.md`，专门保存可恢复交接状态：

```text
最近完成了什么
当前正在处理什么
当前 phase、active task、Goal + Spec 联合确认状态、退出状态和下一个转段条件
SVN 工作副本 URL、工作副本修订信息和工作副本状态
有哪些本地修改
最近一次构建和测试结果
已知问题和风险
下一项建议任务
澄清阶段的当前轮次、最后纳入回答和下一轮问题
阶段继承差异指纹、停止意图、退出原因/证据/变更处置和精确提交清单（若有）
```

`handoff.md` 不是进度历史。它始终覆盖为最新快照，只保存下一会话恢复工作所需的最小信息。更新正文后运行 `wali_policy.py handoff-digest`，把摘要写入 `state_digest`；摘要绑定完整 Goal、完整规范化 Spec、任务与问题文件、交接正文、carry 代次及非治理文件的 SVN 工作副本差异。计算时只排除 `state_digest` 自身和 Goal 的 `stop_intent`，避免循环并允许最后切换停止意图。未完成工作需要结束会话时，先刷新摘要，再设置 `stop_intent: handoff`。Stop Hook 只有在镜像字段、真实更新时间和状态摘要都与当前状态一致时才允许可恢复暂停。

### 13.4 Agent 监督与异常恢复

Agent 的一次运行和 WALI Task 是两套状态机：

```text
WALI Task：pending → working → review → done
运行状态：spawned → running → waiting / idle / completed
                         └→ needs_attention / failed
```

`completed` 只表示 Agent 已返回控制权，不能把 Task 自动设为 `done`；`failed` 也不能自动把 Task 改成 `blocked` 或创建替代实现。为了把 Claude Code 的运行事件接入 WALI：

- Agent Teams 的共享任务标题包含且只能包含一个稳定 Task ID，例如 `[T-001] 实现支付校验`。
- `TaskCompleted` 在 `implementing`/`inspecting` 中只接受当前 `active_task`。Task 仍为 `working`、缺少证据、工作图无效或事件引用其他 Task 时，Hook 以退出码 2 返回可操作反馈。
- `TeammateIdle` 只约束当前 Task 的实际负责人。负责人仍持有 `working` Task 时不能静默 idle；不相关的 Architect、Reviewer 或顾问不受该 Task 阻止。
- `StopFailure` 按事件语义只能观察，不能阻止失败。它记录错误类型、transcript 路径、最后消息摘要和当前 Goal/phase/Task，不声称已经阻止异常退出。只有事件能够绑定当前 `active_task` 时才设置强制恢复标记；没有活动任务的 Coordinator 或顾问失败保留为诊断事件，不虚构 Task 状态。

运行事件保存在 SVN 工作副本本地元数据 `.svn/wali-policy/supervision.json`，通过持久的 `supervision.lock` 文件、操作系统建议锁和原子替换避免并发 Hook 写坏。POSIX 使用 `fcntl.flock`，Windows 使用 `msvcrt.locking`；PID、随机令牌和获得时间只是诊断元数据，不作为锁所有权依据。互斥状态由内核持有，进程正常结束或异常退出都会自动释放，后续 Hook 复用同一文件；存活进程仍持锁时不能强占。平台没有支持的文件锁后端时直接失败，不降级为无锁写入。该文件不是第六份项目状态，不进入 SVN；项目不创建 `progress.md`、运行日志或另一份任务表来保存同一事实。

Coordinator 通过 Agent 面板或 `/tasks`、`wali_supervision.py status`、transcript、WALI Task 和 SVN 差异交叉判断状态。没有新输出不等于卡死：长命令、等待用户输入和等待权限必须先分类；怀疑停滞时只做一次明确状态探测，要求返回当前步骤、最后成功动作、阻断、现有差异和下一步。

恢复按以下顺序进行：

1. 等待用户输入或权限时交给用户，不创建替代 Agent，也不把 Agent 消息视为用户授权。
2. 会话仍可用但方向偏离时纠正原 Agent，优先复用原 Agent ID 和 transcript。
3. `needs_attention` 时要求原 Agent 带证据完成 `working → review`，或记录真实阻断。
4. `failed` 时保存事件和 transcript，先审计 SVN 差异并冻结 Task 与路径所有权；优先恢复原 Agent，无法恢复时才将同一 Task ID、Spec、范围、现有差异、失败原因和下一验证步骤交给替代 Agent。
5. 恢复或替代后的 Agent 只有带证据进入 `review` 并完成有效 `TaskCompleted` 后，本地恢复要求才算解决。

恢复过程不自动回退、删除、覆盖或提交修改。若与活动任务绑定的恢复在会话交接前仍未完成，`handoff.md` 必须记录 `supervision_event`、`recovery_action`（`resume`、`replace`、`wait_user` 或 `terminate_goal`）和非占位的 `recovery_evidence`；Stop Hook 会拒绝缺失这些字段的恢复交接。

### 13.5 会话开始

每次开始或恢复时：

```text
确认当前目录、SVN 工作副本 URL 和工作副本修订信息
→ 读取 goal、spec、todo、issues、handoff
→ 查看 svn status 和近期 svn log
→ 网络与权限可用时用 svn status -u 检查远端过期项
→ 读取 wali_supervision.py status 并处理未恢复失败
→ 核对任务状态与真实代码
→ 运行必要的基础冒烟检查
→ 选择最高优先级的可执行任务
```

### 13.6 会话结束

每次结束前：

```text
运行阶段契约和当前允许的必要验证
→ 核对 Agent 监督状态；活动任务的未恢复失败写入交接事件、动作和证据
→ 只更新当前 phase 授权的状态
→ 更新 handoff.md
→ 运行 handoff-digest 并写入 state_digest
→ 保持代码处于可继续工作的状态
→ 运行 SVN 差异审计
→ 实现转检查前用 carry 冻结合法差异指纹
→ 只在此前验证已完成、进入 delivering 且已记录精确 leaf-path 清单时，执行只读复核并请求用户当场确认严格 SVN 提交
→ 在对话中展示交接摘要
```

若本轮是非成功退出，还要先记录 `cancelled/superseded/aborted` 类型、原因、证据和未提交变更处置，请用户当场确认进入 `terminated`，再刷新交接；不得借退出自动清理工作副本。若只是暂时结束会话，使用 `handoff`，不要进入终态。

受控 `svn add/delete/move/copy`、`svn update -- <exact-path>...` 和 `svn resolve --accept working -- <exact-path>...` 只在 `implementing` 中对状态为 `working` 的活动任务开放，目标必须是任务范围内的精确 leaf path。若交付前出现过期或冲突，必须回到合法活动任务，精确同步、显式编辑解决、重新验证并 `carry`。

项目可由人提交 `svn:ignore`，或在 SVN 1.8+ 的工作副本根提交 `svn:global-ignores`。WALI 只读消费原生结果，不开放自动 `propset`；个人客户端 Ignore 不参与项目判定。属性本身发生变化时仍作为版本化差异审计。

SVN 提交授权不包含 update、冲突解决、externals、部署或发布。只允许 `svn commit (-m|--message) <literal> -- <exact-leaf-path>...`，`allow_external_writes` 在 `delivering` 仍为 false，且此阶段不允许执行项目命令。提交前必须用 `svn info --show-item wc-root` 证明项目目录就是可写工作副本根，并成功保存动作前快照；普通子目录或快照失败都会在命令执行前拒绝。`svn_commit_evidence` 仅保存可追溯的历史依据，不是 Agent 可自行签发的授权令牌；每次匹配的提交仍由 PreToolUse 返回 `ask`，用户必须当场核对命令和精确路径。PreToolUse 同时要求全部目标在提交前确有差异、指纹等于当前 carry 代且 SVN 元数据证明其为 leaf file，并把逐路径证据写入动作快照。PostToolUse 只接受成功工具响应中的唯一提交修订号，并要求提交后授权路径清洁、所有现存目标的 `last-changed-revision` 都等于该修订号；随后写入绑定 Goal、carry 代次、授权、提交前证据、提交后指纹和统一修订号的本地回执。删除目标与同一原子提交修订号绑定，不使用无来源的删除标记。Stop 再检查授权路径无剩余差异、回执未过期且与当前工作副本一致；空提交不能生成回执。提交型流程以 `delivering` 为终态，避免提交后再产生一个未提交的 `closed` 状态差异；无需提交时直接进入 `closed`。

提交前撤销交付时必须清空提交路径与证据并经用户确认；路径已清洁但回执无效时不得复活原 Goal；有效回执成立后 `delivering` 冻结。

记录与真实状态冲突时，以代码、SVN 工作副本状态和最新验证结果为准，并修正状态文件。

## 14. 项目目录

当前设计存档工作区本身使用 Git，仅用于维护这套设计；这里的 Git 状态不代表 Agent 的目标运行环境。存档中保留可见目录名 `claude/`，不改回隐藏目录。使用者部署到只支持 SVN 的目标项目时再自行将它改名为 `.claude/`；运行期策略只按 SVN 工作副本、差异与提交语义工作。部署后结构如下：

```text
project/
├── CLAUDE.md
├── wali-0x3-brand.md
├── .claude/
│   ├── agents/
│   │   ├── coordinator.md
│   │   ├── architect.md
│   │   ├── developer.md
│   │   ├── reviewer.md
│   │   └── tester.md
│   ├── rules/
│   │   ├── engineering.md
│   │   └── testing.md
│   ├── refs/
│   │   ├── INDEX.md
│   │   ├── operations.md
│   │   ├── compatibility.md
│   │   ├── templates/
│   │   │   └── INDEX.md
│   │   └── compliance/
│   │       └── INDEX.md
│   ├── hooks/
│   │   ├── wali_policy.py
│   │   ├── wali_graph.py
│   │   ├── wali_stop.py
│   │   ├── wali_supervision.py
│   │   ├── wali_svn.py
│   │   ├── test_wali_policy.py
│   │   ├── test_wali_graph.py
│   │   ├── test_wali_stop.py
│   │   ├── test_wali_supervision.py
│   │   └── test_wali_svn.py
│   ├── skills/
│   │   ├── wali-start/
│   │   ├── wali-resume/
│   │   ├── wali-inspect/
│   │   └── wali-handoff/
│   └── settings.json
└── docs/
    └── wali-0x3/
        ├── goal.md
        ├── spec.md
        ├── todo.md
        ├── issues.md
        └── handoff.md
```

各部分职责：

```text
CLAUDE.md
所有会话都需要知道的项目入口和不可违反的核心事实。

.claude/agents/
各角色的独立定位、职责、工具和工作边界。

.claude/rules/
按路径加载的编码和测试硬约束。所有会话都需要的少量协作不变量直接保留在 `CLAUDE.md`，不再用无条件 Rule 重复。

.claude/refs/
跨项目稳定、低频变化的静态参考，包括 WALI 运行说明、Developer 使用的开发模板，以及 Developer/Reviewer 使用的企业内部代码检查基线。通过 `INDEX.md` 按角色与场景选择性读取，不保存具体项目知识或运行状态。

.claude/hooks/
阶段契约与工具副作用约束、共享 SVN 边界、基线与差异审计、工作图派生和停止状态检查，以及对应回归测试。

.claude/skills/
只在特定任务中需要的知识和多步骤流程。

.claude/settings.json
项目级 Hooks 和 Claude Code 配置。

Goal、Spec、任务、问题和交接文件
保存 wali-0x3 的持久意图、规范、执行与恢复状态。

项目 docs 中的用户资料
保存当前项目的需求、规格、接口、模块、项目特有模板、依赖和代码检查来源；Spec 记录采用结论。项目资料不复制到共享 Ref，项目对通用 Ref 的例外只写入 Spec。
```

当前不单独增加证据目录。关键证据先记录在任务、问题和 `handoff.md` 中；证据规模明显增长后，再考虑 `evidence/`。

## 15. CLAUDE.md 的边界

`CLAUDE.md` 只保留所有会话都必须知道、且用户不希望反复解释的内容，例如：

- 项目基本结构。
- 构建、测试和常用命令。
- 所有任务必须遵守的约束。
- `wali-0x3` 状态文件位置。
- Agent 和 Rules 的位置。
- 不得绕过验证直接宣布完成。

入口文件应控制在约 80–120 行；这只是本项目的维护预算，不是 Claude Code 的格式要求。拆成 `@import` 或没有 `paths` 的 Rules 仍会常驻上下文，不能视为缩减。详细操作放入按需 Ref，复杂流程放入 Skill。

以下内容不应堆入 `CLAUDE.md`：

- 每个角色的完整职责。
- 只适用于某类文件的编码规范。
- 复杂的多步骤工作流。
- 当前任务和临时问题。
- 大量可以按需加载的领域知识。

放置原则：

```text
每个会话都要知道
→ CLAUDE.md

只适用于特定目录或文件
→ .claude/rules/

按角色与场景查阅的跨项目稳定说明、模板和检查基线
→ .claude/refs/

当前项目的详细输入与来源资料
→ 项目 docs/，并由 spec.md 归一化

特定任务才使用的流程和知识
→ .claude/skills/

需要隔离上下文和职责的工作
→ .claude/agents/
```

## 16. 端到端工作流程

### 16.1 Work：接收并建立目标

用户提出开发、修复或调整需求。

Coordinator 将输入分为模糊需求、已有资料或对现有 Goal 的增量变更。模糊输入采用开放式访谈，已有资料采用规格压力测试，必要时混合；结合真实代码逐轮提取事实、识别缺口与冲突，最终编译 `spec.md` 并生成 Goal + Spec 联合确认包。未获得用户明确确认时不进入 Assign。

### 16.2 Assign：选择执行方式并拆解任务

用户联合确认 Goal + Spec 后，Coordinator 进入 `planning`，先判断主会话、Subagent、Agent Teams 或顺序执行，再沿 Requirement → AC 创建任务、依赖和精确文件所有权。工作图合法且选定前沿任务后，才进入 `implementing`。

### 16.3 Goal：启动当前阶段目标

对于具有明确完成条件的阶段，使用 `/goal` 持续推进，并要求 Agent 在对话中展示验证证据。

### 16.4 Loop：执行增量

Developer 只在 `implementing` 中认领 `active_task`，完成分析、实现和自检。

Claude Code 通过原生 Agentic Loop 根据命令和工具结果持续调整。

### 16.5 Inspect：独立审查和测试

Goal 转入 `inspecting` 后，Reviewer 与 Tester 使用独立上下文检查实现。确定性条件由项目命令或 Hooks 执行。`inspecting` 不直接修实现；发现问题时转回 `implementing`。

发现问题时进入 `issues.md`，由 Developer 修复后重新验证。

### 16.6 External Wait：等待外部状态

需要等待 CI、部署或外部评论时，使用 `/loop` 轮询；具备事件推送条件时优先使用事件通知，减少无意义轮询。

### 16.7 Handoff：保存可恢复状态

每轮结束时只更新当前 phase 允许的状态文件，覆盖更新 `handoff.md`，运行 SVN 差异审计并刷新绑定 Goal + Spec 的 `state_digest`，留下下一会话唯一的恢复入口。未完成时使用同时经过字段镜像和状态摘要校验的 `stop_intent: handoff`，不伪装成 blocked、退出或完成。

### 16.8 Human Acceptance：用户回测

自动验收条件满足后，Goal 进入 `accepting`，由用户执行真实业务回测；需要方向选择时使用独立的 `awaiting_direction`。发现问题则重新进入问题闭环；回测通过后，先对 prospective 终态执行完整工作图、AC、required Task、独立 Evidence、blocker 与 SVN 差异校验，再在无需 SVN 提交时进入 `closed`，或对冻结差异和精确清单另有明确提交授权时进入并终止于 `delivering`。

### 16.9 Memory：经验沉淀

Coordinator 识别经过验证且具有跨项目价值的结论，提交给独立的全局记忆能力判断新增、更新、替代或跳过。

### 16.10 Exit：诚实结束 Goal

成功条件满足时以 `completed` 进入 `closed` 或 `delivering`。用户取消、Goal 被替代或安全/策略不允许继续时，以相同的 `status`/`exit_outcome` 值 `cancelled`、`superseded` 或 `aborted` 进入 `terminated`，并保留原因、证据和变更处置。`handoff`/`blocked` 继续承担暂停语义，不挤进退出状态。

## 17. 当前实现范围

0.11 版已实现：

```text
最小项目目录
目标契约
模糊需求和已有规格的多轮澄清
开放式访谈、规格压力测试与 hybrid 收敛路径
固定 spec.md 与 Goal + Spec 联合确认包
十阶段契约、显式退出机制与受确认重置事务
Goal + Spec 联合摘要与确认后防漂移检查
带递增代次和只追加历史的 carry 指纹与跨阶段继承
活动任务范围内的精确 SVN add/delete/move/copy/update/resolve
可信原生 SVN Ignore 与需审计变化/本地产物分类
工具调用前的 effect/路径/副作用检查
工具调用后与停止前的 SVN 差异审计
不依赖具体 Skill 名称的能力 allowlist、安全 frontmatter、加载期 shell 禁用与通用副作用约束
Agent Skill 的定义—授权—任务关联—动作检查链路
Rules/Refs/Skills 与项目 docs/Spec 的跨项目参考—项目资料分层
执行方式选择
四个核心角色与按需只读 Architect 定义
基于角色的 model/effort 默认映射与 Agent Teams 继承约束
任务认领与状态更新
Markdown 派生工作图
Requirement → AC → Task → Evidence 主追踪链
Skill → Task 方法边与 Goal 能力授权一致性检查
完成节点的证据与独立验证不变量
成功终态写入前的共享完成校验
关系一致性检查
当前可执行前沿与安全并行候选
按需 Mermaid 输出
问题记录、修复和回归
/goal 使用规范
/loop 使用边界
确定性 PreToolUse、PostToolUse 和 Stop Hooks
TeammateIdle、TaskCompleted 与 StopFailure 监督 Hook
Agent 运行态与 WALI Task 状态分离
SVN 本地监督事件记录与异常恢复交接校验
独立 Reviewer 和 Tester
handoff.md 交接协议
handoff 状态摘要与过期检测
显式可恢复暂停意图
completed/cancelled/superseded/aborted 退出结果与变更处置
精确 SVN 提交后的本地交付回执与终态校验
提交完成后的 delivering 冻结与提交前受控返回
新 Goal 全新治理代次和差异重新归属
全阶段 Goal/Spec 身份一致与受限恢复
基于 svn info 的工作副本根发现与子目录拒绝
跨会话恢复
用户回测入口
可选全局记忆候选
```

当前明确不引入：

- 独立管理后台。
- 图数据库、GraphRAG 或持久化图副本。
- LangGraph、ADK Graph 或其他独立运行时编排引擎。
- 数据库和消息总线。
- 复杂工作流 DSL。
- Agent 自动评分。
- 自动抢占和重新选主。
- 大量任务状态。
- 脱离 Goal 阶段契约的独立权限平台。
- 强制所有任务使用 Agent Teams。
- 自动把所有总结写入全局记忆。

## 18. 成功标准

当前体系是否成功，不看 Agent 数量，也不看生成了多少文件，而看能否稳定完成：

```text
用户提出任务
→ 逐轮澄清模糊需求或补全已有规格
→ 编译固定 spec.md
→ 生成 Goal + Spec 联合确认包并获得用户明确确认
→ 选择最简单可行的执行方式
→ 拆解并认领任务
→ 检查工作图并选择当前可执行前沿
→ 使用 /goal 持续推进明确阶段
→ 完成开发增量
→ 运行确定性检查
→ 复查阶段契约和 SVN 差异范围
→ 独立审查和测试
→ 记录并修复问题
→ 根据证据判断完成
→ 更新可恢复交接状态
→ 用户完成回测
→ 以完成、取消、替代或安全中止之一诚实退出，或以 handoff/blocked 暂停
→ 新会话能够继续工作
```

## 19. 后续演进议题

- 如何自动从目标契约生成 `/goal` 条件。
- 审查和测试证据的保留方式。
- 全局记忆候选的触发条件。
- 何时需要从派生工作图升级为运行时 Agent 协作图。
- 跨仓库或分布式 Agent 是否需要 A2A 等互操作协议。
- 用于验证当前体系的真实项目和任务。

## 20. 参考资料

- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [Keep Claude working toward a goal](https://code.claude.com/docs/en/goal)
- [Run prompts on a schedule](https://code.claude.com/docs/en/scheduled-tasks)
- [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- [Orchestrate teams of Claude Code sessions](https://code.claude.com/docs/en/agent-teams)
- [Automate actions with hooks](https://code.claude.com/docs/en/hooks-guide)
- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)
- [How Claude remembers your project](https://code.claude.com/docs/en/memory)
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Google ADK: Graph-based agent workflows](https://adk.dev/graphs/)
- [LangGraph: Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [Testing Agentic Workflows with Structural Coverage Criteria](https://arxiv.org/abs/2605.26521)
