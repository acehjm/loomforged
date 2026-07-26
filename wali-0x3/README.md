# wali-0x3

> 让 Claude Code 中的项目开发可分派、可检查、可恢复、可验收。

`wali-0x3` 是一套嵌入项目仓库的 Agent 开发治理机制。它不替代 Claude 的编码能力，而是在编码能力之外建立目标契约、执行边界、证据链和恢复协议。

目标运行环境只使用 SVN。当前存放这套设计的归档仓库使用 Git，两者互不替代。归档目录保持为可见的 `claude/`；部署到目标项目时，由使用者自行复制或改名为 `.claude/`。

当前核心设计版本为 `0.14`，状态为 `implemented`。控制面已有确定性回归测试，但每个目标环境仍必须通过只读 Doctor、Claude Code 自检和真实 SVN 冒烟验证。

## 1. 它解决什么问题

Agent 很擅长读取代码、修改文件和运行命令。项目真正困难的部分，是把模糊需求稳定推进到可信交付。

没有治理层时，常见问题包括：

- Goal 还不清楚，代码已经开始修改。
- 用户提供了规格，但其中的遗漏、冲突和不可测试条款没有被发现。
- 多个 Agent 同时活动，却没有明确依赖、文件所有权和验证责任。
- Developer 完成修改后直接宣布任务完成，没有独立审查和业务验收。
- 长任务的状态只存在于对话里，换会话后只能猜测。
- Skill 或工具自动创建文件、修改仓库或写入外部系统，越过了当前任务授权。
- SVN 工作副本中的用户修改、属性变化和待提交内容被误覆盖或遗漏。

WALI 把这些不确定性转成五份可读状态、十个受控阶段、一条可检查工作图和一组 fail-closed Hook。

## 2. 核心设计原则

### 先定义完成，再开始执行

实现前必须知道最终可观察结果、范围、非范围、约束、验收条件、验证方法和需要用户决定的事项。

### Goal 与 Spec 共同约束实现

Goal 回答“为什么做、做到什么程度”。Spec 回答“系统具体必须如何表现，以及怎样判定正确”。

用户无论是否提供规格资料，最终都要形成固定的 `spec.md`。Goal 和 Spec 作为一个联合确认包由用户一次确认。

### 能力不等于授权

Agent、Skill、脚本和工具只提供能力。实际动作仍必须符合当前阶段的 `allowed_effects`、`write_scope` 和副作用开关。

未知副作用默认拒绝。WALI 不维护特定 Skill 的黑名单，也不依赖某个外部方法论是否存在。

### 一次推进一个可验证增量

任务应足够小，能在一个会话内稳定推进；也应足够完整，能产生可观察结果，而不是只完成一个没有用户价值的横向技术层。

### 实现者不能成为唯一检查者

Developer 负责实现与自检。Reviewer、Tester 或用户负责独立验证。代码修改完成不等于 Task、AC 或 Goal 已完成。

### 用户保留最终业务验收权

自动测试和独立审查可以证明技术条件，但真实业务结果是否可接受，最终仍由用户确认。

### Markdown 是唯一项目状态源

Goal、Spec、Task、Issue 和 Handoff 保存在固定 Markdown 文件中。运行时图、Agent 面板和对话记录都不能替代这些文件。

### 默认使用最简单的执行方式

主会话能稳定完成时不增加 Agent。只有独立判断有价值时使用 Subagent；只有边界清楚、并行收益显著时才使用 Agent Teams。

## 3. Goal 与 Spec：先把目标变成可确认契约

用户通常不会一开始就提供完整 Goal。WALI 不要求用户填写长表单，而是由 Coordinator 逐轮提问，每轮只处理 1–3 个会改变结果的高影响问题。

### 用户没有完整规格

采用开放式访谈，依次收敛：

1. 谁在什么场景遇到什么问题。
2. 最终希望观察到什么变化。
3. 本轮包含和不包含什么。
4. 正常、失败和边界行为是什么。
5. 用什么证据判断完成。

