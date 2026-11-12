# agent-core 与 jiuwenswarm V2 的关系及宣发素材

适用版本：agent-core `d4c02c6c52dda8e027af1a08295c5db7f4297fe4`，jiuwenswarm `06f70e487e2d478febd621e1b5970a06d4c5c920`。整理日期：2026-11-09。本文提供选题素材和事实边界，尚未形成文章大纲或正文，也未进行运行实测。

## 1. 两库各自提供什么

agent-core 定义扩展如何参与执行、如何取得宿主能力，以及扩展包如何被加载和管理。jiuwenswarm V2 把这些机制接入具体服务、会话和浏览器界面。其 AgentServer 和 Gateway 分别持有独立的运行时，使用不同程度的 Core 复用。[C01] [C05] [J02] [J06] [J08]

```text
agent-core
  core/events：Event + Handler + EventNext + Ops
  core/extension：manifest / PackageManager / Registry / Runtime
  Agent Loop、Harness、Agent Teams：真实执行点与领域事件
          │ 被宿主使用或接线
          ├─ jiuwenswarm AgentServer V2
          │    ExtensionManager → Core Registry / Runtime
          │    会话、消息、历史、prompt.context、用量、命令
          │    WebUI 树、渲染协议、资源与交互
          │          ↕ Gateway 转发 / Web 前端
          └─ jiuwenswarm Gateway V2
               Core EventBus + PackageManager
               独立 loader / runtime / publish
               请求路由、连接、HTTP、浏览器桥接、应用级 UI
```

这里的两套 Bus 不会因为事件名字相同就自动互通。跨进程需要请求适配、下行帧与上行 webui.dispatch 等明确桥接；浏览器由前端协议、实例 Runtime 和组件 Renderer 承载。[J29] [J33] [J35]

## 2. 复用关系与差异对照

| 机制 | agent-core | jiuwenswarm AgentServer V2 | jiuwenswarm Gateway V2 |
| --- | --- | --- | --- |
| Event/Handler/Next/Ops 模型 | 定义并实现 | 直接使用，并扩展宿主事件 | 直接使用，独立 Bus |
| CORE 默认行为 | 事件类型注册时绑定 | 部分用 Core，部分由会话/WebUI/命令宿主提供 | Gateway 自己提供路由/WebUI 等 CORE |
| 扩展 registrar | USER、BUILTIN；禁止 CORE | 经 Core candidate 加载 | 自己的 registrar，只允许 USER |
| 包文件处理 | manifest、ZIP、安装副本 | 委托 Registry 内的 PackageManager | 复用 PackageManager |
| 依赖计划 | 包间 resolve + 包内 Orchestrator | 委托 Core | loader 自己处理入口；未复用同一依赖计划 |
| Handler 发布 | candidate 完整准备后同步发布 | 复用 Core | 自己登记并在失败时撤本批 |
| 重载保留旧 Handler | 新批次登记成功后撤旧，登记失败保留旧 | 复用 Core 的相应保证 | publish 先撤旧，失败后不具有同等保证 |
| in-flight/generation | Runtime 计数与代际管理 | 使用相同 Runtime | query 中 inflight 空、generation 固定展示值；不具有同等语义 |
| 跨域安装报告 | 提供 YAML 报告和 owner/run/依赖机制 | 通过 Registry 接入 | 管理门面没有完整接入相同报告链 |
| UI 插槽、组件、传输 | 不负责产品界面 | V2 实现宿主事件和渲染服务 | V2 实现应用级 UI 与桥接 |

证据：[C09] [C12] [J03] [J07] [J08] [J28] [J29] [J37]。表中差异尤其影响“统一热更新”“完整跨域依赖”“全场景生命周期一致”等宣传用语。

## 3. 容易混淆的术语

