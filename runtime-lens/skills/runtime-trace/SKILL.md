---
name: runtime-trace
description: 关联本地源码与测试环境运行证据，按 SSH IP 或 @bic.bic.ip 匹配环境，从生效配置、调用代码、远端路由、端口或进程证据中确定组件与服务，快速定位不同语言实现的独立进程或多实例 Tomcat 的配置和日志。用于排查本地服务调用、浏览器访问测试环境、空数据、超时、无 TraceId 调用、TraceId 链路、HTTP 错误、事件订阅、服务状态、Nginx、配置、安装和日志问题。
---

# Runtime Trace

使用 Runtime Lens MCP 获取测试环境只读证据，并把本地源码、服务、路由和日志还原为问题链。优先完成一次有界定位，不反复试探目录。

## 环境知识

开始远端诊断前读取 [Environment](../../knowledge/environment.md)。涉及组件、服务、实例、Tomcat、日志或 Trace 时读取 [Platform Layout](../../knowledge/platform-layout.md)。精确路径由 MCP 配置和现场结果提供，不自行拼接。

将这两份文件作为只读的公共环境知识。SSH 主机与读取边界以 MCP 配置为准；PID、端口、进程类型、Tomcat 实例、版本和状态以远端查询结果为准。三者不一致时明确报告差异，不要静默选择其一。

## 执行边界

- 将 Runtime Trace Skill、Runtime Lens MCP 及其所在目录视为已提供的只读诊断工具，不是被诊断对象。
- 执行诊断请求时，只读取当前项目源码、项目配置、环境知识和 MCP 返回的远端证据；不搜索、阅读、修改或调试 Skill、MCP、插件实现及其打包文件。
- MCP 返回错误或超时时，按本 Skill 的降级流程保留未知项并继续排查目标系统，不转向工具开发。
- 只有用户明确要求修改 Runtime Trace、Runtime Lens 或其实现时，才把工具本身作为当前任务目标。
- 业务诊断过程中不把现场案例、工具问题或分析过程写入 Skill、README、环境知识、长期记忆或其他持久文件；需要改进工具时只单独报告建议，等待用户明确要求实施。
- 每次新诊断都重新确认环境、component、service、时间和请求线索；不沿用上一个问题的标识、时间、工具结果或结论。

## 原则

- 先确定目标环境和服务标识，再执行一次针对性定位；不要执行固定巡检清单。
- 公共知识只描述稳定环境规律；PID、端口、进程类型和状态必须现场查询。
- 除用于选择 SSH 环境的 `@bic.bic.ip` 外，本地源码中的端口、地址、URL 和路径只能用于理解本地调用，不能判断测试环境是否运行。
- 按 Platform Layout 的服务标识规则，只使用源码配置、调用代码或用户明确给出的目标标识；不要根据相似名称猜测。
- Nginx access、监听端口、PID、工作目录和启动命令属于远端运行事实。已经取得上游端口但标识未知时，先按端口反查，不从 URL 路径、参数名称或业务含义推测 component/service。
- 用户描述浏览器访问测试环境 URL、代理或 Nginx 路径报错时，从远端路由与访问日志开始；只有本地程序发起调用，或已经定位到需要源码解释的应用逻辑时，才先读源码。
- 按当前最强证据选择范围最小的工具；已经取得端口、PID 或精确路径时沿该证据继续，不退回更宽的服务或目录扫描。
- 明确区分事实、推断和未知项。
- 达到最小充分证据后停止调查。
- 不修改文件、配置或数据，不启停服务，不执行部署。
- 不读取、展示或复述 Runtime Lens 私有 SSH 配置及密码；认证完全交给 MCP，工具结果中出现疑似凭据时按已脱敏内容处理。

## 本地源码配置入口

文件清单只在此处维护，后续步骤按用途引用：

下文的“application 配置”指文件名为 `application` 或 `application-<profile>`，且扩展名为 `.yml`、`.yaml` 或 `.properties` 的配置文件；`<profile>` 可以是 `dev` 等环境标识。

