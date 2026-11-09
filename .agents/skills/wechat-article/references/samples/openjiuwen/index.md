# openJiuwen 参考样文索引

这里保存 8 篇公众号历史样文及其原始归档，共 8 份正文、8 份来源元数据和 50 张图片。按需定位相关段落，不要求读完或凑齐篇数。

需要将样文用于流程、约束、内容组织或大纲填写时，读取[样文写法与约束](writing-guide.md)：先区分[引用性质](writing-guide.md#先判断引用性质)，再按[组织取舍](writing-guide.md#组织方式的取舍)或[模板填写位置](writing-guide.md#模板中的运用)查找方法及原文段落。表中“主要借鉴”用于选文，详细解读在指南集中维护。

## 按题材选择

| 本次题材 | 本地正文 | 主要借鉴 | 图片数 | 原始来源 |
| --- | --- | --- | --- | --- |
| 长程任务、对照实验、记忆效果 | [Agent长时工作如何不跑偏？WorkSwarm用「永续会话」给出解法](<./Agent长时工作如何不跑偏？WorkSwarm用「永续会话」给出解法/article.md>) | 用任务推进与冲突细节解释效果，观察截图、视频说明与使用入口如何衔接 | 8 | [公众号原文](https://mp.weixin.qq.com/s/a3YGJIF6Vi9rHsQPqLGw3A) |
| 新组件、桌面操作、跨应用任务 | [openJiuwen 开源 Computer Use：让智能体真正“上手”用电脑](<./openJiuwen 开源 Computer Use：让智能体真正“上手”用电脑/article.md>) | 用一个完整任务串联观察、操作和核对，再解释接入价值 | 5 | [公众号原文](https://mp.weixin.qq.com/s/zJXEhOHHgGlBupSdElbeKw) |
| 新功能、知识处理流程 | [告别资料散落，让知识持续积累：openJiuwen 首发个人知识空间，重塑个人办公智能体新体验！](<./告别资料散落，让知识持续积累：openJiuwen 首发个人知识空间，重塑个人办公智能体新体验！/article.md>) | 从资料配置、采集与处理写到按需使用，再解释效果及成本口径 | 1 | [公众号原文](https://mp.weixin.qq.com/s/ViVOhJGLd5azXDujgIIWDg) |
| 工程框架、自我改进、实验流程 | [openJiuwen首发双维度RSI框架，AI自修改，落地办公智能体，算力亲和助力又快又省](<./openJiuwen首发双维度RSI框架，AI自修改，落地办公智能体，算力亲和助力又快又省/article.md>) | 把框架分工对应到用户可发起的实验、验证过程与结果 | 5 | [公众号原文](https://mp.weixin.qq.com/s/jXZhv7tY2EniQdRs6XxoQA) |
| 产品升级、综合体验与差异化价值 | [WorkSwarm 引领办公智能体新范式，重塑桌面生产力](<./WorkSwarm 引领办公智能体新范式，重塑桌面生产力/article.md>) | 从多个办公和编程场景归纳差异化价值，避免各章节重复介绍同一能力 | 8 | [公众号原文](https://mp.weixin.qq.com/s/bxizC5DqNEc2bnW5k49tew) |
| 算法机制、多模态记忆、评测 | [让 Agent 首次拥有“视听双流记忆”：openJiuwen Agent-Memory 看懂长视频，关键事件一个不落](<./让 Agent 首次拥有“视听双流记忆”：openJiuwen Agent-Memory 看懂长视频，关键事件一个不落/article.md>) | 用具体失效现象解释机制选择，再用案例和指标支撑判断 | 4 | [公众号原文](https://mp.weixin.qq.com/s/-egoHzADLLF8Gku5ZIsQ4g) |
| 资源平台、开发者生态 | [Agent版Hugging Face来了，openJiuwen发布首个开源智能体资产平台](<./Agent版Hugging Face来了，openJiuwen发布首个开源智能体资产平台/article.md>) | 说明资源类型、职责分工及创建、使用、共享的完整关系 | 11 | [公众号原文](https://mp.weixin.qq.com/s/sYCKFu7piNu2Cd4xZzz14A) |
| 架构升级、跨渠道协作 | [openJiuwen首发蜂群架构Hyper-Agent，开启Agent组织级协作新范式！](<./openJiuwen首发蜂群架构Hyper-Agent，开启Agent组织级协作新范式！/article.md>) | 把身份、会话和任务关系落实到架构、界面和场景演示 | 8 | [公众号原文](https://mp.weixin.qq.com/s/mHQF2gxOaj9VMAebWqVg9g) |

## 归档组织

```text
<样文标题>/
├── article.md
├── metadata.json
└── assets/images/
```

- 每篇正文、来源元数据及资产按原归档保存，保留原文件名、原始 URL、抓取记录及散列，不重写原文。正文中的图片继续使用相对于该篇文章的路径。
- 查看原始来源、图片下载状态及既有检查记录时，读取该篇 `metadata.json`；这些元数据属于参考资料，不是本次写作的大纲与正文版本记录。
- 本资料集未保存视频文件；原文中的视频说明保留为参考，不能把文字说明当成已下载或可直接复用的视频素材。

## 在写作中使用

- 本索引负责选文与定位，具体借鉴方法和历史内容的使用边界统一见[样文指南](writing-guide.md)；写作、确认与变更仍遵循技能原流程。
- 内置资料独立于待分析代码仓和每篇新稿的 `refs/`。作为本篇实际依据或复用媒体时，按[参考材料与历史追溯](../../versioning.md#参考材料与历史追溯)记录来源并重建引用路径。