| 术语 | 本次代码中的确切含义 | 写作建议 |
| --- | --- | --- |
| Event | 宿主注册并在业务入口触发的事件 | 举出实际触发点，避免说“任意环节随便挂” |
| Handler | 匹配事件并决定是否继续、如何返回的处理函数 | 强调按事件契约开放改写与短路 |
| Ops | 宿主启动时构建、调用时绑定上下文的能力视图 | 不把它与推进当前链的 EventNext 混用 |
| Extension package | `package_type: extension` 的事件型系统扩展包 | 与下方 PluginSpec 能力包分开说明 |
| Plugin / AgentTemplate | Harness 的功能能力包 / Agent 角色模板 | 适合解释工具、Skills、MCP 和角色装配 |
| Rail | Agent 实例上的生命周期钩子与行为组件 | 不套用包级 generation/卸载语义 |
| Harness Provider | 执行引擎 SPI 与 entry point | 不承诺全部 provider 支持 DeepAgent 原生事件全集 |
| package.domain | extension 包运行宿主的选择 | 示例文件位置不能代替 domain 判断 |
| application scope | 浏览器连接级寻址，可无 chat ID | 不等同所有用户共享的全局界面状态 |

证据：[C03] [C04] [C18] [C19] [C22] [J07] [J28]。

## 4. 建议优先使用的文章主张

以下是有源码支撑的候选事实表达，不是已经确认的文章文案。

| 可以表达的主张 | 给读者的具体含义 | 支撑与应保留的条件 |
| --- | --- | --- |
| “扩展可以在明确的业务事件上参与执行。” | 可以在下游前后处理输入输出，也能按契约直接响应 | EventNext 与校验器；仅限已注册、已触发的事件 [C01] [C03] |
| “工具执行、提示词组装和团队策略都有可追踪的扩展入口。” | Agent 行为具有不同粒度的定制点 | 原生 ReAct/DeepAgent 与团队宿主接线条件 [C29] [C31] [C32] [C24] [J10] |
| “扩展包有专门的安装和生命周期管理。” | 包含来源校验、依赖计划、候选发布、生效记录及卸载检查 | Core/AgentServer 范围；清理和副作用存在边界 [C07] [C08] [C09] |
| “扩展能够把业务逻辑和产品界面一起交付。” | 同一包监听用量事件、查询会话数据、声明插槽和返回渲染树 | TokenWeather 为源码示例；使用现有组件/插槽 [J41] [J42] |
| “相同事件模型能服务 AgentServer 和 Gateway 两类宿主。” | 业务运行与接入层各有具体扩展面 | 独立 Bus、明确协议衔接；生命周期实现存在差异 [J02] [J06] [J08] |
| “宿主通过 Ops 向扩展开放上下文相关能力。” | 扩展可在绑定的会话和包身份下查询或执行动作 | 需要真实运行时/数据服务/权限绑定 [C04] [J17] [J29] |

文章可以围绕一个读者问题展开：“想给智能体加一条规则、接一项能力，再把结果放进工作台，需要改哪些地方？”随后分别用事件 Handler、Ops、扩展包和 WebUI 展示接入方式。这是写作建议，代码本身没有提供接入成本或人效评测。

## 5. 案例素材卡

### A. TokenWeather：从数据变化到可交互界面

读者场景：希望在输入区看到会话上下文占用，并点击查看明细。

可展示的调用链：

1. manifest 声明 agentserver 扩展入口及状态条、设置项、详情插槽。
2. 宿主在用量统计后通知 `context.usage.updated`。
3. 插件 Handler 经 `ops.session.usage()` 读取观测值，更新会话内状态。
4. `ops.ui.render()` 发起 ui.render 事件，宿主校验并发送渲染树。
5. 前端在声明的插槽中渲染，点击通过 webui.dispatch 上行。
6. 插件生成详情资源并渲染右侧面板；ui.ready 用于挂载后重新读取。

证据：[J21] [J22] [J29] [J30] [J33] [J41] [J42]。可取素材：manifest 局部、register/on_usage 局部、实际状态条和详情截图。后两类截图需要后续启动演示才能取得。本例不能证明持久完整历史、计费精度或资源使用量下降。

### B. 提示词规则：整篇组装与局部 section 分开控制

读者场景：希望在特定模型或 section 上调整智能体规则。

Core 的 prompt.compose 在最终组装边界提供本次 section 视图，prompt.section 可按 name 匹配并修改文本或省略 section。compose 的匹配支持 model/trait，实际是否传入这些事实仍由触发方决定；当前 ReAct 触发方的部分可选事实为空。V2 的 prompt.context 则处理符合条件的外部用户上下文块。[C31] [C32] [J20]

