# 如何看待DeepSeek Harness在新版本中加入Claude Code Mods兼容？

Source: https://www.zhihu.com/question/2089740005770008568/answer/2090104616759325588

Accessed (UTC): 2026-11-08

感谢知友们对 [DeepSeek Harness](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=DeepSeek+Harness&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiJEZWVwU2VlayBIYXJuZXNzIiwiemhpZGFfc291cmNlIjoiZW50aXR5IiwiY29udGVudF9pZCI6ODAwMDgwOTY2LCJjb250ZW50X3R5cGUiOiJBbnN3ZXIiLCJtYXRjaF9vcmRlciI6MSwiemRfdG9rZW4iOm51bGx9.Im2UHp5tXwpSKEz0YxXR-YA_RYNZzcJCdSrh64uRzhg&zhida_source=entity) 的关注。我是 DeepSeek Harness 组的[崔添翼](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=%E5%B4%94%E6%B7%BB%E7%BF%BC&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiLltJTmt7vnv7wiLCJ6aGlkYV9zb3VyY2UiOiJlbnRpdHkiLCJjb250ZW50X2lkIjo4MDAwODA5NjYsImNvbnRlbnRfdHlwZSI6IkFuc3dlciIsIm1hdGNoX29yZGVyIjoxLCJ6ZF90b2tlbiI6bnVsbH0.vSpm8sYKcijl_AtSNVdMWms0xSOf49n7CtwMI0OvKx0&zhida_source=entity)，也是这次 v0.2.1-alpha.1 版本中加入 [Claude Code Mods](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=Claude+Code+Mods&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiJDbGF1ZGUgQ29kZSBNb2RzIiwiemhpZGFfc291cmNlIjoiZW50aXR5IiwiY29udGVudF9pZCI6ODAwMDgwOTY2LCJjb250ZW50X3R5cGUiOiJBbnN3ZXIiLCJtYXRjaF9vcmRlciI6MSwiemRfdG9rZW4iOm51bGx9.7XdTQy9Fbg8qprWlZiWonk9HHWLqWPgBuCuc392D0Gc&zhida_source=entity) 兼容层的作者。  
  
