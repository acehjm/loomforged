---
paths:
  - "**/*"
---

# Engineering

- 保护调用前已有或来源不明的用户修改，不回退、不覆盖、不擅自提交。
- 实现写入的默认路径是 `phase: work` 且落在 active Task 的 `Scope`；确有必要的例外说明原因并请求当场确认。
- 最多两个实现 Agent 并发；每个 Agent 只写其 `agent_id + agent_type` 认领的 Task Scope。共享配置、lockfile、路由总表、生成代码和数据库迁移归一个 Task，或拆为串行 integration Task。
- Subagent 的认领、Scope、控制面和 SVN 调度越界是硬边界；被拒绝后返回 Wali，不通过反复请求权限绕过。异常 claim 只在所有实现 Agent 停止后清理。
- 先理解现有接口、约定和测试，再按 implementation-ready Spec 做满足 Goal 的最小完整修改。
- 不加入当前 Goal/Spec 没有证明需要的抽象、兼容层或额外产物。
- 不删除、跳过或弱化测试，不吞掉错误，不伪造 Evidence。
- 外部写入在实际执行时获得用户确认，不要求预先修改 Goal 授权。
- Goal/Spec/Work/Handoff 只由 Wali 写入。实现 Agent 只返回结构化结果且不执行任何 SVN 工作副本或远端调度，由 Wali 核对并串行处理。
- `goal.md`、`spec.md` 和 `work.md` 是唯一常驻治理状态；普通任务不创建图、第二份 Spec、Todo、Issue 或进度副本。
- Define 期间先在对话中综合 Goal+Spec；除非用户要求保存草案或真实 handoff，确认前不把推测或中间结果逐步写入治理文件。
- 可发现的问题先自行查证；`May decide` 内自主选择并继续，只有 `Must ask` 且穷尽安全查证后才打断用户。