### 用户已经提供资料

接口文档、需求、PRD 或规格说明书不会被直接视为完整真相。Coordinator 对它执行规格压力测试：

- 是否缺少必要行为或异常语义。
- 是否存在歧义或内部冲突。
- 是否与真实代码、配置或依赖冲突。
- 是否包含无法形成明确测试的条款。
- 是否遗漏兼容、数据、权限或迁移边界。

资料明确但仍有关键空白时，使用 `hybrid`：先提取已有条款，再通过开放式问题补齐缺口。

### 联合确认

高影响问题收敛后，Coordinator 生成自包含的 Goal + Spec 确认包，其中至少包括：

- 目标、背景、范围和非范围。
- 约束、决策、假设和风险。
- 带稳定 ID 的 `R-XXX` Requirement。
- `R-XXX → AC-XXX` 关系。
- 行为、接口、数据、错误和质量约束。
- 每个 AC 的唯一判定规则和验证方法。
- 第一个可验证增量。

只有用户明确确认当前版本，Goal 才从 `clarifying` 进入 `planning`。沉默、Agent 自己总结或“看起来没问题”都不构成确认。

Goal 或 Spec 的稳定定义发生变化后，原确认自动失效，必须回到澄清并重新确认。

## 4. WALI 工作循环

WALI 代表：

> **Work · Assign · Loop · Inspect**

```text
Work：澄清 Goal + Spec
  ↓
Assign：拆解与认领任务
  ↓
Loop：实现、审查、测试、修复
  ↓
Inspect：映射证据并验收
  ├─ 仍有缺口 ─────────→ 回到 Loop
  └─ 用户验收通过 ─────→ Exit：交付或关闭
```

### Work

读取用户输入、项目资料、真实代码和 SVN 状态。通过访谈或规格压力测试形成经确认的 Goal + Spec。

### Assign

Coordinator 选择主会话、Subagent、Agent Teams 或顺序执行，再把 Requirement 和 AC 拆成带依赖、负责人、验证者与精确修改范围的任务。

### Loop

Developer 实现最小增量并自检。Reviewer 和 Tester 独立检查。发现的问题进入 Issue 状态机，修复后重新回归。

### Inspect

把每个 AC 映射到真实证据，检查 required Task、未关闭 blocker、项目测试、独立验证和用户业务回测。

证据不足时返回 Loop。全部满足时，才允许成功退出。

### 三种 Loop 不要混用

- Claude Code Agentic Loop：模型读取、行动、观察并继续调整。
- WALI Loop：开发、审查、测试、修复和回归组成的项目闭环。
- Claude Code `/loop`：等待 CI、部署或评论等外部状态。

有明确终点的本地开发使用 `/goal` 持续推进。只有确实在等待外部状态时才使用 `/loop`。

## 5. 阶段契约：把原则变成可执行边界

`status` 描述 Goal 生命周期，`phase` 描述当前允许进行的活动。二者不能混用。

每个 phase 都有固定 profile。Goal frontmatter 中的 effect、范围和布尔开关必须与 profile 一致，任意放大都会被 Policy 拒绝。

| phase | 目的 | 主要写入边界 |
| --- | --- | --- |
| `clarifying` | 访谈、压力测试、形成 Goal + Spec | Goal、Spec、Handoff |
| `awaiting_direction` | 等待高影响方向选择 | Goal、Handoff |
| `planning` | 建立工作图与前沿任务 | WALI 治理文件 |
| `implementing` | 实施一个活动任务 | 治理文件与任务精确范围 |
| `inspecting` | 独立审查、测试和问题闭环 | 治理文件，不改实现 |
| `accepting` | 等待用户业务验收 | Goal、Issue、Handoff |
| `blocked` | 记录无法安全绕过的阻断 | Goal、Handoff |
| `delivering` | 只读复核与精确 SVN 提交 | Goal、Handoff、授权路径 |
| `closed` | 无需提交的成功终态 | 受控 Handoff 或新 Goal |
| `terminated` | 取消、替代或安全中止 | 受控 Handoff 或新 Goal |

