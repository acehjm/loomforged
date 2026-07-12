# Storage

定义全局记忆库的位置、逻辑工作空间识别方式、标识与文件格式，以及安全写入规则。

## 全局记忆目录

配置全局记忆根目录：

```text
GLOBAL_MEMORY_ROOT: E:\资料\内容仓库\Agents\global-memory\
```

根据根目录确定：

```text
索引文件：{GLOBAL_MEMORY_ROOT}/index.md
记忆目录：{GLOBAL_MEMORY_ROOT}/memory/
```

只配置全局记忆根目录，不单独配置索引文件和记忆目录。

如果根目录不存在或无法访问，停止执行并提示用户检查配置，不得在其他位置创建记忆库。

全局记忆库使用以下结构：

```text
global-memory/
├── index.md
└── memory/
    ├── 文旅安防知识库--39bc7a.md
    ├── code-scribe--42af81.md
    └── 高校安防知识库--a72f30.md
```

一个逻辑工作空间对应一个 Markdown 文件。

不得默认按照会话、日期、年份、记忆类型或来源工具创建子目录。

### 初始化

根目录存在时：

* `memory/` 不存在，可以创建
* `index.md` 不存在且 `memory/` 为空，可以初始化
* `index.md` 不存在但 `memory/` 已有文件，停止写入并报告
* `index.md` 格式无法识别，停止写入并报告
* 已有文件不得直接覆盖

初始化后的 `index.md`：

```markdown
# Global Memory Index

## Workspaces

## Memories
```

本规则不负责修复或重建损坏、缺失的已有索引。

## 逻辑工作空间

逻辑工作空间表示一个实际项目、长期主题或独立工作领域。

工具工作空间、项目目录和会话只是定位信息。同一个实际项目即使出现在不同工具、目录或会话中，也应映射到同一个逻辑工作空间。

### Locator

Locator 用于定位逻辑工作空间，支持：

```text
path:{tool}:{项目根目录}
workspace:{tool}:{工具工作空间ID或稳定名称}
```

例如：

```text
path:claude-code:E:\skills\field-notes
workspace:craft-agents:field-notes-development
```

路径使用当前操作系统的原生格式，并指向项目根目录。

一个逻辑工作空间可以登记多个 Locator，但同一个 Locator 不得属于多个工作空间。

### 识别顺序

按照以下顺序识别当前逻辑工作空间：

1. 用户明确指定的 `workspace_id`
2. 工具工作空间 Locator 完全匹配
3. 项目根目录 Locator 完全匹配
4. 项目名称与已有工作空间名称或别名唯一匹配

名称和别名只能用于唯一匹配，不得根据模糊相似名称自动选择。

### 创建工作空间

没有准确匹配结果时，只有能够确认当前项目不是已有工作空间的迁移、改名或新工具入口，才可以创建新的逻辑工作空间。

存在疑似匹配时，停止写入并列出候选工作空间，由用户指定 `workspace_id`。

不得因为路径变化或工具变化创建重复工作空间。

## 标识与文件命名

### Workspace ID

格式：

```text
ws-{6位小写十六进制字符}
```

例如：

```text
ws-39bc7a
```

创建时必须保证唯一。

创建后，不得因为工作空间名称、项目路径或使用工具发生变化而修改。

### Memory ID

格式：

```text
MEM-{WORKSPACE短ID大写}-{至少4位递增序号}
```

例如：

```text
MEM-39BC7A-0001
MEM-39BC7A-0002
MEM-39BC7A-10000
```

生成方式：

1. 从当前 `workspace_id` 提取短标识并转为大写
2. 查找当前工作空间已有记忆的最大序号
3. 使用最大序号加一
4. 序号不足四位时在左侧补零
5. 不复用已经使用过的序号

只需检查当前工作空间文件，不扫描其他工作空间。

### 记忆文件命名

格式：

```text
{可读工作空间名称}--{workspace_id短标识}.md
```

例如：

```text
field-notes--39bc7a.md
code-scribe--42af81.md
高校安防知识库--a72f30.md
```

