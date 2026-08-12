---
paths:
  - "**/test*/**"
  - "**/*test*.*"
  - "**/*spec*.*"
---

# Testing

- Acceptance Criterion 的 `Method` 是测试 oracle；发现歧义时返回 `define`，不要临时发明通过条件。
- Spec 的 Verification Mapping 把 AC 编译为测试层级、关键场景和可执行步骤；Developer 和 Tester 通过该接口工作。
- Developer 自检后只把 Task 设为 `review`；独立验证发生在 `verify`。
- `verify` 中默认不修改实现或测试。需要修复时记录 Issue 并返回 `work`；若用户确认例外写入，本轮验证立即失效，必须返回 `work` 后重新进行独立验证。
- 测试记录包含命令、退出码、结果、环境限制和未覆盖范围。
- 修复后既复现原失败，也检查邻近行为没有回归。
- WorkIndex 的依赖、frontier、并行和检查点通过公开 CLI 测试，不测试私有实现细节。
