# 跨项目参考索引

`refs/` 保存跨项目稳定、按场景读取的资料。它不记录当前进度，不扩大 Goal 或 Task Scope，也不能替代外部写入的当场确认。

| Ref | 路径 | 内容 | 读取时机 |
| --- | --- | --- | --- |
| WALI Operations | `operations.md` | 阶段、恢复、交接和 SVN 操作 | 转段、恢复或交付时 |
| WALI Compatibility | `compatibility.md` | Claude Code 能力和部署核对 | 部署或排障时 |
| Templates | `templates/INDEX.md` | 跨项目开发模板 | 当前 Task 场景匹配时 |
| Compliance | `compliance/INDEX.md` | 代码检查基线 | Developer 自检或 Reviewer 审查时 |

用户为具体项目提供的原始资料保留在项目自己的 `docs/`；采用的目标结论写入 `goal.md`，由代码事实支撑的实现契约写入 `spec.md`，运行状态、问题和证据写入 `work.md`。

Agent 只加载与当前角色和任务直接相关的最小 Ref。Ref 是参考，不是 Skill，不需要形成额外 Work 关系。