阶段转换必须原子更新完整契约，不能只改 `phase`。成功流程不能跳过 `inspecting` 和 `accepting`。

`handoff` 表示可恢复的会话暂停，`blocked` 表示 Goal 被真实条件阻断。二者都不是成功完成。

用户取消、Goal 被替代或安全策略不允许继续时，分别以 `cancelled`、`superseded` 或 `aborted` 进入 `terminated`，并记录原因、证据和未提交变更处置。

## 6. 五份持久状态

`docs/wali-0x3/` 中的五个文件共同保存项目状态：

| 文件 | 权威内容 |
| --- | --- |
| `goal.md` | 意图、范围、AC、确认状态、phase 与权限契约 |
| `spec.md` | Requirement、行为、接口、数据、错误和验收判定 |
| `todo.md` | Task、依赖、负责人、修改范围和执行证据 |
| `issues.md` | 审查、测试和用户问题的修复闭环 |
| `handoff.md` | 覆盖式恢复游标、风险和唯一下一步 |

`handoff.md` 不是进度日志。它取代 `progress.md`，每次只保存最新的可恢复快照。

默认不创建 `context.md`、`progress.md`、额外 plan、记忆文件或持久图副本。新增产物必须同时被 Goal 纳入范围并由当前阶段授权。

`goal.md` 必须声明受支持的 `wali_schema: 1`。缺失或未知 schema 会 fail closed，WALI 不执行静默迁移。

## 7. Graph Engineering：从状态派生可检查关系

Graph Engineering 不是 WALI 之外的独立流程，也不是 GraphRAG。

WALI 从五份 Markdown 状态中派生内存工作图，不创建图数据库或 `graph.md`。Graph 的作用是让 Goal、Requirement、AC、Task、Issue、Agent 和 Evidence 之间的关系可检查。

核心追踪链为：

```text
Requirement → AC → Task → Evidence
```

工作图还包含：

- Task 依赖 Task。
- Issue 影响 Task 或 AC。
- Agent 负责或验证 Task。
- Skill 为 Task 提供方法关系，但不提供权限。

Graph 检查负责发现重复 ID、不存在的引用、依赖环、缺失验收覆盖、无效 Evidence 和越权 Skill。

它还能计算当前可执行前沿，并只在多个任务的精确修改范围可证明互斥时给出安全并行候选。

Mermaid 只是按需输出的阅读视图，不是第二份状态源：

```bash
python3 .claude/hooks/wali_graph.py --project-root . mermaid
```

## 8. Agent 角色与思考深度

主会话承担 Coordinator。其他角色只在当前阶段和任务确实需要时启用。

| Agent | 身份 | 默认模型 / effort | 责任 |
| --- | --- | --- | --- |
| Coordinator | 连接目标、专业边界和责任空白的跨学科协调者 | `opus / high` | Goal、Spec、工作图、转段和完成判断 |
| Architect | 关注作用力、边界与演进风险的只读架构顾问 | `opus / xhigh` | 高影响架构方案比较，不直接写实现 |
| Developer | 追求最少、清晰、可维护实现的工程师 | `sonnet / high` | 一个活动任务的实现、自检和修复 |
| Reviewer | 用第一性原理寻找偏离、复杂度和风险的检查者 | `opus / high` | 独立审查，默认不直接修实现 |
| Tester | 把需求转成可复现实验的验证者 | `sonnet / high` | 测试设计、复现、回归和独立证据 |

模型或组织策略不支持声明的 effort 时，可以降级模型能力，但不能降低阶段、范围、验证和 SVN 权限要求。

多个 Developer 可以按不同模块或业务并行工作，但必须满足：

