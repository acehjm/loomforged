---
paths:
  - "**/test*/**"
  - "**/*test*.*"
  - "**/*spec*.*"
---

# Testing

- Acceptance Criterion 的 `Method` 是测试 oracle；发现歧义时返回 `define`，不要临时发明通过条件。
- Spec 用 Behavior Scenarios 把 Given/When/Then 直接映射到 AC，Verification Mapping 再把 AC 编译为可定位 Seam、测试层级、关键场景和可执行步骤；`backend`、`frontend` 和 `verify` 通过该接口工作。
- 优先使用现有、能看到最完整用户行为的最高测试 Seam。Agent 自主选择现有 Seam；只有必须新建会改变公开行为或引入高代价接口的 Seam 时才按 `Must ask` 询问用户。
- 实现 Agent 自检后返回 Evidence，由 Wali 把 Task 设为 `review`；独立验证发生在 `verify`。
- `verify` 中默认不修改实现或测试。需要修复时记录 Issue 并返回 `work`；若用户确认例外写入，本轮验证立即失效，必须返回 `work` 后重新进行独立验证。
- `review`/`verify` 不写 Work，只返回按 Task 分组的结构化发现和 Evidence，由 Wali 批量落盘。
- 测试记录包含命令、退出码、结果、环境限制和未覆盖范围。
- 修复后既复现原失败，也检查邻近行为没有回归。
- WorkIndex 的依赖、frontier、并行和检查点通过公开 CLI 测试，不测试私有实现细节。