文件名中的名称用于阅读，短标识来自 `workspace_id`。

工作空间改名时，不要求自动修改已有文件名。

## 文件格式

### 工作空间记忆文件

工作空间记忆文件使用以下文件头：

```yaml
---
workspace_id: ws-39bc7a
workspace_name: field-notes
aliases:
  - Field Notes
  - field-notes-skill
locators:
  - 'path:claude-code:E:\skills\field-notes'
  - 'workspace:craft-agents:field-notes-development'
created_at: 2026-07-12
updated_at: 2026-07-12
---
```

`workspace_id` 创建后保持不变。

会话来源保存在具体记忆条目中，不写入文件头。

新增 Locator 时：

* 保留已有 Locator
* 不重复添加
* 确认未被其他工作空间使用

### 记忆条目

记忆条目使用以下格式：

```markdown
## MEM-39BC7A-0001｜平台导出规则应与正文生成解耦

- type: decision
- status: active
- tags: skill, export, obsidian
- sources:
  - claude-code | session_id=2f81a7 | 2026-07-12

内容生成类 Skill 默认只负责正文生成；只有用户明确要求导出时，才加载对应的平台导出规则，避免导出要求干扰正文结构。

适用边界：适用于包含可选导出能力的内容生成类 Skill。不同 Agent 的规则加载机制需要在对应环境中单独验证。
```

字段要求：

* `type` 使用 `memory-update.md` 定义的记忆类型
* `status` 只使用 `active` 或 `superseded`
* `tags` 使用 2～5 个有检索价值的关键词
* `sources` 至少保留一个真实来源
* 正文直接表达结论
* `适用边界` 说明成立条件和必要限制

来源格式：

```text
{tool} | session_id={真实会话ID或unavailable} | {YYYY-MM-DD}
```

例如：

```text
claude-code | session_id=2f81a7 | 2026-07-12
craft-agents | session_id=unavailable | 2026-07-12
```

无法获取真实会话 ID 时使用 `unavailable`，不得自行生成或猜测。

替代旧记忆时，新记忆增加：

```text
- supersedes: MEM-39BC7A-0001
```

被替代的旧记忆保留原有正文和来源，并将：

```text
- status: active
```

修改为：

```text
- status: superseded
```

没有替代关系时，不写 `supersedes`。

## 全局索引

`index.md` 只保存定位和检索所需的元数据，不复制记忆正文和来源详情。

工作空间记忆文件是内容来源，全局索引是检索入口。

名称、别名和 Locator 中不得使用字段分隔符 `｜`。

### 工作空间索引

每个工作空间使用一行：

```markdown
- `ws-39bc7a`｜field-notes｜`memory/field-notes--39bc7a.md`｜Field Notes, field-notes-skill｜path:claude-code:E:\skills\field-notes, workspace:craft-agents:field-notes-development
```

字段顺序：

```text
workspace_id｜workspace_name｜file｜aliases｜locators
```

没有别名或 Locator 时保留空字段，不改变字段顺序。

### 记忆索引

每条记忆使用一行：

```markdown
- `MEM-39BC7A-0001`｜平台导出规则应与正文生成解耦｜`ws-39bc7a`｜decision｜active｜skill, export, obsidian｜`memory/field-notes--39bc7a.md`
```

字段顺序：

```text
memory_id｜title｜workspace_id｜type｜status｜tags｜file
```

记忆被新结论替代后，将索引中的状态同步更新为 `superseded`。

## 写入规则

修改前读取目标记忆文件和 `index.md` 的最新内容，不得使用旧内容覆盖新的变化。

写入顺序：

```text
更新工作空间记忆文件
        ↓
确认记忆文件写入成功
        ↓
更新 index.md
```

如果记忆文件写入失败，不得修改索引。

如果记忆文件写入成功但索引更新失败：

* 保留已经写入的记忆
* 明确报告索引更新失败
* 不得删除记忆正文掩盖错误

写入完成后，确认：

* 记忆正文已经成功写入
* 索引能够定位对应工作空间和记忆
* workspace_id、memory_id、状态和文件位置保持一致
