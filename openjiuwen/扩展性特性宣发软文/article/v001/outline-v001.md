# 从「开发者友好」走向「RSI友好」，openJiuwen 发布 RSI 原生 AgentOS，让 Agent 自由变身，持续迭代！

从使用 WorkSwarm 时想加个新功能说起。说明 Agent 做出的改动要能接入应用，支持试用和按反馈继续调整，由此引出面向递归自我改进的 **RSI 原生 AgentOS**。介绍覆盖**运行全周期**的多类型扩展点，以及**热插拔、非侵入式接入、版本管理和回退**。接着说明这套机制怎样用在 WorkSwarm 这个**基于 openJiuwen RSI 原生 AgentOS 构建的 Agent 应用**里。Agent 做出的**扩展包**装入 WorkSwarm 后叫**系统插件**，启用后就能试用，再按反馈修改。

## 从 WorkSwarm 把自己变成桌宠说起，看看 RSI 原生 AgentOS 怎么让 Agent 给自己加功能

从一个日常需求说起。想随时跟 Agent 聊两句，或者交代个简单任务，桌面上有个桌宠就够了。遇到复杂任务，再打开 WorkSwarm 工作台。但默认的 WorkSwarm 还没有桌宠形态，能不能让 Agent 自己加上？

把需求告诉 Agent，让它自己生成扩展包，再在 WorkSwarm 中作为「应用形态」系统插件启用。点一下按钮，工作台收起，变成能对话的蜜蜂或胶囊桌宠。双击桌宠，就能回到工作台接着聊。下一节再拆解 RSI 原生 AgentOS 怎样让这样的改动生效。

【视频占位 视频1：一个系统插件，让 WorkSwarm 在工作台和桌宠形态之间切换｜启用「应用形态」系统插件后，从工作台切换为蜜蜂或胶囊桌宠。在桌宠中发起对话，再切回工作台继续同一会话】

## 拆解 openJiuwen RSI 原生 AgentOS：扩展包怎样改变界面、网关、服务端与 Agent 行为？

承接上一节 WorkSwarm 把自己变成桌宠的例子，先交代扩展接在哪里，再说明各环节能扩展什么、扩展包怎么生效，最后列出具体事件和 Ops。

介绍 Web 客户端、Gateway 和 Agent 层各自的职责，以及三个层次提供的扩展入口。

【图片占位 图1：openJiuwen RSI 原生 AgentOS 架构图｜Web 客户端、Gateway 和 Agent 层的职责、连接关系及各自的扩展入口。】

按 Client、Gateway、AgentServer、Team 和 Agent 梳理扩展能力，并交代扩展包清单中的版本、依赖、代码入口和界面位置。

【图片占位 图2：openJiuwen RSI 原生 AgentOS 扩展能力一览｜左侧是扩展包目录与清单，右侧是 Client、Gateway、AgentServer、Team 和 Agent 五个环节的扩展能力。】

沿扩展包安装、确定版本与加载顺序、注册处理函数、响应事件的流程，说明 Gateway 和 AgentServer 如何分别加载扩展并调用 Ops。

【图片占位 图3：openJiuwen RSI 原生 AgentOS 扩展包生效原理｜扩展包从安装、选择版本到加载代码、注册处理函数，再到响应事件和按需更新界面的流程。】

【图片占位 图4：扩展事件与 Ops 能力速查表｜左侧是各类扩展事件，右侧是处理函数可调用的 Ops。表中区分已支持和规划中的条目。】

再按会话与消息、Agent 执行、Team 协作、界面交互、网关与服务端等类别梳理扩展事件，并列介绍处理函数可调用的平台能力（Ops）。Team 单列协作规则构建（team.build_policy）与监控事件（team.monitor_event），以及通过 ops.team 只读查询团队信息、成员、任务和任务依赖的能力。

## WorkSwarm 系统插件实战：从创建、安装到故障回退

按创建、安装和启用系统插件，再到从存档点恢复配置的顺序介绍。

**章导语安排**　添加章导语。

**章导语概述**　从 RSI 原生 AgentOS 的扩展机制过渡到 WorkSwarm 中创建、启用和试用系统插件，以及故障时如何恢复配置。

### 3.1 和 Agent 对话，边做边调试你的第一个系统插件

介绍用 Skill 对话创建和手动编写两种方式，推荐前者。用 Token Weather 演示生成系统插件、在 WorkSwarm 里启用和试用，再按反馈修改。简述依赖和版本要求。

【视频占位 视频2：用自然语言创建和迭代 Token Weather 系统插件｜用自然语言告诉 Agent 想做什么，生成 Token Weather 系统插件，在 WorkSwarm 中启用并试用，再按反馈调整。】

### 3.2 系统插件怎么安装和启用？

概述通过安装目录、扩展页面和 `/extension` 安装系统插件的三种方式，以及安装后如何启用、禁用并确认效果。

