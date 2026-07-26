# wali-0x3

> 让 Claude Agent 的项目开发工作可分派、可检查、可恢复、可验收。

`wali-0x3` 是一套嵌入 Claude Code 项目的开发协作与验证机制。它不替代 Agent 的编码能力，而是在 Agent 外围建立目标契约、责任边界、验证闭环和恢复协议。

这套机制面向一个具体环境：Agent 实际工作的项目只使用 SVN。当前保存设计源文件的仓库使用 Git，两者必须明确区分，不能把归档仓库的版本控制方式带入目标项目。

当前核心设计版本为 `0.4`，仍处于设计与验证阶段。

## 阅读路径

- 第一次了解 wali-0x3：从“为什么需要”读到 WALI 四阶段。
- 评审设计：重点阅读 Goal、阶段副作用契约、Inspect 和持久状态。
- 准备部署：直接阅读版本控制边界、归档目录、快速开始和命令参考。
- 了解真实能力边界：阅读“当前实现与后续工作”，不要把设计目标误认为已实现功能。

## 为什么需要 wali-0x3

Agent 很擅长局部执行：读取代码、修改文件、运行命令、根据结果继续调整。真正困难的往往不是某一次修改，而是如何让一项项目工作从模糊需求稳定走到可信交付。

没有项目级约束时，开发过程容易出现五类问题。

### 目标并不清楚，执行却已经开始

用户通常先描述愿望、问题或大致方向，很难一次写出完整 Goal。即使用户提供了规格文档，其中也可能存在冲突、遗漏、隐含假设和不可验证表述。

如果 Agent 把这些空白自行补成实现决定，后续开发越快，偏离真实目标的成本越高。

### 多 Agent 增加了活动，却没有增加确定性

角色数量不等于交付质量。任务边界、依赖和文件范围不清楚时，并行 Agent 只会制造重复劳动、覆盖修改和责任空白。

### “代码已经修改”被误认为“任务已经完成”

实现者天然沿用自己的假设。没有独立审查、失败场景测试和用户回测时，代码可以看起来合理，却没有证据证明业务目标已经达成。

### 长任务的状态只存在于对话中

会话会结束，上下文会压缩，Agent 会更换。若目标、问题、证据和下一步只存在于聊天记录，下一会话只能依赖猜测恢复工作。

### 能力默认行为越过了项目授权

Skill、Agent 或脚本可能默认生成上下文、计划或进度文件，也可能修改仓库或外部系统。能力可用不代表这些副作用已经获得授权。

wali-0x3 的作用，就是把这些不确定性转成可读、可追踪、可以被检查的项目状态。

## 设计理念

### 先定义完成，再开始执行

“完成某个功能”不是有效 Goal。开始实现前，至少要知道最终结果、范围、非目标、主要约束、验收方式、阻断条件和需要用户确认的事项。

### 默认选择最简单的执行方式

主会话能够稳定完成时，不启动额外角色。只需要独立结论时使用 Subagent；只有边界清楚、并行收益明显且需要持续协作时，才使用 Agent Teams。

### 一次推进一个可验证增量

长任务不追求一次写完。每轮只选择一个能在单个会话内实现、检查并留下清晰状态的增量。

### 实现与完成是两件事

Developer 写完代码，只代表实现阶段结束。构建、测试、审查、问题关闭和用户验收共同决定任务是否真正完成。

### 实现者不能成为唯一检查者

独立 Reviewer 和 Tester 用新的上下文寻找反例，避免实现阶段的假设直接变成完成结论。

### 用户保留最终业务验收权

Agent 可以完成技术检查，但真实业务结果是否可接受，只能由用户确认。

### 能力不等于授权

Skill、Agent、脚本和工具只能在 Goal 与任务声明的副作用范围内工作。未知副作用默认不执行，不通过具体 Skill 名称或文件名黑名单维持安全。

## WALI 工作模型

WALI 代表：

> **Work · Assign · Loop · Inspect**

```text
Work
明确问题、建立 Goal、定义完成
   ↓
Assign
选择执行方式、拆解任务、分配责任
   ↓
Loop
实现、审查、测试、修复、回归
   ↓
Inspect
把验收条件映射到证据并判断完成
   └──────── 未满足时返回 Loop
```