可采用一个明确标为“解释性示例”的场景：对指定 section 加入团队约定，再继续默认组装。不要将假设代码说成已有客户实践，也不能宣称当前插件接口已覆盖任何 provider 的提示词全过程。

### C. 团队规则与观测：底层能力如何被宿主复用

读者场景：想调整团队 policy，或读取团队状态供扩展展示。

Core 定义 team.build_policy、team.monitor_event 和只读 ops.team；jiuwenswarm bootstrap 注册它们并提供数据库 resolver，assembly 将 Bus 注入团队运行入口。适合用来解释两库的依赖方向：领域契约和执行基础来自 Core，宿主负责装配与真实资源绑定。[C24] [J02] [J10]

可展示“源码接线案例”，尚不能写成已运行的业务解决方案。ops.team 的读取不意味着插件已拥有任意修改任务或成员的能力。

### D. Gateway 登录示例：界面和请求处理可由包联动

Login Demo 用 gateway 域扩展处理请求、登录入口 UI 和浏览器 token 绑定。素材可以是 domain 声明、gateway.request Handler 与登录/侧栏 UI。[J43] [J44]

需标注 MockIdentity 示例，且说明 Gateway 的超时/异常会放行原路径。它不适合支撑“默认企业级鉴权”“故障时始终拒绝请求”或“session.authorize 已开箱即用”的主张。[J06] [J26]

## 6. 应收窄或暂缓的宣传表述

| 不宜直接使用 | 源码事实 | 可替代表述 |
| --- | --- | --- |
| “一切皆插件，任意环节都能扩展” | 能力由具体事件触发点、Ops 和 UI 白名单决定 | “开放工具、提示词、会话、团队与界面等具体扩展入口” |
| “任意插件都能安全运行” | backend Python 在宿主进程加载执行，registrar 不是沙箱 | “对登记层级、载荷、来源路径和部分资源访问提供校验” |
| “所有扩展均可无感热更新，失败完全回滚” | Core Handler 热切换与 Gateway 发布不同；副作用不能任意撤销 | “Core/AgentServer 支持候选发布和 Handler 热切换，具体清理按生命周期处理” |
| “装上就能控制所有 Harness” | 原生与外部 provider 的能力和接线不同 | 指明使用的原生 Harness/宿主路径 |
| “跨域依赖和生命周期已全链统一” | AgentServer 接 Registry 报告，Gateway 未完整接同一链 | “共享包格式和默认安装树，按 domain 交给不同宿主” |
| “插件可接管生产自动压缩” | 生产 compact 绑定调用禁用 | “压缩扩展接口和服务已建立，生产接入待完成” |
| “插件可直接取得用户密钥” | 授权服务依赖宿主显式绑定，仅提供受限 handle | 只描述已绑定条件下的授权机制，不宣称自动收集凭据 |
| “UI 无需宿主改动，随处扩展” | 只能使用现有槽位/组件/协议 | “可在已开放插槽内贡献符合协议的界面” |
| “已验证高性能、生产稳定、全端兼容” | 本次无运行/性能/跨端记录 | 使用源码实现事实，另补可复现验证材料 |

证据：[C01] [C09] [J06] [J08] [J24] [J25] [J26] [J28] [J31]。

## 7. 写作前还需补什么

| 验证/素材 | 目的 | 当前状态 |
| --- | --- | --- |
| 固定版本启动 AgentServer、Gateway、Web 前端，安装 TokenWeather 并点击详情 | 将静态闭环变成可复现演示与截图 | 本次未执行 |
| Core/AgentServer 成功安装、失败 candidate、失败重载、busy 卸载 | 验证生命周期承诺的实际范围 | 找到实现与相关测试，未运行 |
| Gateway reload 失败、超时、deny/consume/forward/local | 明确接入层行为差异 | 找到实现，未运行 |
| prompt.context 适用请求及跳过分支；prompt.section 实际改写 | 验证提示词示例触发条件 | 找到实现与测试，未运行 |
| 确认对外名称、计划发布时间和默认启用的产品范围 | 把版本实现事实转换为发布叙事 | 源码不足以决定，需要产品信息 |
| 竞品比较与性能收益 | 支撑兼容性、领先性或效率数据 | 不在本次源码分析范围，未作结论 |