【视频占位 视频3：WorkSwarm 系统插件的三种安装方式与日常管理｜可以把解压后的系统插件文件放入安装目录，从「扩展 → 系统插件」页面下载安装，或用 `/extension install` 命令安装。安装后，可以在「我的扩展」里启用或禁用系统插件。】

### 3.3 系统插件引起故障，怎么恢复原来的配置？

把**可回退**作为试用系统插件的关键能力。以系统插件引发 WorkSwarm 故障为例，说明如何选择故障前的存档点、恢复配置，并验证页面能否正常使用。

【视频占位 视频4：从存档点恢复 WorkSwarm 的系统插件配置｜系统插件导致 WorkSwarm 运行异常后，**选择一个存档点，将系统插件配置恢复到当时的状态**。】

## RSI 原生 AgentOS 的扩展能做什么？从定制自己的 Agent 应用，到支持团队协作和企业接入

介绍 RSI 原生 AgentOS 在界面、单 Agent、Swarm 协作和企业接入中的扩展能力，并说明这些能力在 WorkSwarm 的系统插件里怎么用。

**章导语安排**　添加章导语。

**章导语概述**　从界面定制和单 Agent 的工作方式说起，重点说明团队可按项目定制分工和交接，企业可按部署要求调整访问管理和 Agent 的运行方式。

### 4.1 前端界面定制：让 Agent 定制工作台界面，有你的风格，用着更顺手

先说明前端扩展可以调整 Agent 应用的外观和交互，再说明在 WorkSwarm 中如何生成并启用主题背景系统插件，以及怎样切换动态主题。

【视频占位 视频5：生成主题背景扩展包，在 WorkSwarm 中切换动态主题｜生成主题背景扩展包，装进 WorkSwarm 并启用对应的系统插件，再到设置页切换动态主题。】

### 4.2 Agent Harness 调整：让 Agent 的工作过程看得见，做事方式也能按需调整

先概述单 Agent 的会话与执行扩展，再说明在 WorkSwarm 中如何用自然语言让 Agent 生成上下文管理扩展包，并启用对应的系统插件，统一统计、查看和管理会话上下文。

【视频占位 视频6：用自然语言生成上下文管理扩展包，在 WorkSwarm 中试用｜用自然语言让 Agent 生成用于上下文监控的系统插件。在 WorkSwarm 中启用后，可以查看窗口占用率、各类内容的估算占比和工具调用记录。】

### 4.3 Swarm 协作增强：从定制协作规则到跟踪任务进展，看清谁在做、做到哪

先说明如何把分工和交接约定写进 Swarm 协作规则，以及如何根据状态变化跟踪任务负责人和进度，再说明在 WorkSwarm 中如何用自然语言让 Agent 生成团队协作可视化扩展包，启用对应的系统插件，并在集群模式下查看团队信息和任务关系。

【视频占位 视频7：生成团队协作可视化扩展包，在 WorkSwarm 中查看团队和任务｜用自然语言生成团队协作可视化扩展包。装进 WorkSwarm 并启用对应的系统插件后，在集群模式下查看团队信息和任务关系。】

### 4.4 企业接入适配：让 WorkSwarm 适配企业环境，接入和运行都可按需调整

先概述企业接入扩展。重点说明分布式部署中如何按业务选择 Gateway 连接的 AgentServer，并在两侧分别加载扩展。网关侧介绍鉴权和路由，服务端介绍会话上下文及已接入命令的参数和结果处理。补充如何通过适配器接入第三方沙箱，让 Agent 在选定的隔离环境里执行命令和代码。

说明在 WorkSwarm 中如何用 Gateway 登录系统插件接入登录和鉴权，以及登录前后的访问差异。

【视频占位 视频8：通过 Gateway 扩展接入登录和鉴权｜对照登录前后的访问结果，展示网关鉴权】

运行方面，说明在 WorkSwarm 新建单 Agent 会话时，如何选择 CC、Codex 或 openJiuwen Harness，以及前端界面如何随之切换。

【视频占位 视频9：新建会话时切换三种 Harness｜展示新建会话时选择三种 Harness，以及随选择切换的界面】

## 结语

回扣 openJiuwen 的 RSI 原生 AgentOS 和「Agent所想即所等」。Agent 能把工作中想到的改法做成 RSI 原生 AgentOS 能加载的扩展包，在 WorkSwarm 中作为系统插件启用。试过之后，再根据反馈调整自己的界面和能力。展望随着扩展能力进一步丰富，同一个 Agent 可以在使用中逐渐形成适合个人习惯、团队协作和企业环境的不同工作方式。

## 核对依据（内部）