| 用途 | 配置文件 |
| --- | --- |
| 读取测试环境 SSH IP | `config.properties`、application 配置 |
| 提取组件和服务标识 | application 配置、`*.toml`，以及调用代码实际引用的项目内配置文件 |

## 调查流程

### 1. 确定测试环境

严格按以下顺序选择环境，不要同时扫描所有测试环境：

1. 如果用户在提示词中明确说明了 SSH IP，使用该值。
2. 否则，先按文件名枚举“本地源码配置入口”中“读取测试环境 SSH IP”列出的文件，只在实际找到的这些文件内查找键名精确为 `@bic.bic.ip` 的直接配置值。禁止先对整个源码目录做内容搜索。若该值引用环境变量或占位符，只在当前生效来源可以明确解析时使用。不要把其他业务 IP 当成 SSH 地址。
3. 多个候选文件给出相同值时按同一环境处理；值不同时，优先使用能够明确确认当前生效 profile 的配置。没有找到、值仍是未解析变量，或无法确认哪个不同值生效时，主动询问用户要连接的 SSH IP。

获得地址后调用 `resolve_environment`。只有恰好匹配一个环境时才继续；同一环境可以包含多台不同角色的主机。没有匹配或匹配多个环境时向用户确认，不要猜测。

### 2. 提取目标标识

涉及本地调用时，围绕失败调用位置读取生效配置、客户端定义和调用参数，并按 Platform Layout 的服务标识规则形成目标。根据当前项目实际使用的语言和调用方式，检查代码中明确声明或传入的组件、服务、目标地址、协议、接口路径或方法标识。

将确认后的 component 和 service 标识统一转换为小写再传给 MCP；用户输入大写或混合大小写时也按此处理。只转换组件和服务标识，不改变 URL、接口路径、查询条件、TraceId 或其他可能区分大小写的值。

按字段语义保留 component 和 service 两个维度，不用一个覆盖另一个。组件配置中的 component id 作为 component；安装、实例或服务配置中的 service、segment 或服务实例前缀作为 service。两者应组合使用，不属于标识冲突。无法确认字段语义时询问用户。

用户、源码或生效配置已明确给出的 component/service 是本次查询标识。`serviceCandidates` 只用于 service 缺失时的辅助发现，不得覆盖或替换已确认标识。

只有组件标识时不要立即询问服务：查询运行日志时把 component 传给 `search_logs` 现场识别；安装失败查询只需要 component。其他必须使用 service 的操作，或现场无法识别唯一服务时再询问。值仍是占位符、多个来源冲突时也要询问。不要用项目名、模块名、类名、目录名或相似名称代替缺失标识。

### 3. 确定调查入口并提取线索

先按用户描述确定请求起点：

- 浏览器直接访问测试环境 URL、代理或 Nginx 路径：保留 URL、时间、状态码和页面错误，从第 4 步的远端入口开始，不预先搜索源码。
- 本地程序、定时任务、前端开发代理或当前源码主动发起调用：围绕失败调用位置读取源码和生效配置。

涉及本地程序调用时确认：

```text
调用位置
→ HTTP/RPC 客户端、SDK 或自定义调用封装
→ 生效配置、目标地址、协议、接口路径或方法、component 和 service
→ TraceId、错误码、时间和请求特征
```

TraceId 是可选线索，不是服务定位的前置条件。没有 TraceId 时保留组件、服务、接口、时间、错误码和脱敏业务特征。

本地端口和服务地址只用于解释本地调用目标。不得使用本地端口查询测试环境监听状态，也不得因该端口在远端未监听而判断服务未运行。

### 4. 选择一次定位入口

确定标识后按问题选择第一个工具，不执行预备性扫描：

