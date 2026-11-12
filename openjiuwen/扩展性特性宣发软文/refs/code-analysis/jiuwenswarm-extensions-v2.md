# jiuwenswarm Extensions V2 源码分析

版本：`releases/0.2.9.beta3` / `06f70e487e2d478febd621e1b5970a06d4c5c920`。分析日期：2026-11-09。只分析 V2 及其真实宿主调用点，旧扩展不在范围内。本次未启动产品或执行测试。

## 1. V2 在产品中的位置

jiuwenswarm 为 agent-core 的扩展基础提供具体宿主、业务事件和客户端承载。源码有两套进程内运行时：

| 项目 | AgentServer / Worker 侧 | Gateway 侧 |
| --- | --- | --- |
| 目录 | `jiuwenswarm/extensions_v2` | `jiuwenswarm/gateway/extensions_v2` |
| 装配 | `install_extensions(server)` | `install_gateway_extensions(channel, config)` |
| 事件总线 | `SessionStartEventBus`，基于 Core EventBus 增加 session.start 包级登记约束 | 独立 Core `ExtensionEventBus` |
| 包管理 | `ExtensionManager` 委托 Core `Registry` | `GatewayPackageManager` 使用 Core `PackageManager`，调用自身 loader/runtime |
| 主要扩展面 | 会话、历史、消息、提示词上下文、工具/Agent Loop/团队接线、WebUI | 请求路由、连接生命周期、HTTP、应用级 WebUI、浏览器能力桥接 |
| manifest 运行域 | `package.domain: agentserver` | `package.domain: gateway` |
| 安装目录 | 默认工作区下 `extension_pkgs` | 默认同名目录，可通过自己的配置覆盖 |

证据：[J02] [J03] [J04] [J05] [J06] [J07] [J08]。默认可以共用安装树，配置改变后必须核对路径；共享文件树不等于共享内存、Handler 或 EventBus。

`pyproject.toml` 的 openjiuwen 依赖明确绑定 `release/v0.1.20.post3`，与本次 agent-core checkout 的目标分支一致。[J01]

## 2. AgentServer：把 Core 机制装到真实服务

### 2.1 启动、失败与关闭

Worker 生命周期调用 `install_extensions(server)`。装配函数创建 EventBus、包管理器、WebUI Runtime/Transport、会话压缩服务和授权服务；向 Registry 注入宿主事件、Handler、store/state 和资源清理回调，随后加载安装包。[J02] [J09]

初始化失败会记录错误并使 V2 不可用，服务器继续启动。安装包激活有独立异常边界；本地 CLI 启动失败也不作为整个宿主启动失败处理。这属于装配降级，不表示运行期所有扩展错误都会被忽略。[J02]

启动后，装配把 Bus 交给 `Runner.set_team_extension_bus()`，并通过 `Runner.set_extension_bus()` 发布给原生 Agent Loop。bootstrap 注册团队事件及 `ops.team`，并通过宿主的共享团队数据库工厂提供 resolver。[J02] [J10]

关闭时停止本地 CLI、撤回 Runner 的 Agent Loop Bus、关闭压缩服务、释放扩展包、关闭授权服务和 WebUI。Manager 按逆依赖顺序尝试撤销包；清理失败保留事实并报告，不能概括为无条件全部释放成功。[J02] [J03]

### 2.2 管理门面的复用边界

`ExtensionManager` 的 install、load_installed、uninstall 和 reload 委托 Core Registry。它保留宿主配置、会话启动 gate、停机和通知职责；没有再实现一份 Core 的依赖定序、candidate 发布器或生效记录。[J03]

AgentServer 的目录、数据与报告配置包括：

| 配置 | 默认值/含义 |
| --- | --- |
| `extensions.install_dir` | `extension_pkgs`，相对路径锚定用户工作区 |
| `extensions.store_dir` | `extension/store`，包级 JSON 数据 |
| `extensions.state_dir` | `extension/state`，持久状态 |
| `extensions.data_dir` | `extension`，包含 `extension_install_report.yaml` |
| `extensions.install_report` | 轮询、依赖等待和锁超时配置 |

