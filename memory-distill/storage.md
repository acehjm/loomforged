# Storage

定义 Experience 的存储位置、组织方式和内容格式。

Experience 的价值判断按照 `memory-policy.md` 执行。

## Experience 库

根目录：

```text
E:\资料\内容仓库\Agents\experience\
```

目录结构：

```text
experience/
├── index.md
└── memory/
    ├── agent-design.md
    ├── requirement-analysis.md
    └── software-engineering.md
```

规则：

- `index.md` 用于定位 Experience Space。
- `memory/` 保存实际 Experience 内容。
- 不保存完整对话记录。

## Experience Space

Experience Space 用于组织同一主题下的长期经验，不绑定具体项目、工具或 Agent。

文件命名：

```text
{memory_space}.md
```

示例：

```text
agent-design.md
requirement-analysis.md
```

文件头：

```yaml
---
memory_space: agent-design
name: Agent Design
description: Agent、Skill、Memory 相关经验
created_at: 2026-07-13
updated_at: 2026-07-13
---
```

字段：

- `memory_space`：稳定标识。
- `name`：展示名称。
- `description`：经验范围说明。
- `created_at`：创建时间。
- `updated_at`：更新时间。

## Experience 条目

每条 Experience 使用递增 ID：

```text
M-0001
M-0002
```

格式：

```markdown
## M-0001｜标题

- type: decision
- status: active
- tags: skill, architecture
- sources:
  - conversation | source-id | 2026-07-13

核心内容。

适用范围：说明成立条件和限制。
```

## 字段规则

### type

必须使用以下类型之一：

- `decision`：已确认的设计决策或方案取舍。
- `preference`：长期稳定的工作偏好。
- `issue-solution`：经过验证的问题解决方式。
- `pattern`：可复用的方法或处理模式。
- `constraint`：长期有效的环境、平台或业务限制。

### status

仅允许：

- `active`：当前有效。
- `superseded`：已被新 Memory 替代。

### tags

使用 2～5 个具有长期检索价值的关键词。

避免使用一次性项目名称或临时描述。

### sources

记录 Experience 来源。

格式：

```text
来源类型 | 来源标识 | 日期
```

例如：

```text
conversation | claude-code-session-001 | 2026-07-13
project | JKN20260101 | 2026-07-13
document | requirement-design.md | 2026-07-13
```

无法获取来源时：

```text
unavailable
```

不得伪造来源。

## Experience 替代

新 Experience 替代旧 Experience 时：

新 Experience 增加：

```text
- supersedes: M-0001
```

旧 Experience 修改：

```text
- status: superseded
```

旧 Experience 保留，不直接删除。

## Index

`index.md` 用于定位 Experience Space，不记录单条 Experience。

格式：

```markdown
# Experience Index

- agent-design｜Agent、Skill、Memory 相关经验｜memory/agent-design.md
- requirement-analysis｜需求分析和方案设计经验｜memory/requirement-analysis.md
```

## 写入规则

写入前：

1. 读取目标 Experience Space 最新内容。
2. 检查已有相关 Experience。
3. 按 `memory-policy.md` 决定新增、更新、替代或跳过。

写入时：

- 只修改目标 Experience Space 和必要索引。
- 保留已有有效内容。
- 不删除历史 Experience。
- 不修改无关内容。