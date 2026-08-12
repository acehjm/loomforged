---
agent: wali-0x3
goal_id: pending
status: draft
---

# Implementation-Ready Spec

> `spec.md` 把已确认 Goal 编译为 Backend/Frontend Dev 可以连续执行的稳定实现契约。当前 `draft` 文件只是格式种子；普通 Define 的候选 Spec 留在对话与上下文中，Goal+Spec 经用户明确确认后才与 Work 一次性持久化。进入 work 后 Spec 不记录进度；只有不影响 Goal、用户可观察行为或 AC，且未触发 `Must ask` 的代码事实偏差，才在检查点批量修正。Goal、用户可观察行为或 AC 实质变化必须返回 define 并重新确认。

以下二级标题、表头和 Autonomous Decision Contract 的四个英文标签是检查器接口，保留原样；正文可使用项目语言。

## Current System

- Entry points: 待检查相关入口、模块、接口与配置。
- Existing behavior: 待用代码和测试说明当前真实行为。
- Constraints: 待记录必须保持的兼容性、平台和项目约定。
- Evidence: 待列出支持上述判断的文件、测试或命令结果。

## Target Behavior

- Normal flow: 待写用户可观察的正常流程。
- Errors and edges: 待写错误处理、边界输入、并发或恢复行为。
- Compatibility: 待写必须保持及允许改变的行为。
- Non-goals: 待写明确不实现的相邻需求。

## Behavior Scenarios

| Scenario | Given | When | Then | Acceptance |
| --- | --- | --- | --- | --- |

用简短、可观察的 Given/When/Then 编译行为。每个 `AC-XXX` 至少由一个场景覆盖；正常、错误、边界和兼容场景按实际风险填写，不为凑数量重复 Target Behavior。

## Design Mapping

| ID | Requirement | Design | Affected Areas |
| --- | --- | --- | --- |

每个 `R-XXX` 至少由一个 `D-XXX` 覆盖。Design 说明接口、数据流、状态变化和关键失败处理；Affected Areas 使用精确项目相对路径，并必须由关联 AC 的 Task Scope 覆盖。只有存在高代价选择时，才在 Design 中记录采用方案、理由、替代方案和回滚考虑。

## Verification Mapping

| Acceptance | Seam | Coverage | Method |
| --- | --- | --- | --- |

每个 `AC-XXX` 至少有一行并保留 Goal 中的 AC Method oracle。Seam 指向现有的、能看到最完整用户行为的最高测试接缝，并用路径、命令或接口定位。Coverage 说明测试层级与关键 Behavior Scenario；Method 给出可执行命令或可复现步骤，不只写“测试通过”。每个 AC 还必须至少关联一个 Work Task。

## Autonomous Decision Contract

- May decide: 可逆、低影响并遵循现有接口、测试和项目约定的实现细节；局部命名、函数拆分、内部数据结构、错误信息措辞、测试组织和不改变外部行为的重构。
- Must ask: 用户可见语义或 Scope 实质变化；Acceptance 冲突；不可逆数据迁移；重大安全、合规或费用风险；新增无法安全回滚的外部副作用；多个高代价方案没有代码事实可判优。
- Must not: 扩大业务目标、弱化或删除测试、覆盖来源不明的用户修改、伪造 Evidence、把未验证假设写成既定事实，或为省事绕开 Goal 与 Spec。
- If blocked: 先检查代码、测试、配置、历史和适用文档，尝试安全可逆的验证；仍阻塞时只提出一个会改变结果的问题，并携带证据、选项、建议和默认方案。

## Open Questions

- 待列出会阻止实现或改变结果的问题；`implementation-ready` 前必须解决并改为 `none`。
