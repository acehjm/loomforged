# 项目参考资料约定

`refs/` 保存项目特有、需要按任务选择性读取的详细资料。它不是第六份 WALI 状态文件，不记录当前进度，也不自动覆盖 Goal、Spec、Rules 或阶段权限。

## 1. 什么放在哪里

| 内容 | 放置位置 | 原因 |
| --- | --- | --- |
| 所有会话都必须知道的稳定事实 | `CLAUDE.md` | 作为项目入口始终加载 |
| 必须遵守、可以写成“必须/禁止”的约束 | `rules/` | 规范性约束，可按路径限定适用范围 |
| 模板正文、推荐方法、详细 API 说明、兼容矩阵、示例和设计背景 | `refs/` | 信息量大、只在相关任务中按需读取 |
| 可重复的多步骤操作流程 | `skills/` | 提供方法和步骤，不提供额外权限 |
| 当前 Goal 选择了哪些约束、版本和资料 | `spec.md` | 将本次开发与测试依据纳入联合确认摘要 |

判断标准：

- 不遵守就应阻止合并或交付的内容，写入 `rules/`。
- 用于解释、套用或查阅，但允许因 Goal 或代码现状调整的内容，写入 `refs/`。
- “必须使用某模板/版本”本身写入 Rule；模板全文、依赖兼容表和选择理由放入 Ref，由 Rule 引用。
- 只对一次 Goal 有效的选择不要提升为全局 Rule，写入 `spec.md`。

## 2. 当前内置参考

| Ref | 内容 | 何时读取 |
| --- | --- | --- |
| `REF-WALI-OPS-001` / `operations.md` | 阶段转换、工作图、Agent 恢复、SVN 交付和命令索引 | 转段、恢复、交付或查询非常用命令时 |
| `REF-WALI-COMPAT-001` / `compatibility.md` | Claude Code 功能要求、降级方式、`wali_schema` 与部署核对 | 首次部署、升级 Claude Code 或兼容检查时 |

这些文件不通过 `@import` 加入 `CLAUDE.md`，只在相关任务中按需读取。项目可以继续在 `refs/` 中平铺模板、合规基线和接口资料；是否使用由 Spec/Task 的稳定引用决定，而不是由文件存在自动触发。

## 3. 推荐分类

按项目需要建立子目录，不为凑结构创建空目录：

```text
refs/
├── INDEX.md
├── templates/       # 代码、接口、配置或文档模板
├── integrations/    # 外部系统接口、协议和错误语义
├── architecture/    # 模块说明、决策背景和已批准范例
└── compatibility/   # 依赖、运行时、平台和迁移兼容矩阵
```

每份资料应在开头记录：

```yaml
---
ref_id: REF-XXX
title: 简短且稳定的标题
kind: template | integration | architecture | compatibility | example
applies_to:
  - path/or/component
source: 用户提供文档、权威 URL 或项目事实
version: 适用版本
last_verified: YYYY-MM-DD
owner: 维护者或团队
---
```

正文至少说明适用场景、不适用场景、关键内容、与哪些 Rule/Spec 条款关联，以及如何验证资料仍然有效。不得保存秘密、令牌、个人数据或无法追溯来源的复制内容。

## 4. Agent 使用方式

Coordinator 在澄清阶段识别适用的 Rules 和 Refs，只把与当前 Goal 有关的条目标识、版本和选择结果写入 `spec.md`。Developer、Reviewer 和 Tester 只读取任务关联部分，不应一次性加载整个目录。

优先级与冲突处理：

```text
阶段策略和用户已确认的 Goal + Spec
→ 适用 Rules
→ Spec 明确引用且版本匹配的 Refs
→ Skill 中的默认方法和示例
```

这不是允许 Agent 在冲突时自行挑选。任何上层契约与 Rule 冲突、Ref 已过期、版本不匹配或资料与真实代码不一致，都必须停止相关动作并交给 Coordinator 澄清。Ref 中的示例不能直接当成已授权实现，也不能扩大 `write_scope`。

## 5. 维护边界

`refs/`、`rules/`、`skills/` 和 Agent 定义都属于 WALI 控制面。部署到具体项目时由项目维护者配置；运行中的普通开发任务不得顺手修改。需要调整这些内容时，应作为独立的控制面变更审查、验证并重新建立受影响 Goal 的确认摘要。
