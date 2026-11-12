# agent-core 扩展机制源码分析

版本：`release/v0.1.20.post3` / `d4c02c6c52dda8e027af1a08295c5db7f4297fe4`。分析日期：2026-11-09。证据为静态源码与测试源码，本次未运行测试。

## 1. 扩展机制分布在哪几层

| 层次 | 入口与扩展对象 | 解决的问题 | 与本次 V2 的关系 |
| --- | --- | --- | --- |
| 事件行为扩展 | `ExtensionEventBus`、Handler、`EventNext`、Ops | 在宿主定义的业务边界包裹、改写、短路或观察执行 | V2 的共同编程模型 |
| 扩展包生命周期 | `Registry`、`PackageManager`、`Orchestrator`、`Runtime` | 校验、安装、依赖排序、发布、重载、卸载和清理 | AgentServer V2 直接复用；Gateway 部分复用 |
| Agent/Harness 行为组合 | `AgentRail`、`DeepAgentRail`、配置和回调 | 在 Agent 的模型、工具和任务循环中组合行为 | 与事件包并存，有不同注册与作用域 |
| 声明式能力包 | `PluginSpec`、`AgentTemplateSpec`、加载器和 binder | 把工具、MCP、Rails、Skills、提示词及子代理组织为配置和资源 | 不能与 `package_type: extension` 混为同一种包 |
| Harness Provider SPI | `register_harness_provider`、Python entry point、`create_harness` | 接入不同 Agent Harness 实现 | 是运行引擎适配入口，不表示各引擎支持同一事件全集 |
| 资源与领域扩展 | `Runner.resource_mgr`、工具/MCP；团队事件和 Ops | 注册能力对象，在领域边界扩展团队策略与观察能力 | 真实资源执行和团队扩展的衔接点 |

证据：[C01]、[C04]、[C18]、[C19]、[C22]、[C23]、[C24]。其中 `openjiuwen/extensions/` 是可选集成目录，`openjiuwen/core/extension/` 才是本文所述事件扩展包控制面；两者名称相近，职责不同。

## 2. 事件执行：把业务边界开放成可组合的处理链

### 2.1 核心对象

`Event` 包含事件类型和输入；`SessionContext` 提供会话 ID、cwd 和 metadata；`PackageMetadata` 记录宿主绑定的包身份、版本和根目录。事件类型的注册同时提供 matcher、CORE Handler，以及可选输入/输出校验器。扩展注册 Handler 时提供事件名、匹配条件和层级。[C01] [C02]

链条的结构为：

```text
宿主 trigger(Event, SessionContext, 私有 trigger_context)
  → 匹配的 USER Handlers（同层按注册顺序）
  → 匹配的 BUILTIN Handlers（同层按注册顺序）
  → 事件类型的 CORE Handler
  → 结果逐层返回
```

USER 和 BUILTIN 的框架优先级分别为 200、100，CORE 是终端。包的依赖加载顺序可能影响登记顺序，但“包依赖排序”和“事件 Handler 分层执行”是两个独立机制。[C01] [C08] [C38]

### 2.2 Handler 能做什么

Handler 接收 `(event, ops, event_next)`。它可以修改允许变化的输入后继续调用 `await event_next(event)`，在下游结果返回后加工输出，也可以直接返回合法结果、短路后续 Handler。`event_next.to(event, level)` 支持 USER 向 BUILTIN/CORE、BUILTIN 向 CORE 的内向跳转。[C03]

可改写字段由具体事件契约和校验器决定。不能把事件机制概括为“任意修改所有输入输出”：例如 turn 标识、工具调用身份及宿主可信上下文都有专门约束。

`EventNext` 不能改变事件类型，只能在创建它的 asyncio task 及当前 Handler 有效期内使用。一次 trigger 开始时确定匹配结果，向下传入新 Event 时不会重新匹配；嵌套 trigger 会排除该 task 中已活跃的 Handler，避免其直接或间接重入自身。[C01] [C03]

### 2.3 故障处理的真实边界

USER/BUILTIN Handler 的普通异常、非 awaitable 返回或不合法输出，会进入跳过逻辑：未运行下游时继续执行原链；下游已经运行时复用其结果或异常，避免因为上层 Handler 失败而重放下游副作用。初始输入非法、matcher 错误、事件定义校验器异常、CORE 错误等有各自传播路径。取消不属于此处捕获的普通 `Exception`。[C01] [C28]