配置显式值优先，环境变量作为目录解析的后备来源。Registry 的 domain 设为 agentserver，allowed_domains 包含 agentserver 和 gateway。[J04] [J03]

WebSocket 管理入口涵盖 `extensions.v2.query/catalog/show/install/uninstall/reload/file.list/file.read`。Adapter 校验参数后调用门面，目录和详情来自本地示例/安装信息；失败时可查询事实核对结果。还存在面向运行中宿主的本地 CLI 和 Web 前端系统插件管理调用。不能据此宣称已提供在线远程插件市场或任意公网包下载。[J11] [J12] [J13]

## 3. AgentServer 开放了哪些业务扩展点

### 3.1 会话生命周期与数据

| 扩展面 | 当前实现 | 使用条件与边界 | 证据 |
| --- | --- | --- | --- |
| `session.start` | 对当前 Worker 的新包激活执行启动通知 | gate 按激活记录和 Handler ID 记忆尝试，要求可信绝对 cwd；不是每次 chat.send 都重复初始化，也不等同每个会话各一次 | [J14] [J15] |
| `session.end/attach/detach` | 运行结束、连接关联建立/解除的宿主事件 | 需要对应宿主可信调用上下文；不同事件的时间点以实现为准 | [J16] [J48] [J49] |
| `session.cwd/root/model/repo/messages/turns/usage` | 事件与 `ops.session.*` 查询代理，读绑定会话事实 | 缺失数据允许返回 None/不可用；usage 来自宿主观测，不承担计费测量 | [J17] |
| `session.append` | 对历史记录追加进行策略处理与持久写入 | transcript-only，不等同投递新输入、执行工具或把文本即时喂给模型 | [J18] |
| `session.send/receive` | 在已授权的跨会话消息发送和目标接收之间开放事件 | send 可拒绝、receive 可消费；成功依据是真实 durable mailbox receipt | [J19] |
| `ops.session.files/read_file` | 委托宿主工作区文件服务 | 服务未提供时返回 unavailable；仍受宿主会话、工作区与访问检查约束 | [J17] |

`SessionStartGate` 属于 Manager/Runtime 生命周期。它识别当前激活对象和发布 Handler 列表变化，并在原生输入前尝试新激活；即使某次尝试取消，也不会简单重放已开始的同一尝试。它适合作为包激活后的初始化入口，文章不应只凭事件名解释成“每个聊天会话新建时固定执行一次”。[J14] [J15]

消息通路由宿主保留原 commit continuation、真实 receipt 和有效期，扩展只见公开载荷；最终是否入队由宿主收据核对。`session.append` 也经过宿主写入边界，而不是把 Handler 任意返回值当成已完成写入。这些机制体现了“扩展策略”和“真实副作用凭证”的分工。[J18] [J19]

### 3.2 提示词：用户上下文与系统提示词属于不同边界

V2 定义 `prompt.context`，宿主在合适的外部 `chat.send` 用户消息上，收集命名上下文块后触发事件，再把结果绑定到本次 UserTurn；输入使用只读集合，返回结果必须通过契约校验。插件可以调整上下文块及关联 instructionFiles。[J20]

调用入口明确排除了 auto_harness、supplement、中断恢复、A2UI 特殊载荷等情况；没有 Bus 时走原路径，事件异常或非法输出时保留原上下文副本。它不是所有消息的全局任意改写钩子。[J20]

系统提示词的 `prompt.compose`、`prompt.section` 属于 agent-core，走原生 ReActAgent/DeepAgent 路径。jiuwenswarm 把 Bus 发布到 Runner 后与这些路径衔接。写作时可表达为“用户上下文和系统提示词在各自边界开放”，不能将三个事件当作相同接口。[J02] [C31] [C32]

### 3.3 上下文用量与命令

`context.usage.updated` 携带一轮已完成对话的 usage 事实，宿主通过调度任务向 Bus 通知，并携带会话、cwd、项目和模型/用量快照。该事件的 CORE 只提供默认 receipt，具体展示由扩展负责。`interface_deep.py` 的用量统计路径实际调用通知函数。[J21] [J22]