这四个阶段是 README 的主线。状态文件、Agent、Hooks 和工作图都只是帮助这条主线可靠运行的支撑机制。

## Work：从需求到 Goal

Work 阶段不急于生成任务。它先回答两个问题：用户真正想改变什么，以及怎样才算改变成功。

### 渐进式澄清，而不是让用户填写长表单

wali-0x3 借鉴对话式规格收敛的思路，但不依赖任何特定 Skill。Coordinator 每次只提出会实质影响方向的问题，并逐轮缩小未知范围。

澄清按四个层次推进。

1. **结果与背景**：谁在什么场景遇到什么问题，最终希望观察到什么变化。
2. **范围与约束**：本轮必须包含什么、明确不做什么、有哪些技术或业务边界。
3. **行为与验收**：正常路径、失败路径、边界情况，以及每项结果需要什么证据。
4. **汇总与确认**：把结论整理成 Goal 草案，列出剩余未知项和第一项可执行增量，请用户确认。

会改变实现方向的未知项仍存在时，Goal 保持 `draft`，不开始编码。

### 已有规格仍然需要校准

用户提供 PRD、设计稿或规格文档时，Coordinator 不重复询问文档已经回答的问题，也不把文档直接视为无歧义的执行命令。

它先提取确定事实，再标出冲突、缺失、不可验证表述和外部依赖。只有高影响缺口需要继续提问，补充结论必须与原规格的差异一起展示。

目标是降低用户完善规格的负担，而不是要求用户先学会写符合 Agent 模板的文档。

### Goal 契约

确认后的 Goal 至少包含：

- 最终可观察结果和背景。
- 范围与非目标。
- 技术、兼容性、安全和权限约束。
- 带稳定 ID 的自动验收与人工验收条件。
- 每项验收需要的证据。
- 检查方式、停止条件和用户确认项。

Goal 是后续任务、问题和证据的根节点。没有 Goal 关联的活动，不应进入执行队列。

### 状态与阶段不是同一个概念

`status` 表示 Goal 的生命周期，例如 `draft`、`active`、`waiting_user`、`blocked` 和 `done`。

`phase` 表示当前正在进行哪类活动，例如 `clarifying`、`planning`、`implementing`、`inspecting` 或 `accepting`。

同一个 `active` Goal 可以先后经历多个 phase。将两者分开，才能让状态表达“目标是否仍在进行”，同时让阶段约束“Agent 此刻允许做什么”。

### 阶段副作用契约

澄清阶段应使用下面这样的显式契约：

```yaml
phase: clarifying

allowed_effects:
  - read_workspace
  - ask_user
  - update_goal_draft
  - update_handoff

write_scope:
  - docs/wali-0x3/goal.md
  - docs/wali-0x3/handoff.md

allow_new_artifacts: false
allow_implementation_changes: false
allow_external_writes: false
allow_svn_commit: false
```

这份契约表达的是：Agent 可以理解项目、向用户提问并维护 Goal 草稿，但不能因为某个 Skill 的默认流程而创建额外文档，也不能提前修改实现。

#### 当前实现状态

这组字段目前是待落地的设计目标，尚未被现有 Hook 解析和强制执行。

当前仓库只有原则性约束和结束时检查：

- [项目约定](CLAUDE.md)和[协作规则](claude/rules/collaboration.md)规定能力不等于写入授权。
- [Coordinator](claude/agents/coordinator.md)负责在调用前核对预期副作用。
- [Stop Hook](claude/hooks/wali_stop.py)检查 Goal 状态、完成证据和工作图一致性。

这些位置都没有解析 `allowed_effects` 或 `write_scope`，也不能在工具调用前阻止越界写入。

完整落地还需要：

1. 把阶段契约写入 `goal.md` frontmatter，作为权威配置。
2. 在 `handoff.md` 记录当前生效契约及本轮变化。
3. 在工具调用前检查写入和外部副作用。
4. 在会话结束时检查新增文件、越界修改和提交行为。
5. 为每种 phase 与副作用组合建立确定性测试。