- 每个 Agent 同时只拥有一个主要 Task。
- Task 的依赖已经满足。
- 修改范围是精确且可证明互斥的。
- 每个并行写入者使用独立 SVN 工作副本。
- 结果回到统一 Task、Issue 和 Evidence 链。

## 9. Agent 监督与异常恢复

Claude Code 的 Agent 运行状态不等于 WALI Task 状态。

`TaskCompleted` 只说明一次 Agent 运行返回，不能自动把 Task 设为 `done`。`StopFailure` 只说明 API 级失败，也不能自动把 Task 设为 `blocked`。

监督 Hook 接入：

- `TeammateIdle`：在队友进入 idle 前检查活动任务与证据。
- `TaskCompleted`：检查事件是否对应当前任务及合法状态。
- `StopFailure`：只记录失败事实，不伪造决策控制。

运行事件保存在 `.svn/wali-policy/supervision.json`，不进入 SVN。并发写入使用操作系统文件锁，进程退出后由内核释放。

Agent 卡住或异常退出时：

1. 冻结当前 Task 和路径所有权。
2. 核对 Agent 面板、transcript、WALI Task 和 SVN 差异。
3. 优先恢复原 Agent。
4. 需要替换时，先记录恢复动作和证据。
5. 不自动清理、覆盖、回退或生成替代实现。

## 10. SVN 边界与原生 Ignore

目标项目必须使用 SVN 1.9+，并从真实工作副本根运行 WALI。

所有有副作用动作通过 `svn info --show-item wc-root` 验证边界。普通子目录不能因为本地没有 `.svn` 而绕过检查。

### 用户已有修改

首次建立 Goal 时，`baseline` 记录调用前已有或来源不明的差异指纹。这些内容默认视为用户资产，不覆盖、不回退、不擅自纳入任务。

实现转入检查前，`carry` 冻结当前代合法差异。修复后生成新代，旧证据只追加，不覆盖。

### 原生 Ignore

项目 Ignore 由人维护版本化的 `svn:ignore` 或 `svn:global-ignores` 属性。WALI 不创建 `.svnignore`，也不自动执行 `propset`、`propedit` 或 `propdel`。

读取状态时，WALI 清空个人客户端 `global-ignores`，再使用 `--no-ignore` 获取完整 XML 状态。

只有由项目属性匹配、且自身和祖先属性没有本地修改的 `ignored` 项，才被归类为项目本地产物。

这些本地产物不会进入 baseline、carry、handoff 摘要、Stop 或提交差异。普通未版本化文件、冲突、externals 和属性变化仍然接受审计。

如果 Ignore 属性本身或祖先属性存在本地修改，被忽略的后代立即恢复为需要审计，防止通过临时修改属性隐藏差异。

### SVN 提交

SVN 提交只在 `delivering` 中允许，并必须同时具备：

- 用户业务验收通过。
- 当前 carry 有效。
- 用户当场确认逐个精确 leaf path。
- 提交前差异与授权指纹一致。
- 提交后路径清洁，并取得统一修订号回执。

提交授权不包含 update、冲突解决、externals、部署或发布。交付前发现过期或冲突时，必须返回合法实施任务处理并重新验证。

## 11. Rules、Refs、Skills 与项目资料

不同类型的信息放在不同层：

| 内容 | 位置 | 作用 |
| --- | --- | --- |
| 所有会话必须知道的稳定事实 | `CLAUDE.md` | 短小的项目入口 |
| 跨项目、违反时应阻止交付的硬约束 | `.claude/rules/` | 按路径加载的确定性规则 |
| 跨项目稳定、按角色读取的资料 | `.claude/refs/` | 操作说明、模板和代码检查基线 |
| 可重复的多步骤方法 | `.claude/skills/` | 工作流程，不扩大权限 |
| 单个项目的需求、接口和模块约束 | 项目 `docs/` | 保留原始来源 |
| 当前 Goal 的规范化实施依据 | `spec.md` | 开发与测试权威契约 |

`refs/templates/` 保存 Developer 可跨项目使用的返回格式、分页、错误处理和事件流程模板。