`server.run_command` 在宿主选定的命令执行边界开放参数和结果处理。command、origin、presentation 由可信宿主固定，允许改写 args；宿主保留原生命令 continuation 和私有执行结果，以 ref/收据控制原生命令结果的使用，避免重放。它表示已接入的服务命令可扩展，不能泛化为任意 shell 指令或所有命令入口均被接管。[J23] [J50]

### 3.4 已有服务但尚未完成生产接入的能力

| 能力 | 找到的实现 | 当前生产边界 | 可采用的素材表述 |
| --- | --- | --- | --- |
| `session.compact` / `ops.session.compact` | 压缩事件、服务、候选和测试；有显式 bind 逻辑 | `SessionCompactionService` 明确为独立测试绑定，原生 interface_deep 的绑定调用处被注释；未绑定返回 COMPACT_NOT_INTEGRATED 等错误 | “已建立扩展接口与服务实现，原生生产链路接入仍待完成” |
| `session.authorize` / 授权 Ops | 校验活跃包 generation、宿主凭据绑定、限时 opaque handle、生命周期撤销 | 服务要求宿主 bind/unbind；当前没有生产凭据收集器，也不由服务自动收集/发送密钥 | “提供宿主显式绑定凭据后的受限授权机制” |

证据：[J24] [J25] [J26]。Gateway 登录示例自己的 MockIdentity 登录流程属于另一机制，不能拿来证明 session.authorize 已在产品接入。

## 4. WebUI：从包声明到后端树，再到浏览器交互

### 4.1 扩展包声明贡献位置

包的 `ui.items` 声明 `web.slot.contribution`，指定 slot、renderer、instanceKey、scope 等；当前树 renderer 为 `webui-tree`。Catalog 从活跃包的安装副本读取贡献，处理槽位、重复项和设置位置等约束。安装包存在、展示 metadata 存在和 UI 已成功渲染是不同状态。[J27]

槽位由白名单维护，包含 `conversation.input.above/below`、右侧面板、会话标题/动作、assistant meta、应用入口和侧栏、任务区、设置等。application 与 session 有不同寻址：前者绑定浏览器连接，可没有聊天 ID；后者需要会话身份。新增任意插入位置仍需宿主新增槽位与挂载点，扩展不能仅靠 manifest 往任意 DOM 位置挂载。[J28]

### 4.2 下行渲染流程

```text
扩展 Handler
  → ops.ui.render(UiRenderInput)
  → ui.render 事件链
  → CORE：校验 target / slot / tree / props / 预算
  → ActiveRenderRegistry：按实例加锁、分配 revision
  → RenderTransport：webui.render / clear / error 帧
  → Gateway 转发
  → 前端协议处理、实例 Runtime、SchemaRenderer 和槽位宿主
```

后端通过 `ops.build` 注入 `ops.ui.render` 及资源目录、asset URL、release 等方法。渲染树不是任意 Python/React 组件代码；组件与 props 要符合宿主目录和协议。资源文件、iframe 等另走相应组件与资源服务的规则。[J29] [J30] [J31]

CORE 在发送前校验树、props 和大小；按实例维护 revision，发送失败恢复前一登记快照，不跳过版本。实例有容量淘汰和包/会话/连接清理逻辑。当前预算可见树深 8、512 节点、256 KiB 帧以及每会话实例上限 32。预算是协议边界，不能当作吞吐量评测。[J28] [J30]

前端 Runtime 校验并规范化帧，维护实例、revision 与挂载所有权，丢弃过期 render 帧；React 层负责实际挂载和渲染反馈。前端对实例和挂载区分别订阅；这说明存在专门的 UI 状态管理，未提供可量化性能提升结论。[J31] [J32]

`RenderStatus.DELIVERED` 对应后端 transport 发送结果。浏览器最终成功绘制还经过协议校验和组件渲染，不能将后端发送成功直接表述为用户已经看到完整页面。[J30] [J32]

### 4.3 上行交互流程