在这些检查完成前，不能把行为原则描述成已经具备的技术强制能力。

## Assign：把 Goal 变成可负责的任务

Goal 明确后，Coordinator 先选择执行方式，再拆解任务。顺序不能颠倒，因为任务形态应服务实际协作方式，而不是为了填满角色列表。

### 执行方式

```text
主会话
适合小改动、强上下文关联和持续来回调整。

Subagent
适合独立调查、审查、测试分析和只需返回结论的工作。

Agent Teams
适合边界清楚、并行收益明显且角色需要持续沟通的复杂工作。

顺序执行
适合同一文件修改、强依赖或无法证明范围互斥的任务。
```

Agent 数量不是产出指标。协调成本高于并行收益时，使用更简单的方式。

### 任务契约

每项任务至少声明：

- 任务 ID 和关联验收条件。
- 负责人和独立验证者。
- 必要性与当前状态。
- 依赖任务。
- 允许修改范围。
- 任务自身的验收条件。
- 执行结果与证据。

任务必须足够小，能在一个会话内稳定推进；也必须足够完整，能产生可观察结果，而不是只完成没有用户价值的横向代码层。

### 当前可执行前沿

Coordinator 只能分派位于当前可执行前沿的任务。一个任务进入前沿，需要同时满足：

- 状态为 `pending`。
- 所有依赖任务均为 `done`。
- 没有关联的未关闭 `blocker`。
- 仍然关联有效验收条件。

两个前沿任务只有在修改范围可以证明互斥时，才可以并行。范围为空、使用自然语言、包含父目录别名或存在 glob 交集时，一律顺序执行。

## Loop：让实现、反馈和修复形成闭环

Loop 不是让 Agent 无限制重复工作。它是一个受 Goal、任务范围和停止条件约束的反馈循环。

```text
选择一个前沿任务
   ↓
Developer 实现最小完整增量
   ↓
运行自检并记录证据
   ↓
Reviewer / Tester 独立检查
   ↓
发现问题？── 是 → 记录 Issue → 修复 → 回归
   │
   否
   ↓
任务进入 done，选择下一前沿任务
```

### Developer 的循环

Developer 先读取 Goal、任务边界、相关代码和测试，再完成最小完整实现。它不能静默扩大范围，也不能通过删除测试、吞掉错误或降低检查标准获得表面成功。

实现与自检完成后，任务从 `working` 进入 `review`，而不是直接进入 `done`。

### Reviewer 与 Tester 的循环

Reviewer 检查目标符合性、范围、复杂度、安全、兼容性和测试遗漏。Tester 把验收条件转换成正常、失败、边界和回归场景。

两者都使用独立上下文，避免复述 Developer 的结论。发现的问题进入统一问题清单，不只停留在 Agent 返回消息中。

### Issue 闭环

问题状态只按下面的方向前进：

```text
open → fixing → verify → closed
```

修复者不能仅凭自己的自检关闭问题。问题进入 `verify` 后，由 Reviewer、Tester 或用户根据复现步骤和验证证据决定是否关闭。

### 三种“循环”需要区分

- Claude Code Agentic Loop：模型读取、行动、观察并继续调整的微观执行循环。
- WALI Loop：开发、审查、测试、修复和回归组成的项目闭环。
- 定时或外部等待：等待 CI、部署和外部评论，不应被用来反复驱动普通编码。

明确终点的本地开发由 Goal 推进；只有确实等待外部状态时，才进入外部轮询或事件通知。

## Inspect：用证据判断是否完成

Inspect 不是一次形式化审批，而是把每项验收条件映射到真实证据，再判断是否还需要回到 Loop。

### 自动检查

自动检查回答可由确定性命令判断的问题，例如：

- 构建、测试、Lint 和类型检查是否通过。
- 工作图引用是否有效，任务依赖是否成环。
- required 任务是否完成并留下独立证据。
- 是否仍存在未关闭的 blocker。

WALI Hook 只检查自己的状态与关系一致性，不能替代业务项目的真实构建和测试命令。

### 语义检查

Reviewer 和 Tester 判断自动命令无法回答的问题：实现是否真正满足目标、是否越界、失败行为是否合理，以及测试是否遗漏关键风险。

