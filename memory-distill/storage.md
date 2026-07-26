# Storage

定义 Experience 的存储结构和写入格式。

内容是否值得保存，按照 `memory-policy.md` 判断。

## Experience 库

根目录：

```text
E:/资料/内容仓库/Agents/experience/
```

目录结构：

```text
experience/
├── index.md
├── scan-state.json
└── memory/
    ├── agent-design.md
    └── software-engineering.md
```

`index.md` 用于定位 Experience Space，`memory/` 保存实际 Experience 内容。

## Experience Space

Experience Space 用于组织同一主题下的长期经验，不绑定具体项目、工具或 Agent。

### Space 归属

每条候选 Experience 都应根据核心主题独立判断所属 Space，判断标准是：未来需要这条 Experience 时，最可能从哪个主题下寻找？

写入前读取已有 Space 的名称和说明。只有其主题范围明确覆盖当前 Experience 时，才可以写入。当前使用、最近写入、唯一存在的 Space，以及 Experience 的来源项目，都不能作为默认归属依据。

同一批 Experience 也应逐条判断。没有合适 Space 时，可以根据稳定主题创建新的 Space；存在多个合理选择或无法确定时，由用户选择。无法确认归属时，暂不写入。

### 文件命名

文件名使用稳定、可读的 Space 名称，可以是英文名称使用小写下划线连接格式：

```text
{memory_space}.md
```

文件名只表示 Space 的主题，不使用项目名称、工具名称、日期或临时任务名称。分卷文件按照后续「分卷」规则命名。

### 分卷

一个 Space 可以包含多个分卷文件。分卷只用于控制单个文件的大小，不改变 Experience 所属的 Space。

第一卷使用 Space 名称作为文件名，后续分卷从 `02` 开始递增：

```text
{memory_space}.md
{memory_space}-02.md
{memory_space}-03.md
```

新增 Experience 前，如果最新分卷已经达到 300 行，则创建下一分卷。当前 Experience 不因写入后超过 300 行而被拆分或迁移。

新 Experience 写入最新分卷。更新已有 Experience 时，根据索引记录的文件路径修改原分卷。

### 文件头

每个分卷文件使用以下文件头：

```yaml
---
memory_space: agent-design
created_at: 2026-07-13
updated_at: 2026-07-13
---
```

字段说明：

- `memory_space`：Experience Space 的稳定名称，与文件名前缀保持一致。
- `created_at`：当前分卷的创建日期。
- `updated_at`：当前分卷最后一次发生内容变化的日期。

同一 Space 的所有分卷使用相同的 `memory_space`。新增、更新或替代 Experience 后，只更新实际发生变化的分卷文件。

Space 的主题范围统一记录在 `index.md` 中，不在每个分卷文件中重复维护。

## Experience 条目

Experience ID 在当前 Space 内递增，已使用的编号不再复用。创建新 Experience 时，使用当前 Space 中的最大编号加一。

条目格式：

```markdown
## MEM-0001｜标题

- type: decision
- status: active
- tags: skill, architecture
- sources:
  - conversation | source-id | 2026-07-13

正文按照 `memory-policy.md` 中的「Experience 表达」编写。
```

标题应直接表达经验的核心判断、做法或限制。

正文不使用固定模板，根据经验本身保留正确理解和复用所需的场景、结论、依据、条件或边界。没有必要时，不强制增加“适用范围”“原因”“结论”等小标题。

发生替代关系时，新 Experience 增加：

```text
- supersedes: MEM-0001
```

其他字段按照本节后续的字段规则填写。

## 字段规则

### type

`type` 必须使用 `memory-policy.md` 中定义的 Experience 类型，每条 Experience 只选择一个最能体现其主要价值的类型。

### status

`status` 只使用以下值：

- `active`：当前有效。
- `superseded`：已被新的 Experience 替代。

新建 Experience 默认使用 `active`。替代关系的判断和处理按照 `memory-policy.md` 执行。

### tags

使用 2～5 个具有长期检索价值的关键词，避免使用一次性项目名称或临时描述。

### sources

`sources` 用于记录能够直接支撑 Experience 结论的原始来源，便于后续追溯和核对。

格式：

```text
来源类型 | 来源标识 | 日期
```

例如：

```text
conversation | claude-code-session-001 | 2026-07-13
```

来源标识应使用真实且可以定位原始内容的信息，只记录与 Experience 结论直接相关的来源，不添加仅作为任务背景、但不能支撑结论的内容。

无法获取来源时：

```text
conversation | unavailable | 2026-07-13
```

不得猜测或自行生成来源标识。

## Experience 替代

只有已经确认的新结论明确推翻、取代或使旧 Experience 不再适用时，才执行替代。

如果核心结论没有变化，只是补充信息、修正表达或完善适用边界，应更新原 Experience，不创建新的替代记录。新旧结论的关系尚未确认时，暂不替代。

执行替代时：

- 新 Experience 增加 `supersedes: MEM-0001`
- 旧 Experience 的 `status` 修改为 `superseded`
- 旧 Experience 的正文和来源继续保留，不删除、不覆盖
- 新 Experience 应写清新的结论及其适用条件

替代只表示旧经验不再作为当前有效结论，不代表历史内容错误或没有价值。

## Index

`index.md` 用于快速定位 Experience Space 和单条 Experience，不保存正文和来源详情。

### Spaces

每个 Space 记录一行：

```text
memory_space｜description｜files
```

例如：

```TEXT
agent-design｜Agent、Skill 和经验系统的设计、使用与治理经验｜memory/agent-design*.md
```

### Experiences

每条 Experience 记录一行：

```text
experience_id | title | memory_space | type | status | tags | file
```

例如：

```text
MEM-0023｜poi-tl 的 Pictures.ofUrl 不会对 URL 二次编码｜software-engineering｜pattern｜active｜poi-tl, URL编码｜memory/software-engineering.md
```

新增 Experience 时增加索引记录。标题、类型、状态、标签或文件位置发生变化时，同步更新对应记录。正文内容变化但索引字段没有变化时，不需要修改索引。

## 写入规则

写入前，先确定 Experience 所属的 Space，读取该 Space 的全部文件，并按照 memory-policy.md 判断新增、更新、替代或跳过。

具体文件和分卷方式按照「Experience Space」章节执行。

写入时只修改必要内容，不删除历史 Experience，不修改无关 Space。写入完成后，确认内容保存正确，并且 index.md 仍能定位目标 Space。

## 删除与重建

已经删除的 Space、Experience 或索引记录，默认视为用户的明确处理结果，不得从历史会话、旧文件、缓存或其他来源自动恢复。

普通 Experience 沉淀只处理当前 Agent 已经获得的当前任务内容。除非用户明确要求，不得主动扫描历史会话，也不得借沉淀过程重建、补全或迁移整个经验库。

发现文件缺失、索引异常或历史内容被删除时，应停止相关操作并说明情况。只有用户明确要求恢复或重建后，才可以执行，并且恢复操作应与正常沉淀分开处理。