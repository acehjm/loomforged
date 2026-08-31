# Platform Layout

## 组件、服务与实例

- `component` 表示组件，通常对应组件目录。
- `service` 表示组件中运行或对外提供能力的服务。
- 一个组件可以包含多个服务，不能假设组件与服务一一对应。
- `N` 表示实例标识，目录后缀通常为 `.1`、`.2`。
- 一个服务可以多实例部署；除 Tomcat 外，大多数组件通常只有一个实例。
- `Tomcat` 和 `cluster` 组件需要按多实例处理。

组件目录遵循：

```text
{platformRoot}/web/components/{component}.{N}
```

新增组件遵循该规则时由 Runtime Lens 自动发现，不维护静态组件或服务清单。

## 服务标识

本地源码配置中的 `component`、`componentId` 及其等价形式表示组件标识；`segment`、`segmentId`、`service`、`serviceId` 及其等价形式表示服务标识。点号、横线和下划线命名遵循相同语义。

组件和服务标识按小写使用。用户或源码线索给出大写、混合大小写标识时，Runtime Lens 在查询前统一转换为小写；该规则不适用于 URL、接口路径、日志查询词或 TraceId。

内部服务调用存在两种有效形式：

```text
component + service
service
```

名称确实不一致的少数情况才在 Runtime Lens 的 `serviceAliases` 中维护。

按配置字段的语义分别确定 component 和 service，不要求两者同名，也不能用其中一个覆盖另一个。字段语义不明确时询问用户。

定位独立服务进程时以 service 标识匹配进程命令、可执行文件和工作目录。进程名可能带架构或压缩后缀，例如 `{service}_x86.upx`；component 只用于组件路径约束，不能代替 service 做进程名匹配。

进程可执行文件名、service 标识和日志目录名可能不同。只有源码配置、用户说明、进程打开文件或其他现场证据可以建立映射；不要通过删除前缀、截取名称或相似匹配自动改写 service。

## Tomcat

Tomcat 为多实例。服务可能部署在任意 Tomcat 实例中，Runtime Lens 通过服务部署目录、进程启动参数和 `/proc/{pid}/cwd` 现场建立关联，不静态维护“服务 → Tomcat”映射。

Tomcat 应用目录可能使用 component，也可能使用 service；两者不同时必须同时检查：

```text
{tomcat}/webapps/{component}
{tomcat}/webapps/{service}
```

找到部署目录后，Runtime Lens 优先用对应 Tomcat 根目录关联 Java 进程，不再依赖宽泛的服务文本匹配。

Tomcat 服务日志同时支持按 service 分目录和直接放在 component 目录下两种布局：

```text
{tomcat}/logs/{component}/{service}/*.log
{tomcat}/logs/{component}/{service}/*.log.{rotation}
{tomcat}/logs/{component}/{component}.{service}.{logLevel}.log
{tomcat}/logs/{component}/{component}.{service}.{logLevel}.log.{rotation}
```

已知 component 和 service 时直接查询两种布局。只有 component 时，直接日志必须能从文件名取得 service；仅凭子目录名不能形成强服务证据。归档、备份或历史日志目录不是 service。

## Nginx

Nginx 位于多实例 `cluster.{N}` 组件中。Nginx 配置和日志查询需要检查所有实际存在的 cluster 实例，不能固定使用 `cluster.1`。

## 日志

业务日志文件名通常为：

```text
{component}.{service}.{logLevel}.log
{component}.{service}.{logLevel}.log.{rotation}
```

独立服务也可能按 service 建立日志子目录：

```text
{component}.{N}/logs/{service}/{component}.{service}.{logLevel}.log
{component}.{N}/logs/{service}/{component}.{service}.{logLevel}.log.{rotation}
{component}.{N}/logs/{service}/*.log
{component}.{N}/logs/{service}/*.log.{rotation}
```

日志定位按证据来源递进，不按实现语言分流：先使用公共路径规则；已有 PID 时检查该进程在允许目录内打开的日志文件；文件日志不足且 cgroup 明确给出 systemd unit 时再查询该 unit 的 journal；仍未知时只对已经确认的组件日志目录做最多两层的有界元数据列举。`/proc/{pid}/fd` 是高价值证据，但进程也可能输出到 pipe、journal 或其他日志设施，fd 无候选不等于没有日志。

一个 systemd unit 可能管理多个进程。默认只检查目标 PID；只有问题涉及同单元协作进程时才展开同 unit 的有限进程列表，不把兄弟进程日志自动合并为目标服务日志。

定位日志时同时考虑组件实例、服务实例和 Tomcat 实例。TraceId 是可选的高精度关联条件，不是服务调用排查的前置条件：

- 有 TraceId 时跨服务检索 TraceId。
- 没有 TraceId 时使用已确认的目标标识直接定位服务日志，再结合时间、接口、错误码或业务特征搜索。

## 事件订阅

平台内部事件订阅或接收异常时，优先检查 `component: esc`、`service: eds` 对应的事件分发服务日志，再检查订阅端服务日志。使用事件时间、事件类型、订阅地址、接口路径和脱敏业务标识关联事件的接收、处理、分发与订阅端消费过程。

esc 组件中 eds 服务的具体处理和调用方向以现场配置及日志为准，不根据名称继续推测。当前诊断范围到 esc/eds 服务日志和订阅端服务日志为止，不查询 ActiveMQ 内部 Queue、Topic、消费者、消息积压或投递状态；日志不能证明是否完成分发时明确报告证据不足。

## 安装失败

公共安装工具日志由 Runtime Lens 配置的 `installationLogs` 提供。组件安装失败目录与正常组件目录位于同一层级：

```text
{platformRoot}/web/components/{component}.{N}.faild/*
```

`installationFailurePatterns` 相对于组件父目录解析，不依赖正常的 `{component}.{N}` 目录已经创建。安装失败查询同时读取该组件的失败目录和公共 `installationLogs`。

相关知识：[Environment](./environment.md)