- 浏览器访问测试环境入口报错：先调用 `resolve_nginx_route` 查询路由，再用 `search_logs` 的 Nginx 范围查询对应时间的 access/error 日志。根据实际状态码、上游地址和耗时确定失败层，不预先搜索源码。
- Nginx 或其他远端证据已经给出上游监听端口、但 component/service 未知：调用 `inspect_port`，按监听 socket、PID、cwd、可执行文件、启动命令和 Tomcat webapp 获取结构化候选。需要继续确认该进程或日志时，使用返回的 host 和 PID 调用 `inspect_process`，不得根据 URL、参数或功能名称猜标识。
- 没有 PID、需要按 component/service 查询安装路径、Tomcat、进程、端口或运行状态：调用 `inspect_service`。已经有 PID 时不再调用它发现进程。
- 查询服务日志且已有搜索条件：直接调用 `search_logs`；已知 component 和 service 时同时传入，只有其中一个时传已知值。MCP 按已知标识直接展开组件实例和 Tomcat 日志路径，不预先调用 `inspect_service`，也不扫描进程、端口或 systemd。
- 查询安装是否成功：先调用一次 `search_logs`，设置 `scope: installation` 并传 component 和最窄时间线索；按第 6 步判断后，只有需要确认成功时再调用一次 `inspect_service`。
- 已有 TraceId：已知 component/service 时将标识一并传给 `trace_request`，先查询目标服务日志；标识未知或目标服务无证据且确需跨服务关联时，才使用环境范围检索。

调用 `inspect_service` 或 `search_logs` 时，传入第 2 步已经确认并规范化的全部标识。已知 component 时必须直接定位 `{component}.{N}`，不能先遍历组件清单；已知 service 时直接展开服务日志规则。`inspect_service` 只用于确实需要运行态的场景；MCP 内部分别限时查询部署路径、进程和 PID 关联端口，某一阶段失败不丢弃其他已返回证据。

只有 component 的服务日志查询按 `search_logs` 结果处理：`requiresServiceSelection` 为 `false` 且返回 `resolvedService` 时直接继续；为 `true` 且有多个 `serviceCandidates` 时列出候选并询问；查询完整但没有候选时报告已检查的证据后询问 service。`queryStatus` 为 `timed-out` 或 `partial` 时进入第 5 步，不把无候选解释为缺少 service。同一 service 的多个组件或 Tomcat 实例不构成歧义，应全部查询。

现场候选与已确认标识不一致时，报告差异并使用已确认的 component/service 重新查询；不静默采信候选，不把日志归档、备份或历史目录视为 service。

`inspect_port` 返回的监听端口和 PID 是运行事实；component/service 仍按证据强度处理。组件实例目录或独立服务可执行文件属于强证据；Tomcat webapp 只是组件候选。候选唯一且与路由证据一致时继续查询；候选多个或无法取得标识时报告证据并询问，不改用相似名称试探。需要进程详情时直接调用 `inspect_process`，不重新执行 `inspect_service` 的进程发现。

`runtimeInstances.matchConfidence` 为 `strong` 时表示进程命中了已发现的 Tomcat 根目录、Tomcat webapp 或 service 可执行文件等结构化证据；为 `weak` 时仅表示 service/component 文本命中，只能作为可能相关的候选，不能据此断言服务正在运行。存在强证据时，MCP 会排除同次结果中的弱进程候选。Tomcat 部署目录可能按 component 或 service 命名，MCP 应先检查两者并优先用已发现的 Tomcat 路径关联进程。

独立进程按 service 标识匹配，不按 component 名称匹配进程名。`{service}_x86.upx` 等带架构或压缩后缀的进程仍属于该 service；监听端口只采用 MCP 根据远端 PID 关联得到的结果。

`inspect_service.deployedName` 仅表示输入名称经过小写或别名解析后的查询名，不证明服务已经部署。按 `queryStatus`、`deploymentEvidence`、`runtimeEvidence` 和超时警告中的 `inspectionPart` 分别判断部署与运行态，不能用一个失败阶段否定其他已获得的证据。

不要先调用 `discover_services` 再逐个尝试路径，也不要对同一目标固定执行 `inspect_service → search_logs`。只有日志证据表明还需要运行状态时才补充运行态查询：没有 PID 时使用 `inspect_service`，已有 PID 时使用 `inspect_process`。`discover_services` 只用于用户明确要求列出组件或检查部署清单的场景。

标准日志规则没有取得目标文件时，只执行一次有证据约束的降级：

