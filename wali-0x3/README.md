# wali-0x3

> 让 Claude Code 中的开发工作可确认、可执行、可验证、可恢复，同时不让治理流程拖慢实际交付。

`wali-0x3` 是 Agent 名称，不是软件版本名。它是一套可嵌入项目仓库的提示词、状态格式和 Claude Code Hooks。

归档目录使用可见的 `claude/`；部署到目标项目时复制或改名为 `.claude/`。目标运行环境面向 SVN 工作副本，归档仓库本身使用 Git。

## 核心取舍

WALI 只保留会直接提高交付可信度的治理：

- 开工前确认目标、范围和验收方法。
- 已认领 active Task Scope 内的实现写入直接通过，例外写入当场确认。
- 实现者自检与独立验证分离。
- 外部写入需要当场确认，不要求先改状态文件申请授权。
- 真正交接时留下最小恢复游标。

它明确不做：

- 每轮对话都写进度文件。
- 每次停止都生成 handoff 摘要。
- 把普通本地命令登记成完整字符串白名单。
- 为单任务强制建立“图工程”。
- 启用 Agent Teams、心跳或 idle 生命周期监督。
- 用 PostHook 把状态锁进不可修复的失败模式。

## 三份常驻状态

### `goal.md`

稳定契约，包含：

- Goal ID 和确认状态。
- 用户要观察到的结果、背景、In/Out/Constraints。
- `R-XXX` Requirement。
- `AC-XXX` Acceptance Criterion 和验证方法。

进入 `work` 后，Goal 的稳定定义不应随执行细节变化。需求发生实质变化时返回 `define` 并重新确认。

### `spec.md`

稳定的实现契约，包含：

- 当前系统入口、真实行为、约束和代码证据。
- 正常流程、错误与边界、兼容行为和 Non-goals。
- 把 Given/When/Then 直接关联到 AC 的 Behavior Scenarios。
- Requirement → Design → Affected Areas 映射。
- AC → 最高现有 Seam → Coverage → Method 验证映射。
- Agent 可以自主决定、必须询问、不得执行和阻塞前先做什么。

Define 时的 Goal+Spec 候选包先留在对话与上下文中。除非用户明确要求保存草案或真实跨会话交接，确认前不修改三份状态；明确确认后才一次性写入 Goal、Spec 和 Work。进入 work 后 Spec 不记录进度；低层实现选择不逐项追加。只有新的代码事实使行为场景或技术映射失准时才在检查点批量修正，目标行为或 AC 实质变化则返回 define。

### `work.md`

可变执行状态，包含：

- phase、一至两个 active Task、等待原因、停止意图和最终 outcome。
- 每个 AC 的状态、Evidence 和 Verifier。
- Task 的 AC、状态、依赖、Scope、Owner、Evidence 和 Verifier。
- Issue 的关联、严重程度、状态、描述和 Evidence。

`active_task` 可为 `none`、一个 Task ID，或两个逗号分隔的 Task ID。两个 active Task 必须依赖已满足且 Scope 互斥；不再维护 Todo、Issues、第二份 Spec 或进度文件，运行信息只保留在 Work。

### `handoff.md`

只在真正需要跨会话恢复时创建。它只保存当前状态和唯一下一步，不复制完整 Goal/Spec/Work，不记录摘要哈希，不追加进度历史。

## 工作循环

```text
define：在对话中综合并确认 Goal + Spec，确认后一次持久化
   ↓
work：实现一至两个 working Task
   ↓
verify：独立审查、测试和问题闭环
   ├─ 需要修复 ─→ work
   ├─ 等待用户/外部条件 ─→ paused
   └─ 全部验收通过 ─→ done
```

阶段只在职责变化时更新，不是每个动作都要写一次的进度条。

## 内部 WorkIndex

WALI 会从 Goal、Spec 和 Work 派生一个临时 WorkIndex，用于：

- 检查 Requirement → Design、AC → Verification → Task → Evidence 是否断链。
- 检查重复 ID、不存在的引用和 Task 依赖环。
- 计算当前 frontier。
- 在多任务场景判断 Scope 是否互斥。
- 为最多两个实现 Agent 选择依赖已满足的安全并发候选。

WorkIndex 是实现细节，不创建图数据库、图文件或 Mermaid 副本。单任务通常只需要 `check`，无需运行 frontier/parallel。

```text
python3 .claude/hooks/wali_work.py check
python3 .claude/hooks/wali_work.py frontier
python3 .claude/hooks/wali_work.py parallel
```

