# Claude Code 与 wali-0x3 兼容要求

通过功能检测确认环境，不用 Agent 名称表达软件版本。

## 必需能力

- 项目级 `CLAUDE.md`、`.claude/settings.json`、Agents、Rules 和 Skills。
- `docs/wali-0x3/goal.md`、`spec.md`、`work.md` 三份状态接口。
- `PreToolUse`、`PostToolUse` 和 `Stop` command Hook。
- Hook 的 `command + args` 形式及 matcher。
- Python 3.9+。
- 目标项目若使用 SVN，需要可用的 SVN CLI 和真实工作副本。

默认配置不需要 Agent Teams、TeammateIdle、TaskCompleted 或 StopFailure。普通 Subagent 失败通过 transcript、Work 和真实差异恢复。

## 部署核对

1. 将归档中的 `claude/` 复制或改名为目标项目的 `.claude/`。
2. 运行 `python3 .claude/hooks/wali-doctor.py --project-root .`。
3. `/hooks` 应显示三类核心 Hook；Read、Glob、Grep、Agent、Skill 不应匹配 PreToolUse Policy。
4. 在 `.claude/hooks/` 运行控制面测试。
5. 在真实项目检查 `svn info`、`svn status` 和 `svn diff --internal-diff`。
6. 用一次普通本地测试命令、一次受信任 Skill 调用、一次 Scope 内写入、一次 Scope 外确认和一次显式 handoff 做冒烟验证。

缺少核心 Hook 时不要假装策略仍受保护；应修复部署或明确在没有 WALI Policy 的模式下继续。