1. 已有 host 和 PID：调用 `inspect_process`。`logCandidates` 中只有一个目标时用 `search_logs.path`；有多个有证据关联的目标文件时，用一次 `search_logs.paths` 查询，最多 20 个，不逐文件重复调用。
2. `inspect_process` 只确认了 systemd unit，且文件日志不可用或不足：用该精确 unit 调用 `search_journal`；不得根据 component/service 拼接 unit。
3. 已有组件日志目录的精确现场路径、但 fd 和 journal 都未定位日志：调用一次 `list_log_directory`，默认一层，确需查看服务子目录文件时最多两层。只用返回的目录或文件作为候选。
4. 进程名、service、日志目录名不一致时报告差异；不删除前缀、截取相似片段或用目录名覆盖已确认 service。

`search_logs.path` 和 `search_logs.paths` 只查询精确普通文件，不递归目录。`requestedTargets` 是本次实际纳入查询的路径数，`searchedFiles` 是实际搜索的普通文件数；折叠后的未查询原因见 `skippedSummary`，显式路径等需要处理的详情见 `skippedTargets`。`targetDiscoveryTruncated` 表示候选达到上限，`truncated` 表示返回内容达到行数上限；两者都不能解释为已经检查了全部证据。压缩日志返回 `unsupported-file-format` 时不得按无匹配处理。

定位结果为空或存在多个无法区分的 component/service 组合时，报告已使用的标识并询问用户，不更换相似名称继续试探。多实例本身不是歧义，应保留全部匹配实例。

### 5. MCP 超时降级

MCP 返回 `timed out`、`queryStatus: timed-out` 或远端查询未完成时：

1. 先检查工具结果中的 `runtimeLensVersion`、`phase` 和 `stage`。进程、目录和 journal 检查会标明对应阶段。结果缺少版本，或原始超时错误没有阶段信息时，报告“MCP 版本或查询阶段无法确认”，不搜索或修改插件文件，也不归因远端服务。
2. 只把 `inspectionPart` 对应的部署路径、进程或端口证据标记为未知，保留其他阶段已返回的事实；旧结果没有 `inspectionPart` 时才将整体运行态视为未知。不解释为服务停止、未部署或日志不存在。
3. 不重复执行同一宽范围调用，也不改用 `discover_services` 扩大扫描。只有已经明确目标主机时，允许指定 host 重试一次。
4. 报告失败的工具、host、component、service 或 port、`inspectionPart`、stage 和已检查的 baseDirs。`deployedName` 只能继续作为 service 查询名。
5. 若当前没有其他受控只读 SSH 能力，请用户在现有服务器终端执行下面的最小只读命令并返回输出；不要安装工具，不读取或展示密码：

```sh
# 已知上游端口但标识未知时，先执行端口反查
ss -lntp | awk -v port='<port>' '{ address=$4; count=split(address, parts, ":"); if (parts[count] == port) print }'
readlink -f /proc/<PID>/cwd
tr '\0' ' ' < /proc/<PID>/cmdline
ls -l /proc/<PID>/fd

ps -ef | grep -F -i -- '<service>' | grep -v grep
# service 无命中时才可单独查 component，结果只作弱候选
ps -ef | grep -F -i -- '<component>' | grep -v grep
readlink -f /proc/<PID>/cwd
tr '\0' ' ' < /proc/<PID>/cmdline
ss -lntp | grep -F -- 'pid=<PID>,'
find <platformRoot>/web/components/<component>.[0-9]*/logs/<service> -maxdepth 1 -type f -name '*.log*' -print
find <platformRoot>/web/components/tomcat*/logs/<component>/<service> -maxdepth 1 -type f -name '*.log*' -print
find <platformRoot>/web/components/tomcat*/logs/<component> -maxdepth 1 -type f -name '<component>.<service>.*.log*' -print
```

已有上游端口时先按精确端口反查 PID；已有 service 时才执行 service 进程查询，component 查询只在 service 无命中时单独执行，不能单独证明目标服务运行。端口必须来自远端证据，不能代入本地源码配置值。若这些等价命令快速返回而 MCP 仍超时，报告为 MCP/SSH 查询层问题，不归因于业务服务。

### 6. 获取问题证据

