---
paths:
  - "**/*"
---

# Engineering

- 保护调用前已有或来源不明的用户修改，不回退、不覆盖、不擅自提交。
- 实现写入的默认路径是 `phase: work` 且落在 active Task 的 `Scope`；确有必要的例外说明原因并请求当场确认。
- 先理解现有接口、约定和测试，再按 implementation-ready Spec 做满足 Goal 的最小完整修改。
- 不加入当前 Goal/Spec 没有证明需要的抽象、兼容层或额外产物。
- 不删除、跳过或弱化测试，不吞掉错误，不伪造 Evidence。
- 外部写入在实际执行时获得用户确认，不要求预先修改 Goal 授权。
- `goal.md`、`spec.md` 和 `work.md` 是唯一常驻治理状态；普通任务不创建图、第二份 Spec、Todo、Issue 或进度副本。
- 可发现的问题先自行查证；`May decide` 内自主选择并继续，只有 `Must ask` 且穷尽安全查证后才打断用户。