因此适合写“框架对扩展 Handler 的部分失败提供降级处理，并避免重复运行已执行的下游”；不能写“任何扩展异常都不会影响主业务”。链内短路本身也可能是扩展作者有意改变业务的结果。

## 3. Ops：由宿主提供能力，调用时绑定包和会话

### 3.1 一次构建目录，逐次创建视图

`ops.build` 汇总异步能力方法到 `EventHandlerOpsBuilder`。每个 Bus 只允许成功构建一次，构建后普通事件才可触发；此后不能再改动 `ops.build` Handler 登记。`Registry.init()` 在宿主注册事件和 Handler 后负责触发这一次构建。[C01] [C04] [C05]

普通 Handler 获得独立的 Ops 视图，绑定本次 `PackageMetadata` 和 `SessionContext`。CORE 视图没有扩展包身份，另可接收宿主的私有 `trigger_context`。Ops 的方法按 namespace 组织，注册时要求为异步函数并检查命名和重复方法。[C04]

V2 包在 Ops 构建之后加载，主要负责登记业务 Handler。新增宿主 Ops 命名空间需要在宿主启动构建阶段接线，不能承诺“安装任意插件都能动态增添 Ops 目录”。

### 3.2 当前可见的能力族

| 能力族 | 实现内容与前提 | 证据 |
| --- | --- | --- |
| `ops.package` | 提供当前扩展包相关事实；来自宿主绑定的元数据 | [C25] |
| `ops.tool` | 注册工具、执行工具、查询工具权限；执行依赖匹配会话的活跃 Agent/运行上下文 | [C13] [C26] |
| `ops.agent` | 注册 Agent 声明、创建子代理；spawn 要求活跃 Session 与绑定的 DeepAgent | [C27] [C42] |
| `ops.mcp` | `register`、`connect`、`call`，经对应事件进入 MCP 服务 | [C14] |
| `ops.fs` | `read/write/list/stat/exists/ancestors`，经 `fs.*` 事件访问运行时能力 | [C15] |
| `ops.store` | 包级 JSON CRUD，宿主须配置数据服务 | [C16] [C39] |
| `ops.state` | application/session/auto 作用域状态、版本快照和 CAS 写入 | [C17] [C40] |

Ops 中“查询事实”和“发起动作”需要区分。后者常开启新的事件链，例如 `ops.tool.call()` 触发 `tool.call`；这与 `event_next` 推进当前链不同。文件、MCP、工具等能力还依赖实际运行时绑定与权限实现，EventBus 注册成功不能单独证明其在任意宿主都能执行。[C13] [C14] [C15]

### 3.3 持久数据与进程状态

`JsonStore` 按包保存 JSON 数据，支持跨进程文件锁。`JsonState` 按状态地址保存值与版本，`expected_version` 用于 CAS；state.set 限制写入调用包自己的状态。宿主在 Registry 初始化时绑定服务和使用计数钩子。[C05] [C16] [C17]

数据清理按原因区分：store 在卸载时删除，在重载和停机时保留。state 同样在卸载时清理、重载和停机时保留。不能将这些持久化文件描述为“任意插件 Python 对象都可恢复”或“崩溃后能从旧 Handler 中间继续执行”。

## 4. 扩展包：从来源文件到实际生效记录

### 4.1 包声明与两级依赖

Core 识别 `manifest.json`，要求 `schemaVersion: 1`、`package_type: extension`、包 ID/版本和 extensions 声明；宿主可以要求 `package.domain`，并限定允许的域。`requires.host` 是宿主版本约束，`requires.packages` 是包依赖；每个 extension 的 `requires` 另描述包内依赖。当前 extension runtime 校验为 `backend`，入口文件需位于包根目录内。[C06] [C07]

控制面支持目录和 ZIP 来源，安装副本位于 `<install_dir>/<package.id>/<version>`。ZIP 会检查路径穿越、符号链接和资源预算；复制通过 staging 目录完成，拒绝覆盖已有版本副本，调用方源目录和源 ZIP 不被当作安装垃圾删除。[C07]