`refs/compliance/` 保存 Developer 与 Reviewer 使用的企业内部代码质量、安全和工程检查基线。这里的“合规”不表示法规资料。

新增同类 Ref 时，只维护对应索引。Agent 通过 `refs/INDEX.md` 按角色和场景读取，不需要逐个修改 Agent 身份。

项目特有的接口协议、模块边界、依赖约束和特殊检查留在项目 `docs/`，其采用结论编译进 `spec.md`，不反复维护到共享 Refs。

## 12. 项目结构

```text
wali-0x3/
├── README.md
├── CLAUDE.md
├── wali-0x3-core-design.md
├── claude/                          # 归档形态；部署时改为 .claude/
│   ├── settings.json
│   ├── agents/
│   │   ├── coordinator.md
│   │   ├── architect.md
│   │   ├── developer.md
│   │   ├── reviewer.md
│   │   └── tester.md
│   ├── hooks/
│   │   ├── wali-doctor.py
│   │   ├── wali_board.py
│   │   ├── wali_graph.py
│   │   ├── wali_policy.py
│   │   ├── wali_stop.py
│   │   ├── wali_supervision.py
│   │   ├── wali_svn.py
│   │   └── test_wali_*.py
│   ├── refs/
│   │   ├── INDEX.md
│   │   ├── compatibility.md
│   │   ├── operations.md
│   │   ├── templates/INDEX.md
│   │   └── compliance/INDEX.md
│   ├── rules/
│   │   ├── engineering.md
│   │   └── testing.md
│   └── skills/
│       ├── wali-start/
│       ├── wali-resume/
│       ├── wali-inspect/
│       └── wali-handoff/
├── waliwali/                       # 品牌源文件；看板已内嵌，不是运行依赖
│   ├── agent.png
│   └── mutil-agents.png
└── docs/wali-0x3/
    ├── goal.md
    ├── spec.md
    ├── todo.md
    ├── issues.md
    ├── handoff.md
    └── wali-board.html
```

## 13. 部署到 SVN 项目

### 13.1 前置条件

- Python 3.9+。
- SVN CLI 1.9+。
- 支持项目级设置、Hook exec form、Agent frontmatter 和路径 Rules 的 Claude Code。
- POSIX `fcntl.flock` 或 Windows `msvcrt.locking`。

Agent Teams 和三类监督 Hook 是可选增强。目标环境不支持时，使用主会话或普通 Subagent 顺序执行，Policy、Stop、Task 和 Evidence 仍然有效。

### 13.2 复制文件

将以下内容放到目标 SVN 工作副本根：

- `CLAUDE.md`
- `claude/` 的内容，并把目录名改成 `.claude/`
- `docs/wali-0x3/`

如果目标项目已经有 `.claude/settings.json`、Agents、Rules 或 Skills，应人工合并，不要覆盖既有配置。

归档仓库继续保留 `claude/`，不要在这里创建 `.claude/`。目标项目中的 `.claude/` 和 WALI 状态文件应由项目维护者按组织流程加入 SVN。

### 13.3 运行只读 Doctor

```bash
python3 .claude/hooks/wali-doctor.py --project-root .
```

Doctor 会检查：

- 核心目录和固定状态文件。
- Python 版本。
- `claude --version` 与只读 `claude doctor`。
- Policy、Stop 和监督 Hook 配置。
- SVN 版本、工作副本根和完整状态读取。
- Goal schema、阶段契约和工作图。
- 原生 Ignore 分类数量。

Doctor 只调用读取命令，不创建文件、不修改 SVN 属性、不执行 `svn add`、`svn update` 或 `svn commit`。

返回码为 0 表示没有失败项；警告不会单独造成失败。Doctor 不能替代业务项目自己的构建、测试和用户验收。

### 13.4 首次人工核对

进入 Claude Code 后执行：