组件产生 `ui.ready/click/change/select/...`，通过统一 `webui.dispatch` 方法上行。AgentServer Adapter 校验渠道、可信连接、会话和 target，检查声明的贡献，再交给 Runtime 转换为 `ui.*` 事件链。非 ready 交互还有实例存活和动作校验；插件处理后可以通过 ops.ui.render 更新界面。[J33] [J34]

这使业务 Handler 和界面交互共享 Event/Ops 编程模型。`ui.ready` 还用于挂载和重连后的恢复，但每个插件仍须实现所需恢复逻辑，不能推导任意界面或 Python 内存状态都可自动恢复。[J29] [J34]

## 5. Gateway V2：接入层的独立扩展宿主

### 5.1 请求可如何扩展

WebChannel 启动装配 Gateway V2，在请求原生分派前调用 `intercept_gateway_frame`。`gateway.request` 载荷包含 method/params、connection/session/channel/user、headers、request_context 等事实。处理输出支持四种 route：[J05] [J06] [J35]

| route | 实际行为 |
| --- | --- |
| `forward` | 继续既有分派，可采用 Handler 返回的 params |
| `consume` | 扩展提供本地成功响应，停止原生分派 |
| `deny` | 返回错误响应，停止原生分派 |
| `local` | 交给 Gateway 的本地方法表处理 |

零 USER Handler 时有快路径。链执行有 5 秒超时，超时或普通异常时回到原始参数的原生路径。这是 fail-open 机制；如果文章把 Gateway 扩展作为鉴权方案，必须同时保留这个失败策略的限制，不能写成无条件安全闸门。[J06]

Gateway 还暴露 `gateway.disconnect`，用于清理连接级 UI、状态及浏览器桥接记录；HTTP 路径另有相应触发与资源接入逻辑。[J06] [J36]

### 5.2 与 AgentServer 不同的包生命周期

Gateway loader 自己发现包、选择最高安装版本、加载入口并收集 Handler；当前没有走 Core Orchestrator 的包间/包内依赖计划。GatewayRegistrar 只允许 USER，接受 `"*"` 作为空匹配简写；Core registrar 允许 USER 和 BUILTIN。[J07] [J37]

Gateway 的管理门面复用 Core PackageManager 的 ZIP/目录处理、manifest 和安装副本。它没有像 AgentServer 那样初始化 Registry 和 PackageInstallReport，query 返回的 generation 是固定展示值，inflight 为空。这些字段不能解释为已具有 Core generation 和在途保护。[J08]

Gateway Runtime 的 publish 先 `unpublish(old)`，再注册新批次；新批次失败会撤回本次已登记项，但旧批次已被撤销。这与 Core Runtime “新批次成功后再撤旧”的重载保护不同。文章可写 Gateway 支持重读已安装包并重新发布，不能宣称其与 AgentServer 具有相同的失败保留旧版本保证。[J06] [J08]

### 5.3 宿主能力与浏览器桥接

Gateway 通过 `ops.build` 提供本地路由、WebUI、HTTP 和浏览器相关能力。`ops.http.fetch` 有目标主机白名单、时间和响应体预算，默认空白名单拒绝外部请求。[J38]

BrowserBridge 为有 client 声明的包维护 activation generation、connection epoch、资源 URL 和调用身份；可请求 local_storage set/delete 和页面 reload，并通过声明的 requestBindings 将值绑定到目标 Gateway 请求的指定位置。前端校验声明、冲突、命名和作用域，存储 key 按 Gateway 实例/包隔离。[J39] [J40]

这是一组受宿主协议约束的浏览器操作，不应描述成插件可任意执行客户端 JavaScript、访问所有浏览器数据或注入所有请求头。排队返回也不等于浏览器操作已经完成。[J39] [J40]

## 6. 可用于文章的三个源码案例

### TokenWeather：业务事件与界面贡献共同交付

`webui.token-weather-glass` 的 manifest 声明 agentserver 域、backend 入口、输入框上方状态条、应用级设置项和右侧详情面板。实例注册 context.usage.updated、ui.ready 和 ui.click。[J41] [J42]

