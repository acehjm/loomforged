# Runtime Lens

Runtime Lens 是面向 Claude Code 的测试环境只读诊断工具，由 Runtime Trace Skill 和 Runtime Lens MCP 组成。

它能把用户描述、本地源码、Nginx 路由、远程端口、进程、配置和日志串成一条证据链，帮助定位 Linux 测试环境中的服务调用、运行状态、HTTP 错误、空数据、安装失败和 Trace 问题。

## 工具价值

源码与测试环境割裂，服务、进程、日志和调用链依赖人工排查，耗时且易误判。Runtime Lens 通过 Skill 编排诊断，由 MCP 现场取证并关联源码、Nginx 与运行日志，帮助开发人员快速定位根因。

多实例、日志布局差异和标识不一致使服务定位复杂，大日志检索还容易超时。项目通过公共路径规则及组件、服务、端口和 PID 精确取证，并采用分阶段限时、有界检索、脱敏输出和超时降级兼顾效率与安全。

应用后，可以减少登录服务器、查进程、找路径和反复检索日志等人工操作，降低排障与沟通成本，提高诊断效率、自动化程度和测试资源利用率。它在研发链路中承担“源码到运行环境”的诊断桥梁，打通本地开发、联调测试、组件安装、现场取证、根因定位和结论输出。

> 在可信网络环境下，连接至生产环境，可以快速进行日志分析与问题排查定位。

## 适合场景

Runtime Lens 适合以下场景：

- 查看指定组件或服务在某个时间附近的 error、debug 等日志。
- 本地开发调用平台内部服务失败或返回空数据时，结合源码与测试环境日志定位原因。
- 根据 TraceId、接口路径、错误码或请求特征还原调用链。
- 页面访问出现 404、500、502 或超时等，关联 Nginx 路由、access/error 日志和上游服务。
- 根据远程监听端口反查 PID、进程目录、启动命令、Tomcat 实例和服务候选。
- 检查组件安装日志、失败目录及安装后的服务状态。
- 排查事件是否到达分发端和订阅端服务日志。
- 对比运行配置与当前源码，解释异常、空指针或行为差异。

Runtime Lens 不要求维护完整服务清单。组件和服务只要遵循公共目录与日志规则，就能由 MCP 在现场发现。

## 安装与首次配置

以下步骤面向 Windows 上的 Claude Code 用户。Runtime Lens 通过本地目录共享和安装，不需要 Marketplace。

### 1. 创建私有 SSH 配置

参考 `config/runtime-lens.example.json`，创建实际使用的私有文件地址放到个人目录的.ssh文件夹中：

```text
C:\Users\{用户名}\.ssh\runtime-lens.json
```

每台服务器只填写 SSH IP、端口、账号和密码：

```json
{
  "version": 1,
  "connections": [
    {
      "ip": "<SSH IP>",
      "port": 22,
      "username": "<账号>",
      "password": "<密码>"
    }
  ]
}
```

`config/runtime-lens.example.json` 只是填写示例，不会作为实际连接配置使用。真实 SSH 信息不要放入 Runtime Lens 目录或其他共享位置。

当前版本不固定校验服务器主机密钥，请在可信测试网络中使用，并为 Runtime Lens 配置权限与诊断范围相匹配的测试环境账号。

### 2. 复制完整目录

将完整的 `runtime-lens` 目录复制到：

```text
C:\Users\{用户名}\.claude\skills\runtime-lens\
```

不能只复制 `skills/runtime-trace`。安装目录中至少应存在：

```text
%USERPROFILE%\.claude\skills\runtime-lens\.claude-plugin\plugin.json
%USERPROFILE%\.claude\skills\runtime-lens\.mcp.json
%USERPROFILE%\.claude\skills\runtime-lens\mcp\server.mjs
%USERPROFILE%\.claude\skills\runtime-lens\skills\runtime-trace\SKILL.md
```

复制完成后重新启动 Claude Code。

### 3. 验证安装

先在 PowerShell 中查看 Runtime Lens 的安装信息：

```powershell
claude plugin details runtime-lens@skills-dir
```

该命令应能显示 Runtime Lens 的版本和 MCP 信息，说明插件已被 Claude Code 识别。

然后进入 Claude Code，完成两项检查：

1. 执行 `/mcp`，确认 `plugin:runtime-lens:runtime-lens` 已连接。
2. 要求 Claude 调用 Runtime Lens 的 `list_environments`，确认私有 SSH 配置存在，并查看当前配置了哪些测试环境。

`list_environments` 不连接远程服务器，也不用于确认插件版本或 MCP 信息；它只读取环境配置并返回可用环境清单。

## 日常使用

安装成功后，直接用自然语言描述问题即可。例如：

```text
连接 <SSH IP>，帮我查看 xx 组件最近一次错误日志。

看下 xx 服务在 15:00 左右的 debug 日志，整理执行过程。

本地调用人员基础信息接口返回空，结合源码和测试环境日志排查原因。

访问测试环境页面返回 404，结合 Nginx、日志和代码定位失败原因。

根据 TraceId xxx 看请求经过了哪些服务，在哪里失败。

检查 xx 组件中午那次安装是否成功。
```

### 测试环境如何选择

Runtime Trace 按以下顺序确定 SSH 环境：

1. 用户明确提供 SSH IP 时（必须包含在 SSH 环境清单中），直接使用该地址。
2. 未提供时，只在当前源码目录的 `config.properties`，以及文件名为 `application` 或 `application-<profile>`、扩展名为 `.yml`、`.yaml` 或 `.properties` 的配置文件中查找精确配置 `@bic.bic.ip`。
3. 地址仍无法确定、存在冲突或无法解析时，会主动询问用户。