首先叠一个甲，目前 DeepSeek Harness 中的“Claude Code Mods 兼容层”属于“alpha 版本”中的“实验性功能”，还有很多很多不完善的地方，也不能保证 100% 兼容。目前版本的兼容性文档 [https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/docs/subsystems/claude-code-mods.zh.md](https://link.zhihu.com/?target=https%3A//github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/docs/subsystems/claude-code-mods.zh.md) 中列举了详细的兼容情况。  
  
做这个兼容层的主要目的，是验证 Claude Code Mods 向插件作者提供的扩展能力，是否大致是 DSH“一切皆插件”架构所提供能力的一个子集。目前还无法让所有 Claude Code Mods 在 DeepSeek Harness 中无缝运行；如果认为这是一个值得投入的目标，从技术上看，未来有可能做到。  
  
DeepSeek Harness 的核心理念是**“一切皆插件”**，这个理念是从立项之初、写第一行代码之前就确立下来的，正如“开源”的理念是从 DeepSeek 成立之初、发布第一个模型之前就确立下来的一样。开源是我们的初心，不是被迫开源的。让我们的 Agent Harness 产品以开放、开源的方式具备尽量极致的可扩展性，也是我们的初心，并不是被迫或模仿别人才做开放可扩展的。  
  
“一切皆插件”的 Agent Harness 有什么用、有什么意义？这是我们从立项之初就在深度思考的课题。我个人认为，“一切皆插件”至少有三方面的意义：  
  
第一，希望能用插件和社区的方式满足多样化的用户需求，让每个人能用上真正为自己打造的、最适合自己的 Agent Harness 产品。同时，会通过训练模型写插件来更改 Agent 自身的方式，试图让 Agent 产品最终达到“按用户的所需所想而改变”，乃至于“言出法随”的效果。目前 DeepSeek Harness 中的“创造模式”就是朝这个方向迈出的一小步：它已经允许 Agent 根据用户需求编写并安装插件，扩展 Harness 的能力和界面。“[创造模式](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=2&q=%E5%88%9B%E9%80%A0%E6%A8%A1%E5%BC%8F&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiLliJvpgKDmqKHlvI8iLCJ6aGlkYV9zb3VyY2UiOiJlbnRpdHkiLCJjb250ZW50X2lkIjo4MDAwODA5NjYsImNvbnRlbnRfdHlwZSI6IkFuc3dlciIsIm1hdGNoX29yZGVyIjoyLCJ6ZF90b2tlbiI6bnVsbH0._9U-X4i81eyX2TcNdyFiBDCxZ-6NPZs-H-FkAJrvVvE&zhida_source=entity)”作为新生事物，肯定还有很多粗糙未经打磨的地方，欢迎知友们试用和提提意见。  
  
第二，希望用插件化的方式满足不同行业的企业部署 Agent 产品的需求。让不同行业的企业，以及帮助这些企业落地 AI 的 FDE 类团队，能使用插件化的方式沉淀行业经验、连接行业基础设施，而不必反复重新造轮子，从而更高效、低成本地使用前沿的模型能力与开源的 Agent Harness 框架，达到提高企业生产力、AI 提效的目的。我们已经看到 DeepSeek Harness 在一些行业中部署的例子：相关开发者开发了针对特定行业的 [DSH 插件](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=DSH+%E6%8F%92%E4%BB%B6&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiJEU0gg5o-S5Lu2IiwiemhpZGFfc291cmNlIjoiZW50aXR5IiwiY29udGVudF9pZCI6ODAwMDgwOTY2LCJjb250ZW50X3R5cGUiOiJBbnN3ZXIiLCJtYXRjaF9vcmRlciI6MSwiemRfdG9rZW4iOm51bGx9.fJgiVHRSt2_4ZNWf6NvvuQ8STqY_1I4En0znCQ6MgSg&zhida_source=entity)，来打造该行业的“AI 工作台”。这些行业类的 DSH 插件一般都没有在网上公开开源，这也是符合 [MIT 开源协议](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=MIT+%E5%BC%80%E6%BA%90%E5%8D%8F%E8%AE%AE&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiJNSVQg5byA5rqQ5Y2P6K6uIiwiemhpZGFfc291cmNlIjoiZW50aXR5IiwiY29udGVudF9pZCI6ODAwMDgwOTY2LCJjb250ZW50X3R5cGUiOiJBbnN3ZXIiLCJtYXRjaF9vcmRlciI6MSwiemRfdG9rZW4iOm51bGx9.Kzc8NSwtZS_XTFpW8Mk91N3MA0L7CQykHkFvU-OaGCk&zhida_source=entity)的，是我们所支持和认可的。  
  
第三，希望能用“一切皆插件”的 Agent Harness 架构推进“Agent 自进化”的命题，用先进的插件系统提供改变 Agent 任意部分的工作方式的灵活性，让 Agent 能够用插件的方式在运行中改变自身，从而最终能够提高智能上限。这个方向非常需要模型与 Harness 的共同进化，相关工作才刚刚开始，路还很长。从工程上来说，需要更完备地实现插件的热插拔、热重载；[Cordis](https://zhida.zhihu.com/search?content_id=800080966&content_type=Answer&match_order=1&q=Cordis&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3OTQyMTE1NjAsInEiOiJDb3JkaXMiLCJ6aGlkYV9zb3VyY2UiOiJlbnRpdHkiLCJjb250ZW50X2lkIjo4MDAwODA5NjYsImNvbnRlbnRfdHlwZSI6IkFuc3dlciIsIm1hdGNoX29yZGVyIjoxLCJ6ZF90b2tlbiI6bnVsbH0.09RJxUMVeQCVXIMR6V7LcHI9sgvMnPmbkit1IM4T5_0&zhida_source=entity) 提供了良好的理论和工程基础，但实际还有很多工程上的难题需要解决。从模型研究上来说，需要以新的方式训练大语言模型，让模型知道可以改变自身的 Harness，让模型学会如何用改变自身的 Harness 的方式自我迭代和进化，最终提高智能上限。  
  
所以 DeepSeek Harness 团队目前非常积极地在招聘既懂大模型研究和训练、又有志于用模型与 Harness 共同进化的方式提高 Agent 智能上限的研究员，来逐步接近“Agent 自进化”的愿景。可以通过 [https://app.mokahr.com/su/12xvM6](https://link.zhihu.com/?target=https%3A//app.mokahr.com/su/12xvM6) 投递 DeepSeek Harness 团队中“深度学习研究员”方向的岗位。  
  
我自己每天工作的相当一部分时间都用于为 DeepSeek 招人和面试。很多来面试的人都会问我：DeepSeek Harness 组的目标是什么？我会这样回答：DeepSeek 的目标是实现 AGI，DeepSeek Harness 组的目标就是从 Harness 的角度推进 AGI。  
  
那什么才算是“从 Harness 的角度推进 AGI”的事情呢？对于这个问题，不同的同事可以有各自的理解，并不需要完全以我个人的理解为准。我个人的理解是：只有做创新的事情才是真正“推进 AGI”的事情。如果我们抄一个 Claude Code，或者抄一个 Codex，做一个和其它某些 Agent Harness 从技术理念到用户体验上都没啥区别、完全差不多的产品，那一定不是“推进 AGI”的事情。因为用户本来就可以通过 Claude Code、Codex 等 Agent Harness，配置使用 DeepSeek 模型。如果我们的 Agent Harness 做得也和 Claude Code、Codex 或其它一些 Agent Harness 产品差不多，那就没有实现我们希望带给用户的体验增量，也不是我们选择的推进 AGI 的方式。  
  
所以，推进 AGI 的事情一定是创新的事情。这次 Claude Code Mods 的兼容实验，就是我们通过一个具体实现，检验 DSH 插件系统扩展能力的一次尝试。在 DeepSeek Harness 团队，我们希望能做出一些世界级的创新，希望能做出一些影响业界发展、影响大家如何看待和定义 Agent Harness 这一新生事物的创新，希望可以做出一些让世界上的 AI 巨头也会认可和跟进的创新。  
  
不管从团队还是产品的角度来看，DeepSeek Harness 都还非常年轻，还有很多不完善的地方。欢迎知友们多多提提建议，前方的路还很长，AGI 还远未终局。