- 视频7 使用用户指定录屏，按用户说明记录通过自然语言生成团队协作可视化扩展包，以及在 WorkSwarm 集群模式中启用对应系统插件后的效果。 [本版录屏](<../../article/v001/assets/videos/视频7_生成团队协作可视化扩展包，在 WorkSwarm 中查看团队和任务_v001.mp4>)
- 视频5 使用用户指定录屏，按用户说明记录主题背景扩展包的生成过程，以及在 WorkSwarm 里启用对应系统插件后如何切换动态主题。 [本版录屏](<../../article/v001/assets/videos/视频5_生成主题背景扩展包，在 WorkSwarm 中切换动态主题_v001.mp4>)
- 视频4 使用用户指定录屏，按用户说明记录系统插件引发故障后从指定存档点恢复配置的过程。 [本版录屏](<../../article/v001/assets/videos/视频4_从存档点恢复 WorkSwarm 的系统插件配置_v001.mp4>)
- 视频3 使用用户指定录屏，按用户说明记录三种安装方式，以及如何在「我的扩展」中启用或禁用系统插件。 [本版录屏](<../../article/v001/assets/videos/视频3_WorkSwarm 系统插件的三种安装方式与日常管理_v001.mp4>)
- 视频2 使用用户指定录屏，按用户说明记录通过自然语言创建 Token Weather 系统插件，在 WorkSwarm 中试用并按反馈修改。 [本版录屏](<../../article/v001/assets/videos/视频2_用自然语言创建和迭代 Token Weather 系统插件_v002.mp4>)
- 图4 借鉴 Claude Mods 按事件和能力分区的编排。事件、Ops 与接入状态按 openJiuwen 的目标版本和已明确的规划核对。 [参考速查表](<../../refs/competitor_data/Claude-Mods-中文速查表.svg>)
- 第一章 视频1 录屏画面标注 WorkSwarm。可核对「应用形态」系统插件启用、工作台与蜜蜂或胶囊桌宠切换，以及在桌宠里对话后切回工作台续聊。 [本版录屏](<../../article/v001/assets/videos/视频1_一个系统插件，让 WorkSwarm 在工作台和桌宠形态之间切换_v002.mp4>)
- 场景与受众沿用 openJiuwen 公众号模板，面向 Agent 开发者和 WorkSwarm 使用者。全文导语引出运行环境，第一节以桌宠为例，主线落在 Agent 对自身界面与能力的改造。产品称呼沿用本次需求的 WorkSwarm，「Agent所想即所等」按原文保留。
- 技术原理沿用开发指南的运行环境、事件、Ops 与 UI 分层，具体链路以固定 checkout 为准。公开 Harness 文档用于补充 RSI 概念与 Harness 运行背景。 [扩展性概览](<../../refs/develop-docs/1.【概览】OpenJiuwen 扩展性概览.md>) · [openJiuwen Harness 文档](https://github.com/openJiuwen-ai/jiuwenswarm/blob/develop/docs/zh/Harness.md)
- 本次沿用并抽查干净 checkout。agent-core `release/v0.1.20.post3`，提交 `d4c02c6c52dda8e027af1a08295c5db7f4297fe4`。WorkSwarm 源码仓 `releases/0.2.9.beta3`，提交 `06f70e487e2d478febd621e1b5970a06d4c5c920`。回查了 `Registry.load_installed`、Web `/extension` 解析与结果展示、`SystemPluginDetailPage`、Token Weather 的 `on_usage`、Gateway 登录 Handler 及团队查询接口。 [源码证据索引](../../refs/code-analysis/README.md) · [两库关系与案例](../../refs/code-analysis/relationship-and-article-materials.md)
- 安装路径与存档点恢复分开取证。按安装副本启动加载、Web 系统插件管理和 slash command 有源码可追溯。3.3 只介绍恢复指定存档点的系统插件配置，范围和演示内容以用户反馈和录屏说明为依据。 [WorkSwarm V2 源码分析](../../refs/code-analysis/jiuwenswarm-extensions-v2.md)
- 第三、四章结合源码示例和用户提供的录屏。Token Weather 运行链路有示例源码，Skill 有开发指南。生成和迭代、安装启用、存档点回退、动态主题与 Swarm 可视化录屏按用户说明记录。Gateway 认证的源码证据来自 MockIdentity 示例。上下文管理和两段企业接入演示保留视频占位，具体操作待对应素材或目标构建核对。 [扩展调测与 AI 辅助开发](<../../refs/develop-docs/6.【调测与辅助开发】OpenJiuwen 扩展调测与 AI 辅助开发.md>)
- 借鉴 Computer Use 样文第 01 节用一件可观察的任务带入，借鉴 RSI 样文的框架段先讲工程分工再讲改进过程。DeepSeek Harness 创造模式的现有材料也展示了用自然语言为工作台添加功能，本篇以实际观察和再修改为核心来写 Token Weather。 [Computer Use 样文](<../../../../.agents/skills/wechat-article/references/samples/openjiuwen/openJiuwen 开源 Computer Use：让智能体真正“上手”用电脑/article.md>) · [RSI 样文](<../../../../.agents/skills/wechat-article/references/samples/openjiuwen/openJiuwen首发双维度RSI框架，AI自修改，落地办公智能体，算力亲和助力又快又省/article.md>) · [DeepSeek Harness 参考文章](<../../refs/competitor-articles/DeepSeek Harness创造模式：让AI给自己加功能、换界面/article.md>)
