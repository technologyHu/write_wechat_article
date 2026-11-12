# DeepSeek Harness 开发者预览版：一切皆插件

Source: https://mp.weixin.qq.com/s?__biz=MzY4NzM3MTkxOQ%3D%3D&mid=2247483698&idx=1&sn=b7c8d125ac4fdfad1c4a5daedc73bcb8&poc_token=HLbZ7mqj4a80rpfCLkuZ84qHGCgbI5tAy5I2V6Dc

Accessed (UTC): 2026-11-08

今天，DeepSeek Harness 的开发者预览版（v0.1 版本）面向全球 Harness 开发者开放测试，并同步以 MIT 协议开放源代码。

作为早期预览版本，当前仍有许多细节有待改进和打磨，核心插件与基础接口也将在后续快速迭代演进。我们期待听到广大 Harness 开发者的反馈与建议。

DeepSeek Harness 采取“一切皆插件”的设计思路。我们采用插件式开放架构来构建 Agent Harness：模型、工具、技能、会话、沙箱、存储、循环、调度、UI 等所有 Agent 能力均由插件组合而成，可自由替换、灵活重组。

![图片](assets/images/image-a92967e07d7c3f3c.gif)

设计思路

* 一切皆插件

DeepSeek Harness 基于具有时空可组合性的 Cordis 插件系统构建。Cordis 元框架只负责插件的加载与卸载以及依赖关系，Agent Harness 的所有具体组件都是不同的 Cordis 插件。插件通过 Cordis 服务与事件彼此协作，并可以在配置层自由组合。

开发者无需改动 DeepSeek Harness 的源码本身，就能以插件的方式独立选择、替换或扩展其中的任一能力。这就是 DeepSeek Harness 最重要的设计原则：一切皆插件。

![图片](assets/images/image-e37c86cffd641704.png)

* **多种****运行模式**

针对不同的使用场景，DeepSeek Harness 提供四种模式，每种模式会默认加载不同的插件集合：

* 标准模式：提供完整的工具组合；
* PTC 模式：程序化工具调用（Programmatic Tool Calling），由模型生成的一段代码来组合多轮工具调用；
* 极简模式：仅保留一个 shell 工具与一个文件编辑工具，用于最小环境下的模型基准测试；
* 创造模式：可以检查当前运行时、在内存中试验 Cordis 插件，并据此组合和创作新的模式。

  ![图片](assets/images/image-a7db654bd59a0a32.png)

* 每一次运行都有迹可循：

模型看到的一切，都会写入仅追加（append-only）设计的会话日志，包括系统提示词、思维链、工具调用与结果、子 Agent 调度，以及每一次上下文注入。在 Trajectory 视图中，你可以按来源查看这些信息。恢复、分叉、检索与回放也都共享同一份事件流。

![图片](assets/images/image-e4245bd8c042ac7e.png)

### 开始使用

* 快速体验

在已安装 Node.js 开发工具链的系统中，可以使用 npx 命令快速启动 DeepSeek Harness 的 Web UI：

```
npx @deepseek-ai/dsh web
```

* 源码安装

获取完整项目源码，并按照仓库说明完成安装：

```
git clone https://github.com/deepseek-ai/deepseek-harness
```

### 写在最后

DeepSeek Harness 目前的 v0.1 版本只是一个起点，我们期待与全球开发者一起，在开源、开放、可复用、可组合的基础设施之上，共同探索智能上限。诚邀全球 Harness 开发者共建 DSH 插件生态。

![图片](assets/images/image-bc8d9dfe8e8a13a3.png)

**DeepSeek Harness 内测用户制作的部分插件**

![图片](assets/images/image-06afe37e9d260e10.jpg)