1. `/doctor`：确认项目配置没有解析错误。
2. `/memory`：确认只加载预期常驻说明。
3. `/hooks`：确认三类核心 Hook；启用 Agent Teams 时再确认三类监督 Hook。
4. 运行完整 WALI 回归测试。
5. 在真实工作副本根核对 `svn info`、`svn status` 和 `svn diff --internal-diff`。
6. 使用原生 Ignore 时，验证项目规则和个人客户端规则不会混淆。

完整回归命令：

```bash
cd .claude/hooks
python3 -m unittest -v \
  test_wali_graph.py \
  test_wali_policy.py \
  test_wali_stop.py \
  test_wali_supervision.py \
  test_wali_svn.py \
  test_wali_doctor.py \
  test_wali_board.py
```

### 13.5 启动只读看板

在目标 SVN 工作副本根运行：

```bash
python3 .claude/hooks/wali_board.py --project-root . --open
```

命令会启动持续运行的本地只读服务，并由 `--open` 自动打开浏览器。终端出现以下提示后，看板即已开始工作：

```text
WALI 只读看板：http://127.0.0.1:8765/
每 1 秒读取一次项目状态；按 Ctrl-C 停止。
```

看板采用 1 秒轮询，因此属于准实时更新：

- 服务运行期间，浏览器每 1 秒重新聚合 Goal、Task、Issue、Agent 和可选运行事件。
- 状态文件发生变化后无需刷新页面，通常会在下一次轮询中显示。
- 标签页进入后台时暂停轮询，重新显示后立即读取最新状态。
- 某次读取失败时保留最后一次有效状态，并在后续轮询中自动恢复。
- 关闭浏览器不会停止服务；返回启动它的终端并按 `Ctrl-C` 才会结束。

启动器只绑定本机地址，使用 Python 标准库提供页面和聚合状态 API。页面不会修改项目状态，也不展示修改范围、证据文件或 SVN 内部路径。看板使用的两张品牌图已经压缩并内嵌到 HTML，部署时不需要复制 `waliwali/`。

看板运行时实际只依赖 `.claude/hooks/wali_board.py` 和 `docs/wali-0x3/wali-board.html`。保留 Python 服务的原因是普通浏览器页面无权自行读取项目工作区；若增加双击启动脚本，只是把同一条命令包装起来，并不会减少运行依赖。

Agent 运行事件由监督 Hook 在真实 SVN 工作副本中按需生成，不需要人工创建或复制。尚无运行事件时，看板继续根据任务负责人和任务状态展示团队，并把运行状态显示为“无近期活动”。

默认地址是 `http://127.0.0.1:8765/`。如果端口被占用，可以指定其他端口：

```bash
python3 .claude/hooks/wali_board.py --project-root . --port 8877 --open
```

### 13.6 开始第一个 Goal

从 SVN 工作副本根调用：

```text
/wali-start <需求描述或规格资料路径>
```

`wali-start` 会识别 `discovery`、`pressure_test` 或 `hybrid`，逐轮完善 Goal 与 Spec。确认前不会规划或修改实现。

## 14. 日常使用

### 新需求或规格输入

```text
/wali-start <需求、接口文档或规格路径>
```

### 从中断位置恢复

```text
/wali-resume
```

恢复时会读取 Goal、Spec、工作图、Handoff、监督状态和真实 SVN 差异，不把过期文档直接当作事实。

### 进入独立检查

```text
/wali-inspect
```

只有当前实现已通过自检并生成有效 carry 时，才进入 Reviewer、Tester 和 Issue 闭环。

### 保存恢复游标

```text
/wali-handoff
```

它只更新当前 phase 允许的固定状态文件，并刷新 `state_digest`。

## 15. 常用只读命令