后续写作优先使用 A、B、C 三组素材。D 更适合补充说明 Gateway 扩展面，并保留示例及失败策略条件。

<!-- source-links -->
[C01]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/bus.py:219> "bus.py:219 — class ExtensionEventBus:"
[C03]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/event_next.py:17> "event_next.py:17 — class EventNext:"
[C04]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/ops.py:18> "ops.py:18 — class EventHandlerOpsBuilder:"
[C05]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/registry.py:42> "registry.py:42 — class Registry:"
[C07]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/package_manager.py:71> "package_manager.py:71 — class PackageManager:"
[C08]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/orchestrator.py:27> "orchestrator.py:27 — class Orchestrator:"
[C09]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/runtime.py:139> "runtime.py:139 — class Runtime:"
[C12]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/install_report.py:99> "install_report.py:99 — class PackageInstallReport:"
[C18]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/rail/base.py:875> "base.py:875 — class AgentRail("
[C19]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/schema/extension_spec.py:135> "extension_spec.py:135 — class AgentTemplateSpec("
[C22]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness_providers/factory.py:112> "factory.py:112 — def resolve_provider("
[C24]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/agent_teams/extensions/events.py:137> "events.py:137 — def register_team_event_types("
[C29]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/deep_agent.py:2887> "deep_agent.py:2887 — async def _trigger_turn_complete("
[C31]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/agents/react_agent.py:1332> "react_agent.py:1332 — async def _compose_prompt_sections("
[C32]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/deep_agent.py:828> "deep_agent.py:828 — async def compose_prompt_sections("
[J02]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/assembly.py:48> "assembly.py:48 — async def install_extensions("
[J03]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/management/registry.py:47> "registry.py:47 — class ExtensionManager:"
[J06]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/runtime.py:60> "runtime.py:60 — class GatewayRuntime:"
[J07]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/loader.py:52> "loader.py:52 — def load_gateway_packages("
[J08]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/management/registry.py:49> "registry.py:49 — class GatewayPackageManager:"
[J10]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/bootstrap.py:35> "bootstrap.py:35 — def register_event_types("
[J17]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/handler_ops/session_ops.py:221> "session_ops.py:221 — def register_session_ops("
[J20]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/prompt_context.py:36> "prompt_context.py:36 — async def prepare_prompt_context("
[J21]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/event_types/context_usage.py:76> "context_usage.py:76 — def notify_context_usage("
[J22]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:20033> "interface_deep.py:20033 — notify_context_usage("
[J24]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/session_compaction/service.py:30> "service.py:30 — class SessionCompactionService:"
[J25]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:17440> "interface_deep.py:17440 — # self._bind_extension_compaction(context.session_id, context=context)"
[J26]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/session_authorization/service.py:54> "service.py:54 — class SessionAuthorizationService:"
[J28]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/constants.py:78> "constants.py:78 — SLOT_SPECS:"
[J29]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/runtime.py:46> "runtime.py:46 — class WebUIRuntime:"
[J30]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/core_handlers/render_core.py:31> "render_core.py:31 — def build_render_core_handler("
[J31]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/channels/web/frontend/src/features/webui/renderer/SchemaRenderer.tsx:16> "SchemaRenderer.tsx:16 — export"
[J33]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/webui/adapter.py:35> "adapter.py:35 — class WebUIDispatchAdapter("
[J35]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/channel_manager/web/web_connect.py:1904> "web_connect.py:1904 — _visited, params = await intercept_gateway_frame("
[J37]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/gateway/extensions_v2/registry.py:28> "registry.py:28 — class GatewayRegistrar:"
[J41]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/token_weather_glass/manifest.json:3> "manifest.json:3 — "package_type":"
[J42]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/token_weather_glass/token_weather_glass/extension.py:32> "extension.py:32 — class TokenWeatherGlass:"
[J43]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/auth_login_demo/manifest.json:8> "manifest.json:8 — "domain":"
[J44]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/jiuwenswarm/extensions_v2/examples/auth_login_demo/auth_login_demo/extension.py:28> "extension.py:28 — class LoginExtension:"