本地配置中的其他服务地址和端口只用于理解调用方式，不能代表测试环境的实际监听端口或运行状态。

### 组件和服务标识

Runtime Lens 区分 `component` 和 `service`。一个组件可以包含多个服务，两者不能互相覆盖。

用户或源码给出的组件、服务标识会在查询前转换为小写。URL、接口路径、查询词和 TraceId 保持原值。标识无法从用户说明或源码配置中确认时，Skill 会询问用户。

## MCP 能力

MCP 工具只返回远程只读证据。Runtime Trace Skill 会根据问题选择范围最小的工具，不需要每次执行完整能力。

所有能力均通过预定义参数执行，只允许读取、列举和检索受限路径；不提供任意远程命令，不写文件或配置，不启停服务，不安装软件，也不执行部署。返回结果有数量限制，并对常见凭据进行脱敏。

| 能力 | 工具 | 用途                                               |
| --- | --- | --- |
| 环境匹配 | `list_environments`、`resolve_environment` | 列出已配置地址，或根据 SSH IP 选择唯一测试环境                      |
| 组件发现 | `discover_services` | 在用户明确要求查看部署清单时，按公共目录规则列出组件                       |
| 服务检查 | `inspect_service` | 按 component/service 检查组件目录、Tomcat、进程和监听端口        |
| 端口反查 | `inspect_port` | 用远程监听端口反查 socket、PID、cwd、启动命令和服务候选               |
| 进程检查 | `inspect_process` | 用已知 PID 获取监听端口、日志 fd、stdio、cgroup 和 systemd unit |
| 日志查询 | `search_logs` | 查询服务、Nginx、安装日志或已有证据指向的精确日志文件                    |
| 日志目录 | `list_log_directory` | 有界列举已确认目录中的日志文件元数据，不读取内容                         |
| Journal | `search_journal` | 查询现场证据确认的精确 systemd unit 日志                      |
| Trace 关联 | `trace_request` | 优先在已知服务范围内查询 TraceId，必要时再做有界关联                   |
| Nginx 路由 | `resolve_nginx_route` | 查询实际存在的 cluster 实例、路由配置和相关错误日志                   |
| 配置读取 | `read_service_config` | 只返回指定配置键附近的脱敏片段，不读取整份配置                          |

## 配置与知识如何分工

每类信息只在一个位置维护：

| 内容                                   | 维护位置                                   | 是否按环境重复     |
| ------------------------------------ | -------------------------------------- | ----------- |
| SSH IP、端口、账号、密码                      | `%USERPROFILE%\.ssh\runtime-lens.json` | 是，每台服务器一条记录 |
| 平台根目录、组件、Tomcat、Nginx、日志和 Trace 路径模板 | `config/runtime-lens.rules.json`       | 否，所有测试环境共用  |
| 测试环境含义和环境选择规则                        | `knowledge/environment.md`             | 否           |
| component、service、实例、Tomcat 和日志语义    | `knowledge/platform-layout.md`         | 否           |
| Agent 的诊断步骤、证据优先级和停止条件               | `skills/runtime-trace/SKILL.md`        | 否           |

`runtime-lens.rules.json` 支持 `{platformRoot}`、`{component}`、`{service}` 和 `{N}` 等占位符。

## 如何扩展 Runtime Trace Skill

扩展前先判断变化属于“诊断流程”“平台知识”“路径规则”还是“MCP 能力”。不要把所有变化都写进 Skill。

### 新增一种通用排查流程

修改 `skills/runtime-trace/SKILL.md`：

1. 如果新场景需要被 Claude 自动识别，在 frontmatter 的 `description` 中加入稳定、通用的触发语义。
2. 在调查流程中说明入口条件、首选证据、工具选择、降级方式和停止条件。
3. 复用现有 MCP 工具，优先使用精确端口、PID、component/service 或路径，避免新增宽范围扫描。
4. 使用通用术语描述规则；现场组件名、一次性故障和本次排查过程不要沉淀进 Skill。

如果新服务仍遵循现有组件目录和日志规则，不需要修改 Skill 或 MCP。

### 补充稳定的平台规律

- 环境用途、共同特征或环境选择语义写入 `knowledge/environment.md`。
- 组件、服务、实例、Tomcat、日志或安装目录的稳定语义写入 `knowledge/platform-layout.md`。
- 新的公共路径模板、日志模式、安装日志路径或明确别名写入 `config/runtime-lens.rules.json`。

知识文件解释“这些信息代表什么”，规则文件告诉 MCP“允许去哪里读取”。不要在两处重复维护动态服务清单或当前运行状态。

## 常见安装问题

### Skill 能加载，但 MCP 连接失败

确认安装的是完整 `runtime-lens` 目录，并检查 `.mcp.json`、`mcp/server.mjs` 和 `.claude-plugin/plugin.json` 是否存在。只复制 `skills/runtime-trace` 无法启动 MCP。

### MCP 已连接，但环境列表读取失败

检查 `%USERPROFILE%\.ssh\runtime-lens.json` 是否存在、JSON 是否有效，以及字段是否只使用 `ip`、`port`、`username` 和 `password`。

### 修改后仍显示旧行为

完整覆盖安装目录并重新启动 Claude Code。随后调用 `list_environments`，以返回的 `runtimeLensVersion` 判断实际运行版本，不要只看源目录中的版本号。
