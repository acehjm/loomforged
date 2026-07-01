# Obsidian Export Guide

生成 README 后，同步导出到 Obsidian 知识库。

## 导出流程

完成 README 后：

1. 将 README 转换为符合 Obsidian 规范的 Markdown。
2. 保存到：

```text
E:\资料\内容仓库\Contents\Working\
```

---

## 文件命名

文件名格式：

```text
README-{单号}-{组件标识}-{版本}.md
```

### 信息提取优先级

- **单号**：优先从项目目录名称提取。
- **组件标识**：优先使用项目名称，其次使用 artifactId、package 名称、目录名称。
- **版本**：优先从 pom.xml、package.json、项目配置文件、版本常量提取。

---

## 降级策略

如果无法提取全部信息，应至少保留两个维度。

| 场景 | 文件名示例 |
|------|-----------|
| 完整 | `README-JKN20260601_1176-PPACS-1.0.0049.md` |
| 无单号 | `README-PPACS-1.0.0049.md` |
| 无版本 | `README-JKN20260601_1176-PPACS.md` |
| 无单号和版本 | `README-PPACS-YYYYMMDD.md` |

---

## Frontmatter

导出的文档开头统一生成：

```yaml
---
project: PPACS_1.0.0049
date: YYYY-MM-DD
type: README
tags: [项目文档, README]
---
```

`date` 使用生成当天日期。无法获取版本时，project 字段仅使用组件标识。

---

## 导出要求

- 保持 README 内容不变
- 不调整章节结构
- 不修改业务内容
- 仅进行 Obsidian Markdown 格式转换
- 导出文件可直接放入 Obsidian Vault 使用
