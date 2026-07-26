---
ref_id: REF-WALI-COMPAT-001
title: Claude Code 与 WALI 兼容要求
kind: compatibility
applies_to:
  - .claude/settings.json
  - .claude/agents/**
  - .claude/hooks/**
source: Claude Code 官方文档与项目回归测试
version: "1"
last_verified: 2026-07-26
owner: WALI 控制面维护者
---

# Claude Code 与 WALI 兼容要求

WALI 采用功能检测，不用易过期的固定版本号冒充兼容性。部署环境必须验证下列能力；组织策略和实际运行界面显示的结果优先于存档假设。

## 必需能力

- 项目级 `CLAUDE.md`、`.claude/settings.json`、`.claude/rules/`、`.claude/agents/` 和 `.claude/skills/`。
- `PreToolUse`、`PostToolUse` 和 `Stop` command Hook。
- Hook exec form：`command` 与 `args` 分离传参。
- Agent frontmatter 的 `model`、`effort`、`tools` 和 `permissionMode`。
- 路径限定 Rules。
- `disableSkillShellExecution`。
- Python 3.9+ 标准库、SVN 1.9+ CLI，以及平台文件锁：POSIX 的 `fcntl.flock` 或 Windows 的 `msvcrt.locking`。

缺少任一核心 Policy/Stop 能力时，不得进入 `implementing`、`inspecting` 或 `delivering`，应升级 Claude Code 或停止部署。

## 可选能力

Agent Teams 以及 `TeammateIdle`、`TaskCompleted`、`StopFailure` 用于并行协作监督。不能确认这些能力时：

1. 不启用 Agent Teams。
2. 使用主会话或普通 Subagent 顺序执行。
3. 仍保留 Task、Evidence、handoff、Policy 和 Stop 检查。
4. 不把缺失的运行事件伪装成已监督证据。

模型或组织策略不支持角色声明的 `effort` 时，应在启动时明确告知用户实际值；它可以影响成本和分析深度，但不能降低阶段、范围、验证和 SVN 权限要求。

`svn:global-ignores` 从 SVN 1.8 起可用，因此所有满足 WALI 1.9+ 最低版本的部署都能使用。项目不设置该属性时保持原有审计行为；个人客户端 Ignore 配置不会成为项目判定依据。

## WALI 状态格式

当前只支持：

```yaml
wali_schema: 1
```

该字段位于 `goal.md` 顶层 frontmatter。缺失或未知版本会 fail closed，并提示当前支持版本。WALI 不自动静默迁移旧 Goal；升级时由控制面维护任务显式修改状态模板、Policy 和回归测试。

监督注册表另有本地 `version`，保存在 `.svn/wali-policy/supervision.json`。它不是项目状态 schema，也不进入 SVN。

## 部署核对

存档中的 `claude/` 由使用者复制或改名为目标项目的 `.claude/`；不得在本存档中创建隐藏目录。测试文件继续与 Hook 放在同一目录，不会被设置自动执行。

部署后依次核对：

1. 运行 `python3 .claude/hooks/wali-doctor.py --project-root .`；它只执行读取检查，不创建文件或修改 SVN 属性。
2. `/doctor` 不报告配置、Agent 或 Hook 错误。
3. `/memory` 只显示预期的常驻说明；`engineering.md`、`testing.md` 应按路径加载。
4. `/hooks` 显示 `PreToolUse`、`PostToolUse`、`Stop`，启用 Agent Teams 时还显示三类监督 Hook。
5. 在 `.claude/hooks/` 运行完整 WALI 回归测试。
6. 在真实 SVN 工作副本根运行只读 `svn info`、`svn status` 和 `svn diff --internal-diff`。
7. 若项目使用原生 Ignore，确认普通 `svn status` 隐藏匹配产物，而带 `--no-ignore` 和清空个人 `global-ignores` 的状态仍将其标记为 `ignored`。
8. 确认 `.svn/wali-policy/supervision.lock` 是普通文件；若旧实验版本遗留了同名目录，先确认没有 Hook 正在运行，再由维护者显式清理，WALI 不会猜测并删除它。

排查上下文加载时，可以临时配置 `InstructionsLoaded` Hook 记录实际加载原因；它只用于观察，不应成为权限判断。

## 权威资料

- Claude Code memory、CLAUDE.md 与 Rules：<https://code.claude.com/docs/en/memory>
- Claude Code Hooks：<https://code.claude.com/docs/en/hooks>
- Claude Code Subagents：<https://code.claude.com/docs/en/sub-agents>
- Claude Code Agent Teams：<https://code.claude.com/docs/en/agent-teams>
- Claude Code model 与 effort：<https://code.claude.com/docs/en/model-config>