`resolve_install_set()` 校验宿主版本和包依赖，作拓扑排序，识别重复 ID、循环和依赖不满足。`Orchestrator.build_plan()` 再按包内依赖排序；卸载按逆序处理，安装/重载推进 generation。[C08] [C38]

### 4.2 四个组件的职责

| 组件 | 负责 | 不应混淆的职责 |
| --- | --- | --- |
| `Registry` | 绑定 Bus、宿主回调、数据服务和安装报告，提供 install/load/uninstall/reload 入口 | 不直接承担所有业务行为 |
| `PackageManager` | 来源打开、manifest、安装副本和文件所有权 | 文件存在不代表包已激活 |
| `Orchestrator` | 将包声明转换为有序 ExtensionPlan | Plan 本身不等于已经生效 |
| `Runtime` | prepare candidate、发布 Handler、记录激活、计数、切换与撤销 | 不能撤销任意外部副作用 |

证据：[C05] [C07] [C08] [C09]。

### 4.3 管理操作本身也经过事件

九类事件为 `package.parse/resolve/query/install/uninstall/reload` 和 `extension.plan/apply/rollback`。业务入口与 CORE Handler 显式推进步骤，总线不会自动推断下一项操作。[C10]

以安装为例，入口触发 package.install，解析来源并 resolve；对依赖允许的包逐项取得操作准入、等待依赖、复制副本、生成 Plan、prepare 和 publish，最后形成 ActivationReport 及报告记录。依赖安装失败会跳过依赖者，独立包可继续处理。[C11]

安装中的 `create_extension()` 返回扩展对象，其 `register(registrar)` 收集 Handler 声明。Core 的受限 registrar 允许 USER、BUILTIN，拒绝 CORE；publish 时才向 Bus 注册并绑定可信包元数据。Python 模块在 prepare 时已实际执行，因此这个限制不能隔离恶意 Python 代码。[C09]

### 4.4 整包发布、热切换和卸载

prepare 阶段使用新模块名加载代码并收集完整 candidate，失败则清理本轮模块，不把半包发布到 Bus。publish 在同步批次内写入 Handler，任一登记失败则撤回本批已登记项。[C09]

`replace_published()` 先登记新批次，成功后切换记录并撤旧 ID；新批次登记失败保留旧 Handler。在切换前开始的调用保留其执行链快照，旧 generation 退役时等待相应调用结束后清理。这个保证适用于 Core 管理的 Handler 发布；完整 reload 还包括 MCP 和宿主资源步骤，不能外推为所有副作用的事务回滚。[C09] [C11]

运行时跟踪包级 in-flight、活跃 Ops 和 generation。卸载会检查其他包依赖和在途使用；忙时立即返回 PACKAGE_BUSY，不默认等待所有调用结束。清理失败保留必要记录供查询或重试，注销 Handler 本身不代表旧调用已经退出。[C09]

### 4.5 多运行域与报告

`PackageInstallReport` 在宿主指定的 YAML 报告路径上记录 owner、run、包操作和有效版本，配合文件锁、依赖等待和启动计划处理跨进程管理事实。`Registry.open_install_dir()` 接收 domain、allowed_domains 和超时参数。[C05] [C12]

这为多个运行域使用共同安装树提供基础，但实际宿主必须接入该报告协议。当前 jiuwenswarm AgentServer 使用 Registry 和报告，Gateway 的管理门面使用 PackageManager 加自己的发布器，不能因此称两侧都完整采用同一跨域生命周期协议。详见另一份报告。

## 5. 已接入真实 Agent 执行的扩展边界