```bash
python3 .claude/hooks/wali-doctor.py --project-root .
python3 .claude/hooks/wali_policy.py --project-root . check
python3 .claude/hooks/wali_policy.py --project-root . audit
python3 .claude/hooks/wali_graph.py --project-root . check
python3 .claude/hooks/wali_graph.py --project-root . frontier
python3 .claude/hooks/wali_graph.py --project-root . parallel
python3 .claude/hooks/wali_graph.py --project-root . mermaid
python3 .claude/hooks/wali_supervision.py --project-root . status
python3 .claude/hooks/wali_stop.py --project-root .
```

持续查看只读项目状态：

```bash
python3 .claude/hooks/wali_board.py --project-root . --open
```

会产生治理状态输出的 `baseline`、`carry`、`digest` 和 `handoff-digest` 只能在对应阶段、写入范围和工作流中使用，不应作为普通只读命令随意执行。

## 16. 如何扩展

### 增加跨项目开发模板

把文件加入 `.claude/refs/templates/`，并在该目录的 `INDEX.md` 登记稳定 Ref ID、版本、适用场景和不适用场景。

模板默认只由 Developer 按场景读取。项目例外写入该项目 Spec，不修改共享模板迁就单个项目。

### 增加企业代码检查基线

把文件加入 `.claude/refs/compliance/`，并在对应 `INDEX.md` 登记检查主题、读取角色、严重程度和通过条件。

Developer 用它自检，Reviewer 用它独立审查。执行结果和项目豁免仍写入当前 Goal、Task、Issue 或 Spec。

### 增加 Skill

只有真正可重复的多步骤方法才适合成为 Skill。Skill 必须声明副作用，且实际调用需要同时满足 Goal 授权、Task 方法关系和当前阶段权限。

仅供 Agent 阅读的模板或清单不需要包装成 Skill。

### 增加项目资料

把需求、接口、模块边界、依赖和项目特殊约束放到项目 `docs/`。Coordinator 核对来源和适用范围，再把当前 Goal 采用的结论编译进 `spec.md`。

## 17. 明确边界

WALI 是授权与审计层，不是操作系统安全沙箱。

Hook、SVN 客户端与服务端、用户、项目命令及其依赖属于可信计算基础。同一系统用户下的对抗性进程仍可能伪造本地状态。

项目命令或依赖不可信时，不应由 Agent 在本地运行。应改在隔离环境或 CI 中执行，再把结果作为外部证据带回。

当前设计刻意不引入：

- `.svnignore` 与自动 `propset`。
- GraphRAG、图数据库或持久 `graph.md`。
- 自动抢占、自动清理或无证据替换 Agent。
- 强制所有任务使用 Agent Teams。
- 由 Skill 名称硬编码的权限黑名单。
- 自动生成额外 context、progress、plan 或 memory 文件。

## 18. 文档导航

- [核心设计](wali-0x3-core-design.md)：完整状态机、威胁模型和实现原理。
- [项目约定](CLAUDE.md)：所有 Agent 的常驻入口。
- [兼容性说明](claude/refs/compatibility.md)：部署能力、降级和核对清单。
- [操作说明](claude/refs/operations.md)：转段、恢复、监督和 SVN 交付。
- [Refs 索引](claude/refs/INDEX.md)：跨项目资料的角色与场景路由。
- [Goal 模板](docs/wali-0x3/goal.md)：目标、AC 与阶段契约。
- [Spec 模板](docs/wali-0x3/spec.md)：Requirement 和测试判定依据。
- [Task 模板](docs/wali-0x3/todo.md)：依赖、范围与执行证据。
- [Issue 模板](docs/wali-0x3/issues.md)：发现、修复和独立复验。
- [Handoff 模板](docs/wali-0x3/handoff.md)：最新恢复快照。
- [只读项目看板](docs/wali-0x3/wali-board.html)：由本地启动器提供数据，每 1 秒展示 Goal、Task、Issue 与 Agent 状态。

## 19. 品牌关系

`wali-0x3` 是虚拟开发团队及其协作系统的名称。

`waliwali` 是面向使用者的统一虚拟形象，不对应某个具体 Agent。

> waliwali，由 wali-0x3 驱动的虚拟开发伙伴。