用量事件发生后，插件通过 `ops.session.usage()` 读取当前会话数据，维护按 session 隔离的 WeatherState 和历史；已挂载时调用 ops.ui.render。页面挂载时 ui.ready 重新查询当前会话；点击详情后创建资源目录、生成详情文档并取得 asset URL，再渲染详情面板。设置控制显示，语言资源包含中英文。[J42]

适合说明：扩展作者把“事件处理 + 宿主能力调用 + UI 插槽 + 资源文件”封装进同一个包。历史主要保存在激活实例内存中，重载/进程重启后重新采集，不能写成完整历史永久恢复。用量为宿主观测，不宣称插件测出了模型未提供的成本或真实计费。[J41] [J42]

### Login Demo：Gateway 行为与应用入口界面联动

示例源码放在 AgentServer V2 的统一 examples 目录，manifest 却声明 gateway；实际加载宿主由 domain 决定。LoginExtension 使用 MockIdentity，注册 gateway.request/disconnect 和 UI 事件，控制应用入口登录页及侧栏用户信息，并通过浏览器桥接保存和绑定 token。[J43] [J44]

适合展示接入层扩展与应用级页面的组合。必须标为示例鉴权流程，不写成产品默认身份系统或已验证的企业级认证能力。

### WebUI Workbench：探索现有插槽和组件

`webui_workbench_v2` 示例包含应用、侧栏、任务区和对话相关的贡献声明及事件处理，可作为展示插槽覆盖范围的阅读与演示入口。需要实际启动后再决定使用哪组截图；不能把示例目录存在写成所有槽位都已完成真实跨进程验收。[J45]

## 7. 证据状态与后续验证

已经通过静态源码核对 AgentServer 装配、Core 委托、会话/命令/提示词边界、WebUI 前后端协议、Gateway 的独立加载发布及示例。部分 AGENTS/设计说明保留较早的阶段描述，本报告对具体机制以当前实现和调用点为准，不用旧进度声明覆盖新代码。

后续定向验证入口包括 `tests/unit_tests/extensions_v2/` 的 assembly、management、session、prompt_context、team_extension_wiring 和 webui 用例，以及 `tests/unit_tests/gateway/extensions_v2/` 的 request、package_management、http_fetch、browser_bridge 和 login_example；前端有 webui 对应测试脚本。它们是可追溯验证材料，本次未执行。[J46] [J47]

宣发前优先验证：一次 TokenWeather 安装到渲染/点击的真实三端闭环、一次 AgentServer 安装/失败重载/卸载、一组 Gateway route 及超时行为。没有这些运行记录前，可以使用“源码已实现”“示例提供”，不采用“已完成全端验收”“生产无感热更新”等表述。