### 用户验收

自动条件和独立检查通过后，Goal 进入 `waiting_user`，等待用户执行真实业务回测。

只有用户明确确认结果可接受，human 验收条件才可以标记为 `verified`，Goal 才能进入 `done`。

### 完成不是一句总结

一个可信的 Inspect 输出必须逐项说明：

- 验收条件及对应证据。
- 执行过的命令、退出结果和摘要。
- 独立审查与测试结论。
- 未关闭问题、风险和未覆盖范围。
- SVN 差异范围。
- 仍需用户确认的事项。

证据不足时继续 Loop，不用总结替代验证。

## 角色与责任

角色不是固定岗位编制。Coordinator 根据当前 Goal 选择真正需要的角色。

每个 Agent 定义只保留一个“身份”段，角色定位与思维方式已经融合。

| Agent | 身份与思维方式 | 责任 |
| --- | --- | --- |
| Coordinator | 以列奥纳多·达·芬奇的跨学科视角连接目标、专业边界和责任空白 | 澄清 Goal、选择执行方式、治理工作图、协调状态、判断完成 |
| Developer | 以 Linus Torvalds 的工程标准追求最少、清晰、可维护的实现 | 分析、开发、自检、问题修复和实现交接 |
| Reviewer | 以第一性原理质疑需求、复杂度和潜在爆点 | 独立审查目标符合性、范围、质量、安全和兼容性 |
| Tester | 以理查德·费曼的实证精神把需求转成可复现实验 | 测试设计、问题复现、自动化测试、回归和独立验证 |

Coordinator 不包揽所有实现，Developer 不宣布最终完成，Reviewer 默认不直接修实现，Tester 不把单个成功路径当成完整验收。

## 持久状态与可恢复性

会话消息和 Agent 内部 Todo 可以服务当前执行，但不能成为项目的唯一状态来源。

wali-0x3 默认只使用四个 Markdown 文件保存治理状态：

| 文件 | 回答的问题 |
| --- | --- |
| `goal.md` | 为什么做、做什么、怎样才算完成？ |
| `todo.md` | 当前有哪些任务、依赖、责任和执行证据？ |
| `issues.md` | 发现了什么问题、由谁修复、是否独立复验？ |
| `handoff.md` | 现在停在哪里，下一会话从哪里继续？ |

`handoff.md` 是最新恢复快照，不是持续追加的进度历史。每轮结束时覆盖旧快照，只保留恢复真正需要的状态、证据、风险和下一步。

它已经取代早期的 `progress.md`：这里需要的是恢复游标，而不是另一份越来越长、很快失真的过程日志。

### 状态模型

Goal 生命周期：

```text
draft → active → waiting_user → done
                 ↘ blocked
```

Task 生命周期：

```text
pending → working → review → done
             ↘ blocked
```

Issue 生命周期：

```text
open → fixing → verify → closed
```

Goal 的 `status` 表示生命周期，`phase` 表示当前活动。两者不能混用。

## Graph Engineering：状态一致性的支撑机制

Graph Engineering 不是 WALI 之外的第五阶段。它把四个状态文件中已经存在的关系显式化，用来支持 Assign、Loop 和 Inspect。

Markdown 仍是唯一真实来源。脚本只在运行时派生内存工作图，不引入图数据库，不创建持久化 `graph.md`，也不使用 GraphRAG。

### 节点与关系

```text
Goal        G-XXX
验收条件    AC-XXX
Task        T-XXX
Issue       I-XXX
Agent       coordinator / developer / reviewer / tester / user
Evidence    从各节点证据字段派生
```

```text
Goal 包含 AC
Task 实现 AC
Task 依赖 Task
Issue 影响 Task 或 AC
Agent 负责或验证 Task
Task、AC、Issue 连接 Evidence
```

这些边直接来自 `关联 AC`、`依赖`、`关联任务`、`负责人`、`独立验证者` 和证据字段，不维护第二份关系文档。

### 工作图提供什么

