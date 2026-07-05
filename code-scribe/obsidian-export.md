# Obsidian Export Guide

将生成的 README 导出到 Obsidian 知识库。

本规范仅负责导出，不参与 README 内容生成。

---

# 导出路径

默认保存到：

```text
E:\资料\内容仓库\Contents\CodeScribe\
```

如用户指定其它路径，以用户要求为准。

---

# 文件命名

文件名格式：

```text
README-{单号}-{组件标识}-{版本}.md
```

命名信息直接使用 README 中已确认的信息，不重新分析源码。

降级策略：

| 场景 | 文件名示例 |
|------|-----------|
| 完整 | `README-JKN20260601_1176-PPACS-1.0.0049.md` |
| 无单号 | `README-PPACS-1.0.0049.md` |
| 无版本 | `README-JKN20260601_1176-PPACS.md` |
| 无单号和版本 | `README-PPACS-YYYYMMDD.md` |

默认覆盖同名文件；只有用户明确要求保留历史版本时，才生成新文件。

---

# Frontmatter

导出文档统一添加：

```yaml
---
项目: PPACS_1.0.0049  
日期: YYYY-MM-DD  
类型: README  
tags:
  - 项目文档
  - README
  - CodeScribe
---
```

---

# 导出要求

仅允许新增：

- Frontmatter
- 文件名
- 保存路径

除此之外，保持 README 正文完全一致：

- 不修改内容
- 不调整结构
- 不重新排版
- 不补充说明
- 不删除内容

保留 Markdown 原有格式，包括标题、表格、代码块、ASCII 流程图、Mermaid（如有）和图片引用。

不要自动生成 Wiki Link（`[[...]]`）或修改图片引用。

---

# 最终原则

导出属于格式转换，不属于内容生成。

除 Frontmatter、文件命名和保存位置外，不修改 README 的任何正文内容。