| 边界 | 实际接入与作用 | 条件/限制 |
| --- | --- | --- |
| `turn.start` / `turn.complete` | DeepAgent 在新 turn 开始和结构化终态结果时触发；完成结果可按契约改写输出和 usage | 存在 Session、turn 状态和 Runner 上发布的 Bus；resume 不重复触发 start |
| `turn.step` | ReActAgent 的模型步骤经事件包裹，CORE 通过私有 continuation 执行原模型步骤 | 必须存在有效 turn step 和 Bus，输入身份不可任意改写 |
| `tool.call` | ReActAgent 工具批次进入事件，CORE 驱动原 ability_manager 执行 | 有 Bus 时事件失败向外传播，不重放直接调用 |
| `tool.check` | 通过权限查询和对应 Rail 与工具路径连接 | 支持边界以工具安全实现为准 |
| `prompt.compose` | 最终 post-rail 渲染边界触发，得到本次有序 section 视图 | 会话绑定支持 compose 的 DeepAgent；独立 ReActAgent 可跳过 |
| `prompt.section` | DeepAgent 对每个生效 section 渲染后触发，可改写文本或省略 section | 保留 builder 的原有过滤与排序，结果为本次请求的 section 快照 |
| `prompt.attachment` | Harness 的 prompt attachment manager 使用注入的 extension_bus | 需要 Harness 侧对应 Bus 注入 |
| 团队事件 | `team.monitor_event`、`team.build_policy`；团队只读 `ops.team` | 宿主注册事件/Ops、注入 team extension bus，并提供查询 resolver |

证据：[C29] [C30] [C31] [C32] [C33] [C34] [C24]。这些接线说明事件扩展已有真实执行入口；不意味着任何第三方 Harness 都有同样的原生 DeepAgent 事件覆盖。

## 6. 其他扩展方式与事件包的边界

### Rails

`AgentRail` 是有状态、按实例管理的生命周期钩子集合，有 init/uninit、模型/工具/输入等回调。priority 及可覆写的 callback_priority 控制顺序；DeepAgent 按事件把回调接到内层 ReActAgent 或外层任务循环。[C18]

Rails 适合与单个 Agent 的运行生命周期紧密组合的行为；事件包适合通过宿主注册表统一安装和干预明确业务事件。两者会在工具或提示词等真实路径交汇，但不能把 Rail 的 priority、对象生命周期和扩展包的 generation/卸载规则等同。

### Plugin、AgentTemplate 和声明式装配

`PluginSpec` 包含工具、MCP、Rails、Skills、prompt sections；`AgentTemplateSpec` 还包含身份、模型、可选外部 runtime、子模板等。加载器定位 manifest、解析资源并将路径绝对化，resolver 解析资源，binder 将资源挂到活跃 DeepAgent；失败撤回本批绑定，卸载按资源引用逆序撤销。[C19] [C20]

`@harness_element` 记录 tool/rail/subagent 的构造描述和输入 schema，`register_from_catalog()` 再把它们注册到对应 provider 表。提示词 section 是能力包的组成项，当前 `ElementKind` 并没有独立 PROMPT_SECTION 枚举。[C21] [C41] [C43]

因此“工具包/角色模板”与事件型“系统扩展包”应分开介绍，不能用同名 manifest 就推断两种格式互相兼容。

### Harness Provider 与资源接口

Provider 工厂先解析内置 provider，再查进程内注册，最后查 `openjiuwen.harness_providers` entry point。第三方包实现 SPI 后可以作为新的 Harness 引擎被解析，能力需要按各 provider 的声明判断；DeepAgent 专属 tools/rails/subagents 字段不能直接外推给外部 provider。[C22]

`Runner.resource_mgr` 提供 Agent、工作流、工具、模型、prompt、SysOperation 和 MCP 等资源的登记与移除接口。这些是能力接入基础；它们与事件链、包安装器位于不同层次。[C23]

## 7. 可用于文章的事实与核验入口

适合成为主线的事实：扩展有明确事件边界；Handler 可以前后包裹和按契约短路；宿主能力通过 Ops 开放；包的来源、依赖、候选发布和资源撤销有专门生命周期；同一底层可以由不同宿主接入业务事件。

后续验证可从以下测试开始：事件执行与故障边界 `test_event_bus_execution.py`、`test_event_bus_fault_tolerance.py`；发布/重载 `test_bus_wiring.py`；包与报告 `test_package_events.py`、`test_install_report.py`；真实 Agent Loop 模拟路径 `test_agent_loop_harness_e2e.py`；提示词 `test_prompt_events.py`。本次阅读了相关测试的用例和断言，未执行这些测试。[C28] [C35] [C36] [C37]

不能从本次分析推导零开销、完全隔离、任意代码安全、全端功能一致、全生态兼容或已通过生产压测。

