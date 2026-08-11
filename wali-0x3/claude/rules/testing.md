---
paths:
  - "**/test*/**"
  - "**/*test*.*"
  - "**/*spec*.*"
---

# Testing

- Acceptance Criterion 的 `Method` 是测试 oracle；发现歧义时返回 `define`，不要临时发明通过条件。
- Developer 自检后只把 Task 设为 `review`；独立验证发生在 `verify`。
- `verify` 中不修改实现或测试。需要修复时记录 Issue 并返回 `work`。
- 测试记录包含命令、退出码、结果、环境限制和未覆盖范围。
- 修复后既复现原失败，也检查邻近行为没有回归。
- WorkIndex 的依赖、frontier、并行和检查点通过公开 CLI 测试，不测试私有实现细节。