- 检查 Goal ID 格式，以及 AC、Task 和 Issue ID 的格式与重复。
- 检查不存在的引用、空 ID、缺失的验收覆盖和任务依赖环。
- 识别当前可执行前沿。
- 排除被未关闭 blocker 影响的候选任务。
- 只在修改范围可证明互斥时提供安全并行候选。
- 按需输出 Mermaid，帮助人理解关系。

Mermaid 只输出到标准输出，不自动创建文件。Graph 检查也不代替构建、测试、语义审查或用户验收。

## 能力与副作用

阶段契约决定 Agent 可以产生什么副作用。Skill 或工具自己的默认行为不能扩大这份授权。

调用前：

1. 识别能力会读取、创建、修改和发布什么。
2. 与 Goal、phase、任务范围和用户授权求交集。
3. 只有副作用能够证明位于交集内时，才直接调用。

副作用未知或越界时：

- 要求能力只返回结论。
- 在仓库外临时位置隔离执行。
- 借鉴其方法，由 WALI 控制最终写入。
- 确实需要扩大范围时，请用户明确授权。

调用后检查版本控制状态和实际差异。自动生成物不自动成为项目资产；调用前已经存在或来源不明的用户文件也不能被擅自清理。

这套约束针对所有当前与未来能力，不硬编码某个 Skill 或某个自动生成文件的名称。

## 长任务、Handoff 与 SVN

### 版本控制边界

这里存在两个不同环境：

| 环境 | 版本控制 | 规则 |
| --- | --- | --- |
| 当前 wali-0x3 设计仓库 | Git | 用于维护、审阅和保存这套设计归档 |
| 部署后的 Agent 工作项目 | SVN only | Agent 的启动、恢复、差异检查和提交规则只使用 SVN |

目标环境中的 Agent 不使用 Git branch、worktree、PR 或 push 语义。当前设计仓库使用 Git，不改变目标环境的这一约束。

### 会话开始

在目标 SVN 工作副本中，Agent 根据网络和权限执行：

```bash
svn info
svn status
svn diff
svn log -l 10
svn status -u
```

随后读取四个 WALI 状态文件，用真实代码、SVN 状态和最新验证结果校正过期记录。

### 会话结束

每轮结束时：

1. 运行与风险相称的业务验证和 WALI 检查。
2. 更新任务、问题和验收证据。
3. 覆盖更新 `handoff.md`。
4. 记录工作副本 URL、修订信息、基准修订和本地修改。
5. 留下下一项可执行任务和恢复命令。

SVN 提交会直接写入共享仓库。只有用户授权或项目规则明确要求时，才执行 `svn update`、处理冲突、重新验证并执行 `svn commit`。SVN 没有独立 push 步骤。

## 归档目录与部署目录

当前仓库为了让文件在管理工具中保持可见，故意使用：

```text
claude/
```

不要在这个设计归档中自动改成隐藏的 `.claude/`。

部署到真实 Claude Code 项目时，由使用者自行完成：

```text
claude/ → .claude/
```

`CLAUDE.md`、Hook 设置和核心设计文档中的 `.claude/` 表示部署后的运行形态。`claude/settings.json` 也只有部署为 `.claude/settings.json` 后才会被 Claude Code 自动加载。

## 项目结构

```text
wali-0x3/
├── README.md
├── CLAUDE.md
├── wali-0x3-core-design.md
├── wali-0x3品牌与虚拟形象.md
├── claude/                         # 当前可见归档；部署时由用户改名
│   ├── settings.json
│   ├── agents/
│   │   ├── coordinator.md
│   │   ├── developer.md
│   │   ├── reviewer.md
│   │   └── tester.md
│   ├── hooks/
│   │   ├── wali_graph.py
│   │   ├── wali_stop.py
│   │   ├── test_wali_graph.py
│   │   └── test_wali_stop.py
│   ├── rules/
│   │   ├── collaboration.md
│   │   ├── engineering.md
│   │   └── testing.md
│   └── skills/
│       ├── wali-start/
│       ├── wali-resume/
│       ├── wali-inspect/
│       └── wali-handoff/
└── docs/
    └── wali-0x3/
        ├── goal.md
        ├── todo.md
        ├── issues.md
        └── handoff.md
```

## 快速开始

以下步骤描述部署后的目标 SVN 项目。

### 1. 部署配置

