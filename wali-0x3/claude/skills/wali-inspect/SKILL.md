---
name: wali-inspect
description: 在 verify 阶段独立审查、测试并把证据写回 work.md。
disable-model-invocation: true
---

1. Developer 完成自检后，把 active Task 设为 `review` 并记录实现与命令 Evidence。
2. 运行 `wali_work.py check --checkpoint verify`，通过后将 Work phase 改为 `verify`。
3. Reviewer 和 Tester 读取 Goal、Work、真实差异、相关代码与测试。实现者不能成为唯一 Verifier。
4. Reviewer 报告范围、正确性、安全、兼容性、复杂度和测试遗漏；Tester 按 AC 的 Method 验证正常、失败和边界行为。
5. 发现写入 `work.md` 的 Issues；需要修复时将 phase 返回 `work`，只让 active Task Scope 获得实现写入。
6. 独立验证通过后，将 Task 设为 `done`，填写 Evidence 和独立 Verifier；同步更新 Acceptance 状态和证据。
7. 仍有任务时使用 `frontier` 选择下一项。全部完成并获得用户验收后运行 `wali_work.py check --checkpoint done`，再将 phase 设为 `done`、active_task 设为 `none`、outcome 设为 `completed`。

输出 Requirement → AC → Task → Evidence 映射、命令结果、未关闭问题、风险和下一步。普通 Inspect 不创建 handoff。
