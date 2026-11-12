# 扩展性源码分析与文章素材索引

分析日期：2026-11-09。用途：为扩展性宣发文章提供事实、案例和源码证据；本目录不是文章正文或已确认大纲。

## 版本与分析范围

| 仓库 | 本地位置 | 分支 | 本次分析提交 |
| --- | --- | --- | --- |
| agent-core | `D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/agent-core` | `release/v0.1.20.post3` | `d4c02c6c52dda8e027af1a08295c5db7f4297fe4` |
| jiuwenswarm | `D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm` | `releases/0.2.9.beta3` | `06f70e487e2d478febd621e1b5970a06d4c5c920` |

两个 checkout 在分析前均无未提交变更。jiuwenswarm 的依赖配置确实指向上述 agent-core 分支，见 [J01]。报告基于这两个固定提交，后续分支更新须重新核对。

agent-core 重点分析 `core/events`、`core/extension`，并追踪真实 Agent Loop、Harness、团队扩展接线；补充区分 Rails、Plugin/AgentTemplate、Harness Provider 和资源抽象。没有逐一审计所有模型、存储、工作流和 RSI 插件实现。

用户所称 `extension_v2`，对应源码中的 `extensions_v2`。jiuwenswarm 仅分析这套 V2 机制，包括 AgentServer 侧、Gateway 侧及其直接依赖的 WebUI、会话和命令接入点。未展开旧 `jiuwenswarm/extensions/` 的实现，也未将旧扩展的能力计入 V2。

## 阅读顺序

1. [两库关系与宣发素材](relationship-and-article-materials.md)：先看分工、能力对照、可采用表述、案例与待验证项。
2. [agent-core 扩展机制](agent-core.md)：看事件链、Ops、包生命周期，以及其他层次的扩展入口。
3. [jiuwenswarm Extensions V2](jiuwenswarm-extensions-v2.md)：看宿主装配、业务接入、WebUI 闭环和 Gateway 差异。

各报告使用 `[Cxx]`、`[Jxx]` 链接定位源码文件及行号。链接指向当前本地 checkout；临时目录移走后需用本页的提交和文件路径重新定位。设计文档仅用来寻找入口，关键结论以实际实现和调用方为依据。

## 最重要的结论

- agent-core 提供通用事件执行模型与扩展包管理：事件、Handler、`EventNext`、Ops、manifest、依赖定序、候选发布和生命周期记录。
- jiuwenswarm 的 AgentServer V2 将 Core 基础接到真实宿主：会话查询、消息与历史、提示词上下文、团队接线，以及 WebUI 渲染和交互。
- Gateway V2 使用独立 EventBus 和运行时，复用 Core 事件模型及包文件管理。它与 AgentServer 的加载器、发布器和生命周期保证有差异。
- 后端行为扩展与界面贡献可以由一个扩展包共同声明。TokenWeather 示例已经展示用量事件 → 会话查询 → 插槽渲染 → 点击详情的源码闭环。
- `session.compact` 的生产绑定仍被禁用；`session.authorize` 的服务要求宿主显式绑定凭据，当前没有生产凭据收集器。两者不能作为当前产品开箱即用的案例。

## 证据等级与验证记录

本文中的“已实现”表示在上述提交中找到了实现及必要调用关系；“条件支持”表示依赖宿主绑定、配置或特定运行时；“未接入”表示存在接口或服务实现，但真实产品入口未启用。分析性归纳和建议选题均不视为实测结果。

实际完成了源码预检、Git 版本与工作区核对、关键实现和调用方阅读、相关测试源码阅读，以及产物链接和行号检查。本次没有安装依赖、启动服务、执行仓库测试或进行浏览器联调。仓库中的测试是后续验证入口，不代表本次测试通过，也不能单凭这些代码承诺性能、跨端兼容性或生产可靠性。

<!-- source-links -->
[J01]: <D:/code/personal/write_wechat_article/openjiuwen/扩展性特性宣发软文/tmp/jiuwenswarm/pyproject.toml:21> "pyproject.toml:21 — openjiuwen @ git+https://gitcode.com/openJiuwen/agent-core.git@release/v0.1.20.post3"
