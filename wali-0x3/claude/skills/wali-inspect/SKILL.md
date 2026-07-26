---
name: wali-inspect
description: 将已自检的活动任务转入 inspecting，沿 WALI 工作图完成独立审查、测试、问题闭环和验收证据映射。
disable-model-invocation: true
---

检查当前阶段，范围补充为：`$ARGUMENTS`

1. 确认 Goal 已经用户确认、当前 phase 为 `implementing` 或 `inspecting`、`active_task` 有效，且任务已完成实现者自检并处于 `review`。
2. 从 `implementing` 进入前，运行 `wali_policy.py carry`，原子采用其完整输出：`carry_epoch` 恰好递增，上一代 `carried_changes` 只追加进 `carried_history`，当前合法实现差异成为新一代 `carried_changes`。再将阶段契约转为 `inspecting`：保留 `active_task`，将任务设为 `review`，关闭新产物和实现修改，只允许读取、提问、更新 Goal 阶段字段/`todo.md`/`issues.md`/`handoff.md` 以及运行 Goal 已声明的检查命令。后续差异与当前代指纹不一致时立即退回处理；修复完成后生成下一代，不覆盖旧代。
3. 从 `spec.md` 确定关联 Requirement、规范性 AC 判定规则、适用 Rules/Refs、待审任务、SVN 基准和实际差异。实现者不能成为唯一检查者。
4. 若使用 Agent Teams，共享任务标题必须包含且只能包含当前稳定 Task ID，例如 `[T-001] 独立审查支付校验`。`TaskCompleted` 只是一次运行完成事件：它要求 Task 已有证据并至少进入 `review`，不能代替独立验证或直接把 Task 设为 `done`。
5. 若审查与测试可独立进行，分别委派新的 Reviewer 和 Tester 上下文；若依赖或文件范围不允许并行，顺序执行但保持独立判断。
6. Reviewer 检查 Goal 符合性、范围、安全、兼容性、工程质量、错误处理、测试遗漏和适用 Rule。任务声明审查 Skill 时，只在它已获 Goal 授权且定义可检查时调用；合规 Skill 必须使用 Spec 指定的标准、版本和范围。
7. Tester 依据 Spec 的判定规则将 AC 转为正常、失败、边界和回归场景，只运行 `goal.md` 已明确声明的真实命令。
8. 所有可操作发现都写入 `issues.md`，重复发现合并并补充证据。`inspecting` 中不直接修实现；需要修复时，先将问题分配给 Developer，并转回 `implementing`。
9. 修复完成后问题进入 `verify`，再转回 `inspecting` 由 Reviewer 或 Tester 复验；修复者不能自行设为 `closed`。
10. 只有关联问题关闭、任务证据充分且独立检查通过时，才将任务转为 `done`。运行工作图和 SVN 差异审计。
11. 如果仍有可执行任务，选定下一个前沿任务并转入 `implementing`；如果所有 automatic AC 都有证据，转入 `accepting`、清空 `active_task`，设置 `waiting_for: acceptance` 和具体回测要求。若需要用户选择实现方向而非回测，使用 `awaiting_direction`。

输出逐项 Requirement → AC → Task → Evidence 映射、Reviewer 与 Tester 的独立结论、命令与结果、SVN 范围检查、未关闭问题、剩余风险和唯一的下一个阶段。