<!-- source-links -->
[C31]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/agents/react_agent.py:1332> "react_agent.py:1332 — async def _compose_prompt_sections("
[C32]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/deep_agent.py:828> "deep_agent.py:828 — async def compose_prompt_sections("
[J01]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/pyproject.toml:21> "pyproject.toml:21 — openjiuwen @ git+https://gitcode.com/openJiuwen/agent-core.git@release/v0.1.20.post3"
[J02]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/assembly.py:48> "assembly.py:48 — async def install_extensions("
[J03]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/management/registry.py:47> "registry.py:47 — class ExtensionManager:"
[J04]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/config.py:23> "config.py:23 — def resolve_install_dir("
[J05]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/assembly.py:41> "assembly.py:41 — async def install_gateway_extensions("
[J06]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/runtime.py:60> "runtime.py:60 — class GatewayRuntime:"
[J07]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/loader.py:52> "loader.py:52 — def load_gateway_packages("
[J08]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/management/registry.py:49> "registry.py:49 — class GatewayPackageManager:"
[J09]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/worker/lifecycle.py:403> "lifecycle.py:403 — await install_extensions(server)"
[J10]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/bootstrap.py:35> "bootstrap.py:35 — def register_event_types("
[J11]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/management/adapter.py:53> "adapter.py:53 — class PackageManagementAdapter("
[J12]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/management/local_cli.py:20> "local_cli.py:20 — async def start_local_cli("
[J13]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/channels/web/frontend/src/services/extensionsV2Api.ts:31> "extensionsV2Api.ts:31 — extensions.v2."
[J14]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/management/session_start.py:35> "session_start.py:35 — class SessionStartGate:"
[J15]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/event_types/session_start.py:31> "session_start.py:31 — class SessionStartEventBus("
[J16]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/session/attach_notifications.py:141> "attach_notifications.py:141 — class ExtensionSessionAttachParticipant:"
[J17]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/handler_ops/session_ops.py:221> "session_ops.py:221 — def register_session_ops("
[J18]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/session/history_events.py:57> "history_events.py:57 — async def"
[J19]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/session/session_message_events.py:110> "session_message_events.py:110 — async def route_session_message("
[J20]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/prompt_context.py:36> "prompt_context.py:36 — async def prepare_prompt_context("
[J21]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/event_types/context_usage.py:76> "context_usage.py:76 — def notify_context_usage("
[J22]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:20033> "interface_deep.py:20033 — notify_context_usage("
[J23]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/commands/run_command_events.py:110> "run_command_events.py:110 — async def dispatch_server_run_command("
[J24]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/session_compaction/service.py:30> "service.py:30 — class SessionCompactionService:"
[J25]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:17440> "interface_deep.py:17440 — # self._bind_extension_compaction(context.session_id, context=context)"
[J26]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/session_authorization/service.py:54> "service.py:54 — class SessionAuthorizationService:"
[J27]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/contributions.py:72> "contributions.py:72 — class WebUICatalogService:"
[J28]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/constants.py:78> "constants.py:78 — SLOT_SPECS:"
[J29]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/runtime.py:46> "runtime.py:46 — class WebUIRuntime:"
[J30]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/core_handlers/render_core.py:31> "render_core.py:31 — def build_render_core_handler("
[J31]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/channels/web/frontend/src/features/webui/renderer/SchemaRenderer.tsx:16> "SchemaRenderer.tsx:16 — export"
[J32]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/channels/web/frontend/src/features/webui/runtime/createWebUIRuntime.ts:55> "createWebUIRuntime.ts:55 — export function createWebUIRuntime("
[J33]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/adapter.py:35> "adapter.py:35 — class WebUIDispatchAdapter("
[J34]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/action_validation.py:27> "action_validation.py:27 — def validate_upstream("
[J35]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/channel_manager/web/web_connect.py:1904> "web_connect.py:1904 — _visited, params = await intercept_gateway_frame("
[J36]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/webui/http.py:22> "http.py:22 — async def"
[J37]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/registry.py:28> "registry.py:28 — class GatewayRegistrar:"
[J38]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/config.py:29> "config.py:29 — class HttpPolicy:"
[J39]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/webui/bridge.py:91> "bridge.py:91 — class BrowserBridge:"
[J40]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/channels/web/frontend/src/features/webui/client/createClientCapabilityHost.ts:65> "createClientCapabilityHost.ts:65 — export function createClientCapabilityHost("
[J41]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/token_weather_glass/manifest.json:3> "manifest.json:3 — "package_type":"
[J42]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/token_weather_glass/token_weather_glass/extension.py:32> "extension.py:32 — class TokenWeatherGlass:"
[J43]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/auth_login_demo/manifest.json:8> "manifest.json:8 — "domain":"
[J44]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/auth_login_demo/auth_login_demo/extension.py:28> "extension.py:28 — class LoginExtension:"
[J45]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/webui_workbench_v2/manifest.json:3> "manifest.json:3 — "package_type":"
[J46]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/tests/unit_tests/extensions_v2/test_assembly.py:38> "test_assembly.py:38 — def test_"
[J47]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/tests/unit_tests/gateway/extensions_v2/test_gateway_package_management.py:208> "test_gateway_package_management.py:208 — async def test_reload_republishes_the_installed_copy("
[J48]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/session/end_notifications.py:35> "end_notifications.py:35 — class ExtensionSessionEndParticipant:"
[J49]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/session/detach_notifications.py:28> "detach_notifications.py:28 — async def"
[J50]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/event_types/server_run_command.py:40> "server_run_command.py:40 — class ServerRunCommandInput:"