把归档内容复制到目标工作副本，并由使用者把 `claude/` 改名为 `.claude/`。

### 2. 读取真实项目

确认 SVN 工作副本、已有本地修改、构建命令和项目约定。不要根据 wali-0x3 示例臆造业务验证命令。

### 3. 建立 Goal 草案

从 `docs/wali-0x3/goal.md` 开始。Coordinator 按 Work 阶段逐步澄清需求，Goal 保持 `draft`，直到用户确认。

### 4. 建立任务关系

为验收条件分配 `AC-XXX`，在 `todo.md` 建立关联任务、依赖、负责人和修改范围。发现的问题以 `I-XXX` 进入 `issues.md`。

### 5. 检查并推进

运行工作图检查，从当前可执行前沿选择一个 required 任务。完成实现、自检、独立验证和 Issue 闭环后，再选择下一任务。

### 6. Inspect 与 Handoff

逐项展示验收证据。需要业务回测时进入 `waiting_user`；每轮结束时覆盖更新 `handoff.md`。

## 命令参考

当前归档仓库使用可见的 `claude/` 路径：

```bash
python3 claude/hooks/test_wali_graph.py -v
python3 claude/hooks/test_wali_stop.py -v

python3 claude/hooks/wali_graph.py --project-root . check
python3 claude/hooks/wali_graph.py --project-root . frontier
python3 claude/hooks/wali_graph.py --project-root . parallel
python3 claude/hooks/wali_graph.py --project-root . mermaid

python3 claude/hooks/wali_stop.py --project-root .
python3 -m json.tool claude/settings.json
```

部署后的项目使用 `.claude/` 路径：

```bash
python3 .claude/hooks/test_wali_graph.py -v
python3 .claude/hooks/test_wali_stop.py -v

python3 .claude/hooks/wali_graph.py --project-root . check
python3 .claude/hooks/wali_graph.py --project-root . frontier
python3 .claude/hooks/wali_graph.py --project-root . parallel
python3 .claude/hooks/wali_graph.py --project-root . mermaid

python3 .claude/hooks/wali_stop.py --project-root .
python3 -m json.tool .claude/settings.json
```

这些命令只验证 WALI 配置和状态一致性，不能替代业务项目的构建、测试、Lint、类型检查、安全检查和用户回测。

## 当前实现与后续工作

当前已经实现：

- 四个 Agent 的身份与职责定义。
- Goal、Task、Issue 和 Handoff 模板。
- Markdown 派生工作图。
- 关系、依赖环、验收覆盖和并行范围检查。
- 当前可执行前沿与安全并行候选。
- Mermaid 标准输出。
- Goal 完成状态与独立证据检查。

仍需继续设计或实现：

- `phase` 与 `status` 的正式枚举及转换规则。
- `allowed_effects`、`write_scope` 和副作用布尔字段。
- 工具调用前的阶段权限检查。
- 新增产物、越界修改和外部写入检查。
- 从澄清、实现到 Inspect 的阶段策略测试。

第一版刻意不引入图数据库、GraphRAG、独立运行时编排引擎、复杂工作流 DSL、自动抢占或强制 Agent Teams。

## 文档导航

- [核心设计](wali-0x3-core-design.md)：完整运行模型、角色、状态和恢复协议。
- [品牌与虚拟形象](wali-0x3品牌与虚拟形象.md)：`wali-0x3` 与 `waliwali` 的品牌关系。
- [项目级约定](CLAUDE.md)：部署后所有 Agent 必须遵守的核心规则。
- [Goal 模板](docs/wali-0x3/goal.md)：目标契约和验收条件。
- [任务模板](docs/wali-0x3/todo.md)：任务、依赖、范围与证据。
- [问题模板](docs/wali-0x3/issues.md)：问题发现、修复和关闭验证。
- [Handoff 模板](docs/wali-0x3/handoff.md)：最新恢复快照。

## 品牌关系

`wali-0x3` 是虚拟开发团队及其协作系统的名称。

`waliwali` 是团队面向使用者的统一虚拟形象，不对应某个具体调度或开发 Agent。

> waliwali，由 wali-0x3 驱动的虚拟开发伙伴。