## 检查点

关系完整性不在每次工具调用时重建，而是在职责转换前检查：

```text
python3 .claude/hooks/wali_work.py check --checkpoint work
python3 .claude/hooks/wali_work.py check --checkpoint verify
python3 .claude/hooks/wali_work.py check --checkpoint done
```

- 进入 work：Goal 已确认、Spec implementation-ready、没有 Open Questions，每个 AC 有 Behavior Scenario 和可定位测试 Seam，Requirement/AC 映射完整且至少有一个 Task。
- 进入 verify：所有 active Task 已 review 并有实现 Evidence。
- 进入 done：所有 Task 和 AC 已完成，没有未关闭 blocker。

## Hook 行为

### PreToolUse

只匹配 Bash 和写入工具。Read、Glob、Grep、Agent、Skill 不经过 WALI Policy；Agent/Skill 后续发起的 Bash 或写入仍会分别接受检查。

Policy 是软门禁：

- 普通命令和已认领 active Task Scope 内写入直接 `allow`。
- 外部写入、控制面修改、Scope 外写入、非 work 阶段写入和可恢复的高风险本地操作返回 `ask`。
- 可能删除项目根、主目录或系统根的灾难性操作，以及实现 Subagent 执行破坏性工作区命令或越过认领、Scope、控制面、SVN 调度边界时返回 `deny`。这些拒绝都指向 Coordinator，不阻断主会话修复。

工作区内普通读取、搜索、测试、构建和检查命令无需预先登记。

Scope 对 Write/Edit 等原生写入工具是默认边界；Bash 还识别重定向、`touch/rm/mv/cp/tee/sed -i` 等显式文件变更并应用相同分级。实现 Subagent 必须同时匹配 `agent_id + agent_type` 的 Task 认领，只能写该 Task Scope。超出边界时由用户当场决定，而不是为了例外先重写 Goal/Work。Hook 无法从任意测试或构建程序内部可靠推断隐藏副作用，因此它不是操作系统沙箱；不可信脚本仍应使用独立工作区/沙箱。

### SubagentStart / SubagentStop

最多两个实现 Agent 并发。`SubagentStart` 根据 `session_id + agent_id + agent_type`，通过系统临时目录中的逐 Task `O_EXCL` 文件原子认领一个 Owner 匹配的 active Task；每次工具调用还会复核当前 Owner。`SubagentStop` 释放认领。认领不写仓库、不改 Work、没有轮询心跳，也不持有长期进程锁。两个同类型 Agent 也可以各认领一个 Scope 互斥的 Task。

若 Agent 异常退出且 Stop Hook 未执行，Coordinator 等其他实现 Agent 全部结束后运行 `python3 .claude/hooks/wali_work.py clear-claims`，再重新分派。该命令只清理系统临时目录中的本项目 claim；有实现 Agent 仍在运行时不得调用。

Coordinator 是 Goal/Spec/Work/Handoff 的唯一写入者。Backend/Frontend Dev、Reviewer 和 Tester 只返回结构化结果；Coordinator 核对路径与真实差异后，一次批量写 Work，并串行执行必要的 SVN add/delete/move/commit。共享配置、lockfile、路由总表、生成代码和数据库迁移必须归一个 Task，或拆成后续串行 integration Task。

### 外部 Skill

项目设置允许受信任 Skill 使用 `!` 动态上下文命令，Skill 和 Agent 调用本身不由 WALI 拦截。Claude Code 会在 Skill 内容交给模型前执行这类命令，因此它们不是普通的模型 Bash 工具调用；安装或调用外部 Skill 前应审查来源和 `SKILL.md`。Skill 后续由模型发起的 Bash/写入仍按上述软门禁处理。

### PostToolUse

PostHook 只在治理状态写入后检查 Goal/Spec/Work 是否完整。发现不完整时返回提示，不返回 block；下一次对 `goal.md`、`spec.md`、`work.md` 或 `handoff.md` 的修复始终允许。

### Stop

普通 Stop 直接允许。只有 `stop_intent: handoff` 时，才要求：

- `handoff.md` 存在。
- Goal ID、phase 和 active Task 与当前 Goal/Spec/Work 一致。
- 更新时间真实。
- Current State 和 Next Step 非占位。

## 命令策略

本地命令默认可用，但以下操作仍受保护：

