---
name: wali-inspect
description: 对当前 WALI 阶段执行独立 Reviewer 与 Tester 检查，汇总发现、更新问题状态并建立验收证据。
disable-model-invocation: true
---

检查当前阶段，范围补充为：`$ARGUMENTS`

1. 确定目标、关联验收条件、待审任务、变更基准和实际 diff。
2. 若审查与测试可以独立进行，分别委派新的 `reviewer` 和 `tester` 上下文；若工具或任务依赖不允许并行，则顺序执行但保持独立上下文。实现者不能成为唯一检查者。
3. Reviewer 检查目标符合性、范围、安全、兼容性、工程质量、错误处理和测试遗漏。
4. Tester 将验收条件转为正常、失败、边界和回归场景，运行真实可用的最小相关检查并按风险扩展。
5. 把所有可操作发现写入 `issues.md`，不得只留在子 Agent 返回消息中。重复发现合并到同一问题并补充证据。
6. 修复者完成后，将问题设为 `verify` 并交回 Reviewer 或 Tester；未经复验不得 `closed`。
7. 只有关联问题关闭且证据充分时，才能建议任务从 `review` 转为 `done`。
8. 输出逐项验收映射、两类独立结论、命令和结果、未关闭问题、剩余风险及用户待验收项。

本技能负责 Inspect，不直接代替 Developer 修复实现。
