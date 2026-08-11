# wali-0x3

> 让 Claude Code 中的开发工作可确认、可执行、可验证、可恢复，同时不让治理流程拖慢实际交付。

`wali-0x3` 是 Agent 名称，不是软件版本名。它是一套可嵌入项目仓库的提示词、状态格式和 Claude Code Hooks。

归档目录使用可见的 `claude/`；部署到目标项目时复制或改名为 `.claude/`。目标运行环境面向 SVN 工作副本，归档仓库本身使用 Git。

## 核心取舍

WALI 只保留会直接提高交付可信度的治理：

- 开工前确认目标、范围和验收方法。
- 实现写入受 active Task Scope 约束。
- 实现者自检与独立验证分离。
- 外部写入需要显式授权和当场确认。
- 真正交接时留下最小恢复游标。

它明确不做：

- 每轮对话都写进度文件。
- 每次停止都生成 handoff 摘要。
- 把普通本地命令登记成完整字符串白名单。
- 为单任务强制建立“图工程”。
- 默认启用 Agent Teams 生命周期监督。
- 用 PostHook 把状态锁进不可修复的失败模式。

## 两份常驻状态

### `goal.md`

稳定契约，包含：

- Goal ID、确认状态和外部写入授权。
- 用户要观察到的结果、背景、In/Out/Constraints。
- `R-XXX` Requirement。
- `AC-XXX` Acceptance Criterion 和验证方法。

进入 `work` 后，Goal 的稳定定义不应随执行细节变化。需求发生实质变化时返回 `define` 并重新确认。

### `work.md`

可变执行状态，包含：

- phase、active Task、等待原因、停止意图和最终 outcome。
- 每个 AC 的状态、Evidence 和 Verifier。
- Task 的 AC、状态、依赖、Scope、Owner、Evidence 和 Verifier。
- Issue 的关联、严重程度、状态、描述和 Evidence。

不再维护独立的 Spec、Todo、Issues 文件；这些内容已分别归入 Goal 和 Work。

### `handoff.md`

只在真正需要跨会话恢复时创建。它只保存当前状态和唯一下一步，不复制完整 Goal/Work，不记录摘要哈希，不追加进度历史。

## 工作循环

```text
define：澄清并确认 Goal
   ↓
work：实现一个 working Task
   ↓
verify：独立审查、测试和问题闭环
   ├─ 需要修复 ─→ work
   ├─ 等待用户/外部条件 ─→ paused
   └─ 全部验收通过 ─→ done
```

阶段只在职责变化时更新，不是每个动作都要写一次的进度条。

## 内部 WorkIndex

WALI 会从 Goal 和 Work 派生一个临时 WorkIndex，用于：

- 检查 Requirement → AC → Task → Evidence 是否断链。
- 检查重复 ID、不存在的引用和 Task 依赖环。
- 计算当前 frontier。
- 在多任务场景判断 Scope 是否互斥。

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

- 进入 work：Goal 已确认且至少有一个 Task。
- 进入 verify：active Task 已 review 并有实现 Evidence。
- 进入 done：所有 Task 和 AC 已完成，没有未关闭 blocker。

## Hook 行为

### PreToolUse

只匹配 Bash 和写入工具。Read、Glob、Grep、Agent、Skill 不经过 WALI Policy；Agent/Skill 内部产生的 Bash 或写入仍会分别接受检查。

Policy 保护：

- 破坏性本地命令。
- 未授权外部写入。
- WALI 控制面文件。
- active Task Scope 外的实现写入。
- 非 work 阶段的实现修改。

工作区内普通读取、搜索、测试、构建和检查命令无需预先登记。

Scope 对 Write/Edit 等原生写入工具是强门禁；Bash 还识别重定向、`touch/rm/mv/cp/tee/sed -i` 等显式文件变更并应用同一门禁。Hook 无法从任意测试或构建程序内部可靠推断隐藏副作用，因此它不是操作系统沙箱；需要强隔离的并发或不可信脚本应使用独立工作区/沙箱。

### PostToolUse

PostHook 只在治理状态写入后检查 Goal/Work 是否完整。发现不完整时返回提示，不返回 block；下一次对 `goal.md`、`work.md` 或 `handoff.md` 的修复始终允许。

### Stop

普通 Stop 直接允许。只有 `stop_intent: handoff` 时，才要求：

- `handoff.md` 存在。
- Goal ID、phase 和 active Task 与当前 Goal/Work 一致。
- 更新时间真实。
- Current State 和 Next Step 非占位。

## 命令策略

本地命令默认可用，但以下操作仍受保护：

- `rm -rf`、`git reset --hard`、强制 `git clean`、`svn revert`，以及带删除未版本化/忽略项参数的 `svn cleanup` 等破坏性命令。普通 `svn cleanup` 保留可用。
- Git/SVN 推送或提交、上传、发布、集群修改等外部写入。
- 本地 SVN 调度超出 active Task Scope 的路径。

外部写入需要先把 Goal 中的 `allow_external_writes` 设为 `true`，实际工具调用仍返回 `ask`，由用户当场核对。

## 角色

- Coordinator：维护 Goal/Work、选择执行方式、推进检查点。
- Developer：在 work 中实现一个 Scope 明确的 Task。
- Reviewer：在 verify 中独立审查并记录 Issues。
- Tester：在 verify 中按 AC Method 独立验证。
- Architect：只在高代价架构选择会改变 Goal 时做只读比较。

主会话能稳定完成时不增加 Agent。需要独立上下文时使用普通 Subagent；默认设置不启用 Agent Teams 或生命周期监督 Hooks。

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
└── work.md
```

## 部署

1. 把 `claude/` 复制或改名为目标项目的 `.claude/`。
2. 保留 `docs/wali-0x3/goal.md` 和 `work.md` 模板。
3. 运行：

```text
python3 .claude/hooks/wali-doctor.py --project-root .
```

4. 在真实 SVN 工作副本检查 `svn info`、`svn status` 和 `svn diff --internal-diff`。
5. 做四个冒烟测试：普通本地命令、Scope 内写入、Scope 外拒绝、显式 handoff。

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

- `/wali-start <需求或资料>`：定义并确认 Goal，建立首个 Task。
- `/wali-resume`：从 Goal、Work、真实差异和可选 handoff 恢复。
- `/wali-inspect`：进入独立验证和问题闭环。
- `/wali-handoff`：仅在确实需要跨会话恢复时创建游标。