- `rm -rf`、`git reset --hard`、强制 `git clean`、`svn revert`，以及带删除未版本化/忽略项参数的 `svn cleanup` 等可恢复高风险命令会请求确认。普通 `svn cleanup` 直接可用。
- Git/SVN 推送或提交、上传、发布、集群修改等外部写入。
- Coordinator 的本地 SVN 调度超出 active Task Scope 的路径；实现 Agent 的 SVN 调度一律交回 Coordinator。

外部写入直接返回 `ask`，由用户当场核对目标与影响；不再为了获得许可修改 Goal。

## 角色

每个 Agent 定义都由三层组成：稳定的身份与判断立场、当前职责与边界、结构化输出契约。身份不是装饰性人设；它规定角色面对不完整证据和方案取舍时如何思考，拆分或精简角色时不得只保留权限清单。

- Coordinator：唯一维护 Goal/Spec/Work/Handoff；一次确认后连续编排检查点、Task 与串行 SVN 集成。
- Backend Dev：依据 implementation-ready Spec 实现已认领的后端 Task，返回路径、自检和 Evidence。
- Frontend Dev：依据已确认的接口 Seam 实现已认领的 UI/交互 Task，返回路径、自检和 Evidence。
- Reviewer：在 verify 中独立审查，向 Coordinator 返回建议 Issues。
- Tester：在 verify 中按 AC Method 独立验证，向 Coordinator 返回 Evidence。
- Architect：只在高代价架构选择会改变 Goal 时做只读比较。

主会话能稳定完成时不增加 Agent。存在两个无依赖、Scope 互斥且工作量值得并发的 Task 时，Coordinator 可同时启动前端+后端，或两个同类型实现 Agent。默认设置不启用 Agent Teams、心跳或 idle 监督；只用轻量 Subagent 启停 Hook 做 Task 认领与释放。

## 最小交互原则

`/wali-start` 先检查代码、测试、配置和项目资料。能自行发现的答案不询问用户；只把会改变结果且只有用户能决定的问题集中为一轮 1–3 个问题。没有阻塞问题时直接给出一次 Goal+Spec 确认包，此前不边综合边写文件。

Spec 使用固定的“对话到规格”映射：问题背景与期望结果进入 Goal，明确排除项进入 Scope Out，可观察行为进入直连 AC 的 Behavior Scenarios，已确认的实现与验证选择分别进入 Design Mapping 和 Verification Mapping。Affected Areas 保留精确路径，验证自主选择现有的最高测试 Seam；默认只形成 WALI 的 Goal、Spec、Work，只有用户明确要求时才额外发布。

用户确认后，Agent 自动建立 Work、实现、测试、修复、独立验证并选择下一 Task。`May decide` 中的可逆低影响细节由 Agent 自主选择；只有用户可见语义、Acceptance 冲突、不可逆数据迁移、重大安全/费用风险或不可安全回滚的外部副作用才重新交互。

## 目录

```text
claude/
├── settings.json
├── agents/
├── hooks/
│   ├── wali-doctor.py
│   ├── wali_work.py
│   ├── wali_policy.py
│   ├── wali_stop.py
│   ├── wali_svn.py
│   └── test_wali_*.py
├── refs/
├── rules/
└── skills/
    ├── wali-start/
    ├── wali-resume/
    ├── wali-inspect/
    └── wali-handoff/

docs/wali-0x3/
├── goal.md
├── spec.md
└── work.md
```

## 部署

1. 把 `claude/` 复制或改名为目标项目的 `.claude/`。
2. 保留 `docs/wali-0x3/goal.md`、`spec.md` 和 `work.md` 模板。
3. 运行：

```text
python3 .claude/hooks/wali-doctor.py --project-root .
```

4. 在真实 SVN 工作副本检查 `svn info`、`svn status` 和 `svn diff --internal-diff`。
5. 做六个冒烟测试：普通本地命令、Skill 调用、两个 Agent 原子认领不同 Scope、各自 Scope 内写入、交叉 Scope 确认、显式 handoff。

## 测试

在 Hooks 目录运行：

```text
python3 -m unittest -v \
  test_wali_liveness.py \
  test_wali_work.py \
  test_wali_policy_light.py \
  test_wali_doctor_light.py \
  test_wali_svn.py
```

## 使用入口

- `/wali-start <需求或资料>`：在对话中从需求与代码事实综合 Goal+Spec，确认后与 Work 一次写入并自动开始开发。
- `/wali-resume`：从 Goal、Spec、Work、真实差异和可选 handoff 恢复。
- `/wali-inspect`：进入独立验证和问题闭环。
- `/wali-handoff`：仅在确实需要跨会话恢复时创建游标。
