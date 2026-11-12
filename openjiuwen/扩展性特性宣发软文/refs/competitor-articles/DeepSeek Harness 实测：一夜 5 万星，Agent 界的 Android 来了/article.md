# DeepSeek Harness 实测：一夜 5 万星，Agent 界的 Android 来了

Source: https://www.geekpark.net/news/368809

Accessed (UTC): 2026-11-08

![](assets/images/image-9924183ecdf48a88.jpg)

摘要

Agent 行业需要一个 Android。

![图片](assets/images/image-d95df797202f7d2d.jpg)

Agent 行业需要一个 Android。

**作者｜张勇毅**

**编辑｜靖宇**

北京时间 8 月 13 日晚上八点半，DeepSeek 正式公布了它成立以来的第一个 Agent 产品，之前预热很久，大家期待值很高的 Deepseek Harness。

截至发稿，**它的 GitHub 仓库已经涨到超过 5 万个 star**—— 而仓库公开刚刚过了 12 个小时。

![图片](assets/images/image-08fe05e7a2fecd6d.png)

Deepseek Harness GitHub 主页截止发稿时已突破 5 万 star｜图片来源：GitHub

DeepSeek 官方给它的定义其实和别家也差不多：模型加上 Harness，才等于 Agent。模型是脑子，Harness 是手脚；聊天机器人交付的是一段话，Agent 交付的是一件做完的事。

发布当晚，我们把它装进了自己的电脑，让它干了两件活：照着 The Verge 的风格重构极客公园官网，再调 GitHub 的接口，画出它自己的涨星曲线。两件活都交付了，全程花掉的 token 不到 3 块钱。

但它也确实还是个毛坯：界面对不写代码的人算不上友好，目前上传的开发者预览版的毛边随处可见。12 个小时用下来，我们的印象是——DeepSeek 压根没想现在就给你一个成品，它给的是一堆等你动手组装的零件。

***01***

****「一切皆插件」****

GitHub 仓库在正式公布前半小时就悄悄公开了，接下来是我们眼看着发生的一幕：21:05 查询时 7，283 个 star，21:51 再查，15，530 个。公布不到两小时，star 破万；今天早上再查，已经突破了 5 万。

在此之前，被称为史上增长最快仓库的 OpenClaw，84 天涨 20 万个，平均每小时约 99 个。DSH 头两个小时的涨速，是它的 80 倍。

目前 Deepseek Harness 还不是一个云端服务：装了 Node.js 的电脑上敲一行「npx @deepseek-ai/dsh web」，浏览器打开本地的 3080 端口，就是它的全部界面。会话、日志、数据都留在本地，浏览器只是它的壳。

新会话页面上挂着它的 slogan：「探索未至之境」，英文原文是 Into the Unknown，旁边是「预览版」的角标。第一次启动还会弹一个「内部测试提示」，大意是 0.1 版仍在面向 Harness 开发者测试，核心插件和基础接口未来几个月会快速演化。翻译一下：这是给开发者的尝鲜版，不是给普通用户的成品。

它最激进、也是发布后 12 个小时争议最大的设计，即「一切皆插件」。

![图片](assets/images/image-e1d48b715e9c0624.png)

插件概念是 Deepseek Harness 的核心｜图片来源：极客公园

模型、工具、界面、审批策略，甚至驱动整个 Agent 运转的主循环本身，全都可以拆下来换掉：如果你愿意的话，连整个前端都是可以更换成你自己喜欢的风格的：比如上手第一时间，我就用 Prompt 将它改成了我更喜欢的洋红色主题。

![图片](assets/images/image-56485061b0a2a19e.png)

Deepseek 允许你自由更改各种组件，甚至包括 Web UI 前端｜图片来源：极客公园

让你直接动手改 Harness 的 Web 前端，**这一个小细节其实也能看出 Deepseek Harness 的开发逻辑，是一个由大大小小插件组成的生态系统**；只要你愿意动手去适应这套系统，你就能搭出一套独一无二、专属于你的工作生态。

![图片](assets/images/image-528362e5a14c2976.png)

按官方文档的说法，Deepseek Harness 内置了标准、极简、代码、创造四种预设，V4-Flash 上个月刷榜 Terminal Bench 的那次官方评测，用的就是其中的极简模式——当时 API 更新日志里那句「即将发布的 DeepSeek Harness」，昨天兑了现。

![图片](assets/images/image-e271e2784f3fdd0f.png)

目前 Deepseek Harness 内置了 4 种模式 Agent 预设，也可以手动添加自己喜欢的预设｜图片来源：极客公园

开放的结果来得比想象快。内测阶段的开发者几天里做了约三百个插件，有人给它换上 Windows XP 的复古皮肤，有人做了表情包插件，让它干完活还能立刻给你发一张大肥鱼表情包。但这种广泛的玩法恰恰说明：这个框架里没有什么是焊死的。

但 star 涨得有多快，冷水来得就有多快。发布第二天，开发者社区的评价开始分化：无论是 Deepseek Harness 目前的用户体验，对非编程用户不是很友好、还是整个围绕着插件构建起来的 Deepseek Harness 生态，其实都引发了一些争议与讨论。

这些冷水没有一盆是冲着模型来的，全部泼在 Harness 这个「壳」上。壳的成色到底如何，我们发布当晚的两个测试正好可以对着看。

上手 Harness 之后，我的第一个测试，就是让它重构极客公园的官网：我把极客公园官网的网址丢给它，让它照着 The Verge 的风格，重构一版新的网站设计。

![图片](assets/images/image-d138b8a2a02c3652.png)

这个任务测的是另一个坑：它到底会不会真的去看两个网站。