<!-- source-links -->
[C01]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/bus.py:219> "bus.py:219 — class ExtensionEventBus:"
[C02]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/types.py:35> "types.py:35 — class Event:"
[C03]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/event_next.py:17> "event_next.py:17 — class EventNext:"
[C04]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/ops.py:18> "ops.py:18 — class EventHandlerOpsBuilder:"
[C05]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/registry.py:42> "registry.py:42 — class Registry:"
[C06]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/manifest.py:59> "manifest.py:59 — def parse_manifest_mapping("
[C07]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/package_manager.py:71> "package_manager.py:71 — class PackageManager:"
[C08]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/orchestrator.py:27> "orchestrator.py:27 — class Orchestrator:"
[C09]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/runtime.py:139> "runtime.py:139 — class Runtime:"
[C10]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/management/types.py:30> "types.py:30 — PACKAGE_PARSE_EVENT ="
[C11]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/management/handlers.py:380> "handlers.py:380 — async def _install_batch("
[C12]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/install_report.py:99> "install_report.py:99 — class PackageInstallReport:"
[C13]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/tool_ops.py:43> "tool_ops.py:43 — class _ToolOps:"
[C14]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/mcp_ops.py:22> "mcp_ops.py:22 — def register("
[C15]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/fs_ops.py:31> "fs_ops.py:31 — def register("
[C16]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/data/store.py:33> "store.py:33 — class JsonStore:"
[C17]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/data/state.py:63> "state.py:63 — class JsonState:"
[C18]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/rail/base.py:875> "base.py:875 — class AgentRail("
[C19]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/schema/extension_spec.py:135> "extension_spec.py:135 — class AgentTemplateSpec("
[C20]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/extension_binder.py:27> "extension_binder.py:27 — async def apply_extension_hot("
[C21]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/manifest/catalog.py:67> "catalog.py:67 — def harness_element("
[C22]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness_providers/factory.py:112> "factory.py:112 — def resolve_provider("
[C23]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/runner/resources_manager/resource_manager.py:68> "resource_manager.py:68 — class ResourceMgr:"
[C24]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/agent_teams/extensions/events.py:137> "events.py:137 — def register_team_event_types("
[C25]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/package.py:75> "package.py:75 — def register("
[C26]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/tool_register.py:32> "tool_register.py:32 — class _ToolRegistrationOps:"
[C27]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/agent_spawn.py:35> "agent_spawn.py:35 — class _AgentSpawnOps:"
[C28]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/tests/unit_tests/core/events/test_event_bus_fault_tolerance.py:79> "test_event_bus_fault_tolerance.py:79 — async def test_extension_fault_before_downstream_skips_handler("
[C29]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/deep_agent.py:2887> "deep_agent.py:2887 — async def _trigger_turn_complete("
[C30]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/agents/react_agent.py:1121> "react_agent.py:1121 — bus = Runner.get_extension_bus()"
[C31]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/single_agent/agents/react_agent.py:1332> "react_agent.py:1332 — async def _compose_prompt_sections("
[C32]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/deep_agent.py:828> "deep_agent.py:828 — async def compose_prompt_sections("
[C33]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/prompts/prompt_attachment_manager.py:283> "prompt_attachment_manager.py:283 — class PromptAttachmentManager:"
[C34]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/agent_teams/extensions/ops.py:79> "ops.py:79 — class TeamReadView("
[C35]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/tests/unit_tests/core/extension/test_bus_wiring.py:73> "test_bus_wiring.py:73 — async def test_publish_makes_the_whole_package_visible_and_records_it("
[C36]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/tests/unit_tests/core/extension/test_install_report.py:85> "test_install_report.py:85 — async def test_cross_domain_wait_and_reverse_dependency_protection("
[C37]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/tests/unit_tests/core/events/test_agent_loop_harness_e2e.py:220> "test_agent_loop_harness_e2e.py:220 — async def test_tool_round_traces_full_agent_loop_event_order("
[C38]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/extension/selection.py:40> "selection.py:40 — def resolve_install_set("
[C39]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/store.py:38> "store.py:38 — def register("
[C40]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/state.py:39> "state.py:39 — def register("
[C41]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/manifest/models.py:22> "models.py:22 — class ElementKind("
[C42]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/core/events/builtins/handler_ops/agent_register.py:31> "agent_register.py:31 — class _AgentRegistrationOps:"
[C43]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core/openjiuwen/harness/manifest/registration.py:31> "registration.py:31 — def register_from_catalog("
