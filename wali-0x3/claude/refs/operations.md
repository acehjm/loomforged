---
ref_id: REF-WALI-OPS-001
title: WALI 运行与恢复参考
kind: architecture
applies_to:
  - docs/wali-0x3/**
  - .claude/hooks/**
source: wali-0x3 Policy、Graph、Stop 与监督 Hook
version: "1"
last_verified: 2026-07-26
owner: WALI 控制面维护者
---

# WALI 运行与恢复参考

本文解释阶段转换、Agent 恢复、SVN 交付和维护命令。它按需读取，不是阶段授权来源；实际权限以 `goal.md` 当前契约和 Hook 判定为准。

## 1. Goal 与 Spec 收敛

模糊或缺失需求由 `/wali-start` 进行开放式访谈；已有接口文档、需求或规格时进行缺失、歧义、冲突、代码一致性和可测试性压力测试。用户资料保留在具体项目的 `docs/`，其路径、版本、适用范围和采用结论写入固定的 `spec.md`；不得复制到 `.claude/refs/`。必要时两种收敛方式混合，最后与 Goal 一次联合确认。

确认包至少包含目标、背景、范围、非范围、约束、Requirement、行为与接口/数据/错误契约、验收判定规则、检查方式、决策、风险和第一个可验证增量。沉默和 Agent 自行概括不是确认。Spec 或 Goal 稳定定义变化后，清空确认与 `goal_definition_digest`，返回 `clarifying`。

## 2. 阶段转换

主路径：

```text
clarifying
→ planning
→ implementing
→ inspecting
→ accepting
→ closed（无需提交）
   或 delivering（精确 SVN 提交后的冻结终态）
```

修复从 `inspecting` 返回 `implementing`，运行 `carry` 建立下一代差异后再检查。方向问题进入 `awaiting_direction`；无法安全绕过的真实阻断进入 `blocked`。任何未关闭阶段都可在有证据时终止为 `terminated`。

`handoff` 是会话暂停，`blocked` 是 Goal 阻断，两者都可恢复。取消、被新 Goal 替代或安全中止分别使用 `cancelled`、`superseded`、`aborted`，并记录退出原因、证据和未提交变更处置；退出不自动授权清理。

终态开始新工作时必须使用不同的 Goal ID，并回到最小 `clarifying` 契约。旧 carry 不继承；当前非治理差异重新登记为受保护的 `preexisting_changes`，`spec_id` 修复为 `SPEC-<新 Goal ID>` 后刷新 handoff。

## 3. 工作图与并行

五个状态文件是唯一真实来源。Policy 在内存中派生 Requirement → AC → Task → Evidence 主链，并校验 Requirement、Task、Issue、Skill、依赖、负责人、验证者和修改范围。

Task 仅从当前 frontier 认领，状态为 `pending → working → review → done`；阻断时使用 `blocked`。Issue 使用 `open → fixing → verify → closed`。实现者不能成为唯一验证者，修复者不能独立关闭自己的问题。

策略一次只授权一个 `active_task`。真正并行写入必须使用独立 SVN 工作副本和互斥范围；同文件、强顺序依赖或范围不明确时顺序执行。

## 4. Agent 监督与异常恢复

Agent 运行状态和 WALI Task 状态是两套状态机。`TaskCompleted` 与 `TeammateIdle` 只阻止运行事件和活动 Task/证据不一致；`StopFailure` 只记录失败，不能阻止异常退出。

诊断时交叉检查：

1. `/tasks`、Agent 面板或后台 Agent View。
2. `wali_supervision.py status`。
3. transcript 最后动作与错误。
4. 当前 Task、phase、SVN 状态和真实差异。

没有新输出不等于卡死。确认异常后先冻结 Task 和路径所有权，审计已有差异，优先恢复原 Agent。只有无法恢复时才以相同 Task ID、Spec、范围、差异和失败证据启动替代者。不得自动回退、清理、覆盖或提交。

监督事件保存在 `.svn/wali-policy/supervision.json`，不进入 SVN。并发更新使用持久的 `supervision.lock` 文件和操作系统建议锁：POSIX 使用 `fcntl.flock`，Windows 使用 `msvcrt.locking`。PID、所有者令牌和时间仅用于诊断，不参与所有权判断；真正的互斥状态由内核持有。进程正常结束或异常退出时锁都会由操作系统释放，下一次 Hook 可复用同一文件；仍被存活进程持有时不能强占。若平台没有受支持的锁后端，监督写入直接失败，不降级为无锁写入。

活动任务仍有未恢复失败时，handoff 必须填写精确 `supervision_event`、`recovery_action`（`resume`、`replace`、`wait_user`、`terminate_goal`）和可验证的 `recovery_evidence`。

## 5. SVN 工作副本与交付

WALI 要求 SVN 1.9+，所有有副作用动作从 `svn info --show-item wc-root` 发现真实工作副本根。普通子目录、无法验证的元数据或无法保存动作快照会被拒绝。

项目维护者可以提交目录上的 `svn:ignore`，或在 SVN 1.8+ 的工作副本根提交 `svn:global-ignores`。WALI 不推断规则、不创建 `.svnignore`，也不自动执行 `propedit`、`propset` 或 `propdel`。

读取状态时，WALI 用 `--config-option config:miscellany:global-ignores=` 排除个人客户端配置，再用 `--no-ignore` 保留完整诊断视图。只有项目 SVN 属性产生、状态为 `ignored`，且自身与祖先属性没有本地修改的未版本化项归入本地产物；它们不进入 baseline、carry、handoff 摘要、Stop 阻断或提交差异。

普通 `unversioned` 项、已版本化变化、冲突、externals 和属性变化继续接受完整审计。Ignore 属性本身的修改也是版本化差异，不会因它同时改变文件分类而消失。

`implementing` 只允许在活动任务精确 leaf path 上使用受控的：

- `svn add/delete/move/copy`
- `svn update -- <exact-path>...`
- `svn resolve --accept working -- <exact-path>...`

交付前出现过期或冲突时返回合法实施任务，精确同步、显式解决、重新验证并生成新 carry。不得在 `delivering` 中顺手修改或运行项目命令。

进入 `delivering` 前必须已有用户业务验收、当前 carry、逐个精确 `svn_commit_paths` 和可追溯授权依据。只接受：

```text
svn commit (-m|--message) <literal> -- <exact-leaf-path>...
```

每次提交仍由 PreToolUse 请求用户当场确认。PostToolUse 只有在成功输出包含唯一修订号、授权路径已清洁、现存目标的 `last-changed-revision` 都等于该修订号时才写本地交付回执。Stop 会再次核对回执、授权、指纹和工作副本；空提交不能生成回执。

## 6. 命令索引

在项目根运行，测试命令除外：

- `python3 .claude/hooks/wali-doctor.py --project-root .`
- `python3 .claude/hooks/wali_policy.py check`
- `python3 .claude/hooks/wali_policy.py audit`
- `python3 .claude/hooks/wali_policy.py baseline`
- `python3 .claude/hooks/wali_policy.py digest`
- `python3 .claude/hooks/wali_policy.py handoff-digest`
- `python3 .claude/hooks/wali_policy.py carry`
- `python3 .claude/hooks/wali_graph.py --project-root . check`
- `python3 .claude/hooks/wali_graph.py --project-root . frontier`
- `python3 .claude/hooks/wali_graph.py --project-root . parallel`
- `python3 .claude/hooks/wali_graph.py --project-root . mermaid`
- `python3 .claude/hooks/wali_supervision.py --project-root . status`
- `python3 .claude/hooks/wali_board.py --project-root . --open`
- `python3 .claude/hooks/wali_stop.py --project-root .`
- `python3 -m json.tool .claude/settings.json`

在 `.claude/hooks/` 中运行完整控制面测试：

```text
python3 -m unittest -v test_wali_graph.py test_wali_policy.py test_wali_stop.py test_wali_supervision.py test_wali_svn.py test_wali_doctor.py test_wali_board.py
```