![图片](assets/images/image-1ed5bbb3f9aaca47.png)

这是 Deepseek Harness 最后实际生成的效果：实际上这个网站格式与交互都有一些细微的问题，但当你通过 Deepseek Harness 的插件式架构，装上更多关于模型与设计的 Agent 能力插件之后，整个网站就在快速迭代之下，变得更加具有现代感了。

![图片](assets/images/image-23d35487897effcf.jpg)

举例来讲：虽然 Deepseek Harness 内置没有带画板功能，也可以去通过安装插件来实现；官方插件库里有现成的名为 DSH-OpenPencil 的插件，安装之后，你就可以直接实时在对话中预览交互设计文件，直接让 Deepseek Harness 原本单调的 Web UI 变身设计交付工具。

![图片](assets/images/image-fe0fb38e04883ba8.png)

此外，为了验证这次的图片生成以及数据提取能力。我甚至还用 Deepseek Harness 直接生成了一张从昨晚到今天早上的 GitHub 增长趋势图：

提示词：用 GitHub 的公开 API 查一下 deepseek-ai/deepseek-harness 这个仓库的 star 数据，结合这几个我们人工记录的时间点:8 月 13 日 21:05 是 7，283，21:51 是 15，530，8 月 14 日 8:53 是 44，514。画一张 star 增长曲线图，横轴时间、纵轴 star 数，标注关键节点，存成图片。

![图片](assets/images/image-3feb785e6d806345.png)

DeepSeek Harness 有一个「轨迹」页，模型看到的一切都记录在案：系统提示词、思维链、每一次工具调用和返回结果。所以它是真抓取了页面，还是凭训练记忆里的印象「脑补」了一个 Verge 风格，翻记录就能对质。**这种「全程留痕」是它和聊天机器人在架构上的根本区别之一**——聊天工具只保存最终的对话，它保存的是过程里的每一步。

这个设计也是它在 Hacker News 上收到的最响亮的好评。有开发者把「模型看到的一切都写入只增不改的日志」称为 killer feature，还特别点出，美国模型厂商的 API 恰恰把这层数据藏了起来。

算一笔账

Harness 本身免费开源，但模型调用照常收费：目前我们测试的都还是13 日晚 Deepseek 官宣涨价之前的模型价格，因此仍然算是量大管饱：实际上，**这整篇文章的 Demo 测试下来，我们消耗的 Token 用量也没有超过 3 块钱****。**

![图片](assets/images/image-344eaa6f3fdb72ad.png)

此外，Deepseek Harness 还会主动帮你把账算得明明白白：每个会话底部都挂着实时统计，这一轮几步、模型耗时几秒、输入输出各多少 token、甚至缓存命中率多少，都会全部摊开给你看。

争议也恰好出在这里。

发布次日，一项在开发者圈流传的第三方对比称，同款 V4-Flash 接入另一个开源 harness Pi，token 消耗只有 DeepSeek Harness 的三成多。

我们自己的使用体感上，除了使用 V4 Pro Max 仍然量大管饱之外，目前直接使用 Deepseek V4 Flash，不仅速度更快，在那内容生成准确率上也并没有降低很多，或许这也代表着目前 Deepseek 的 Harness 确实还处在开发者预览版的阶段，它并不是最终完成的版本。

![图片](assets/images/image-4cbb4d24c32da1c2.png)

***02***

****Agent 界的 Android****

模型公司亲自下场做「壳」，DeepSeek 不是第一家。Anthropic 有 Claude Code，OpenAI 有 Codex，现在名单上补齐了最后一个大玩家。

Harness 可能是大模型打通生产场景目前最重要的路径之一；开发者工具公司 Composio 做过一个对照测试：同一个 V4-Flash，接入八种不同的 harness，完成三十项任务。最好的完成了二十项，最差的只有十四项。模型一模一样，结果差出三成。

**模型划定能力上限，Harness 决定这份能力最终能兑现多少。**

对 DeepSeek 来说，这层壳还有三重更现实的账。成本上，上下文怎么组织、缓存怎么命中，决定一个任务烧多少 token、重试几次，这些都发生在 Harness 层，别人的壳它管不着。数据上，任务失败的完整记录是改进模型最好的养料，而记录握在壳的手里。生态上，网易科技的报道里提到，团队表示会向部分开发者提供 API 额度——把插件开发者留在自己院子里的意图，不算隐晦。

站远一点看，过去两年模型公司卖的是 token，按字数收费，像卖水。从 Claude Code 开始，它们陆续发现真正值钱的是「把事做完」这个动作本身。DeepSeek 是最新下场的大玩家，也是第一个把整个壳都开源的。

它赌的是另一条路：别人把 Agent 做成成品卖给你，它把 Agent 的零件全部摊开，赌开发者会用这些零件，拼出它自己都没想到的东西。

回头看，「像框架、不像成品」这句今天关于 DeepSeek Harness 最大的争议，放在另一个坐标系里就是恭维—— 安卓刚问世的时候，也是一副毛坯的样子，粗糙、开放、只吸引动手的人。后来的事，大家都知道了。

DeepSeek 赌的，是 Agent 这个行当也需要一个安卓。

\*头图来源：Deepseek Harness 官网

本文为极客公园原创文章，转载请联系极客君微信 geekparkGO

**极客一问**

**你使用 DeepSeek Harness 的体验如何？**

![图片](assets/images/image-f4ca60e54f2c6f38.png)

![图片](assets/images/image-13d3e9c70f9c584c.png)

![图片](assets/images/image-c19e478071e71b71.gif)

![图片](assets/images/image-1e788098eabab11d.gif)