- 有 TraceId：把已确认的 component/service 一并传给 `trace_request`，优先进行服务范围查询；只有标识未知或需要继续关联时才扩大到环境范围。需要更多上下文时再用 `search_logs` 读取命中的精确目标日志。
- 没有 TraceId：把第 2 步确认的目标标识传给 `search_logs`，再使用接口、最窄时间、错误码或脱敏业务特征搜索。
- 把用户给出的时间视为大概范围。只有时间没有日期时，结合当前问题日期补成明确日期，优先转换为 `time.date`、`time.start`、可选 `time.end` 和 `precision: approximate`；只有旧 MCP 不支持结构化时间时才使用 `timeHint`。以 MCP 返回的 `timeWindow` 为实际查询窗口；窗口无匹配时检查 `nearest`，邻近记录可能说明用户时间存在偏差。`timeHintStatus` 为 `partial`、`unsupported` 或 `unparsed` 时，相关内容可能未经时间过滤，必须根据返回行中的实际时间判断。
- 多个条件必须在同一日志上下文窗口内共同出现时设置 `matchAll: true`；它不会要求所有条件位于同一行。
- 浏览器或测试环境入口的 HTTP 错误：使用 `resolve_nginx_route` 和 Nginx access/error 日志关联 location、upstream、状态码与耗时；上游端口已知而服务未知时调用 `inspect_port`。只有失败层需要源码解释时再读取相关代码。
- 事件订阅或接收异常：按 Platform Layout 的事件订阅规则，查询事件分发端和订阅端的服务日志；不深入消息中间件内部状态。
- 配置差异：使用 `read_service_config` 只查询相关配置键，不读取整份配置。
- 安装结果固定按两步判断，不在第一步反复更换关键词：
  1. 使用 component 和最窄时间线索查询一次 installation 范围；MCP 会合并组件同级失败目录和公共安装日志。目标时间窗内存在与本次安装直接相关的明确错误时，判断安装失败。
  2. 当查询完整、`searchedFiles > 0`、已返回目标时间窗证据且未见明确错误时，判断为“大概率成功”，随即调用一次 `inspect_service` 确认服务状态。服务运行且证据与本次安装一致时确认成功；服务未运行时再调查启动失败；运行态查询超时时表述为“大概率成功，服务状态待确认”。

缺少 `install-result` 等成功标记不等于失败，不为寻找成功标记重复查询。installation 查询无匹配、未覆盖目标时间窗、部分失败或超时时，不能套用“大概率成功”。installation 与运行态是独立证据链，一条超时不否定另一条已经取得的证据。

按 `searchOutcome` 判断空结果：

- `not-searched`：没有实际读取目标文件，证据未知。
- `no-lines-in-window`：已读取的文件在规范化时间窗内没有可解析日志行。
- `no-query-match-in-window`：时间窗内有日志，但查询词未命中；检查 `nearest` 后再决定是否调整时间。
- `no-query-match-unfiltered`：日志时间格式不支持，内容查询没有可靠的时间约束。
- `matched`：只表示取得匹配内容；仍需结合 `queryStatus`、`truncated` 和实例覆盖范围判断完整性。

日志无命中不等于请求没有到达，也不能单独证明安装没有发生；同时考虑时间偏差、日志级别、其他实例、入口拦截以及 TraceId 未生成或未透传。

`searchedFiles: 0` 或 `searchOutcome` 不是 `matched` 时，先检查 `queryStatus`、`skippedSummary`、时间状态、截断状态、component/service 和路径证据，再按本节的 PID、journal、目录顺序降级；未获得直接证据前，不得归因为环境日志命名或落盘规则异常。

### 7. 形成判断

按以下关系组织证据：

```text
本地调用事实
→ 服务与路由映射
→ 当前运行事实
→ 日志或 Trace 事实
→ 原因判断
```

输出：

1. 最可能结论和置信度。
2. 支撑结论的证据链。
3. 尚不能确认的内容。
4. 建议处理方式和验证方法。

建议只能描述为待执行动作，不能声称已经修改或修复测试环境。

## 停止条件

满足以下条件后停止继续查询：

- 已确定失败发生的层级。
- 至少有一条直接证据支持原因。
- 关键替代解释已排除或列为未知。
- 已能给出可验证的下一步。
