---
name: wali-inspect
description: 在 verify 阶段独立审查和测试，由 Coordinator 批量写回证据。
disable-model-invocation: true
---

1. 实现 Agent 返回结果后，Coordinator 核对真实差异，在一个编辑回合把一至两个 active Task 设为 `review` 并记录实现与命令 Evidence。
2. 运行 `wali_work.py check --checkpoint verify`，通过后将 Work phase 改为 `verify`。
3. Reviewer 和 Tester 读取 Goal、Spec、Work、真实差异、相关代码与测试。实现者不能成为唯一 Verifier。
4. Reviewer 报告范围、正确性、安全、兼容性、复杂度和测试遗漏；Tester 按 AC 的 Method 验证正常、失败和边界行为。
5. Reviewer/Tester 只返回结构化发现、验证 Evidence 和建议状态，不修改治理文件。Coordinator 在两者结束后一次写入 Issues、Verifier 与 Acceptance。
6. 需要修复时将 phase 返回 `work`；独立验证通过后，Coordinator 将 Task 设为 `done`，填写 Evidence 和独立 Verifier，同步更新 Acceptance。
7. 仍有任务时使用 `frontier` 自动选择下一项。全部 AC 由 Verification Mapping 的证据满足后，先在同一编辑回合将 phase 设为 `done`、active_task 设为 `none`、outcome 设为 `completed`，再立即运行 `wali_work.py check --checkpoint done`；检查失败时保持会话并修复终态，不得对用户宣称完成。只有 AC 明确要求主观验收时才询问用户。

输出 Requirement → AC → Task → Evidence 映射、命令结果、未关闭问题、风险和下一步。普通 Inspect 不创建 handoff。
