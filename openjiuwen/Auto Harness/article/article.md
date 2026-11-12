# 业界首个"Auto Harness"工程化落地：JiuwenSwarm 给 Harness 装上「后训练」，人人都能 DIY

Source: https://mp.weixin.qq.com/s/KVRzaA5YrB2TGdeR0gLIVg

Accessed (UTC): 2026-11-11

**Agent = Model + Harness**。Harness 是将 LLM 转化为自主 Agent 的编排基础设施——system prompt、工具定义与实现、rail（全生命周期功能钩子）、skill 文档、sub-agent 编排、长期记忆、观测。没有 Harness，LLM 只是一个能说话的概率模型；套上 Harness，它才成为能行动的自主 Agent。

但这里有一个尚未被系统回答的矛盾：Model 已经有了 Post-training——从 RLHF 到 DPO 到 GRPO，后训练让 LLM 从"会说话"变成"好用"。**而 Agent 的另一半——Harness——的后训练，至今几乎完全依赖人工**。调 prompt、改 tool desc、写 skill 文档、配 rail 钩子……每一次优化都是人在试、在猜、在调。模型以月为单位迭代，场景往长尾分布发展，Harness 的进化却高度依赖人工经验。

Auto Harness 是 openJiuwen 的工程化回答——不是训练模型权重，而是让 Harness 在实战中自动学习、自动优化。评测驱动的、覆盖 Harness 全栈组件的端到端自动优化框架。

# 1. 为什么需要 Auto Harness

Anthropic 和 OpenAI 的对照实验已经实锤：**Agent 失败的原因不在模型，在 Harness**。模型能力决定上限，Harness 决定用到上限的几成。同一个模型换一个场景，成功率可能从 90% 骤降到 30%，而手工定制 Harness 成本极高、不可规模化。

Model Post-training 已有成熟的方法、评测基准和自动化流程。但 Harness 的自动优化几乎为零——模型后训练之后，如何让 Agent 在垂域场景（编程、设计、营销、法律审查、医疗诊断）下表现好？至今只能靠人工调 Harness。

学界已有探索验证了"评测驱动+组件解耦"、"用 Agent 优化 Agent"等方向的可行性，但多为学术验证，尚未形成工程化落地。JiuwenSwarm 的 Auto Harness 是对这一方向的首次工程化落地尝试。

Auto Harness 的差异化在于：基于 **Meta Harness（基座）+ Expert Harness（扩展）** 的双层架构天然解耦设计，两层优化覆盖Harness基座到扩展的完整空间——基座优化提升所有场景共享的底层能力上限，扩展优化让 Agent 在不同角色、垂域场景、个人诉求下精准适配。

# 2. Auto Harness 架构与方法

### openJiuwen Harness 框架——Auto Harness 的优化对象

Auto Harness 要优化的对象是 Harness，而 Harness 的结构决定了优化的范围和层级。openJiuwen（JiuwenSwarm）在工程实践中将 Harness 定义为两层：**Meta Harness（基座）** 和 **Expert Harness（扩展）**——这一划分是 Auto Harness 双层优化架构的设计基础。

![](assets/images/image-2cc7d902f2a22233.png)

*图1 openJiuwen Harness 架构总览*

**Meta Harness——基座（通用编排引擎）**：定义 Agent 运行的基础流程与接口——控制流、路由、权限、上下文管理、生命周期、错误恢复。核心组件包括 Agent 创建工厂、双层任务循环（外层 Task Loop 负责任务调度，内层 ReAct Loop 负责推理-行动循环）、预置工具集、预置 Rails（全生命周期功能钩子）、基础设施组件。关键特征：**无状态编排器**，不包含任何领域特化内容，所有场景化能力都通过 Expert Harness 扩展注入。

**Expert Harness 扩展——扩展（领域特化配置包）**：在 Meta Harness 基座上叠加的领域特化配置，关键特征：**配置与实现分离**，声明"有什么"与定义"怎么做"解耦。包含以下内容：

* • **领域提示词**：补充指导内容、改进提示效果，为 Agent 提供场景特定的行为指引
* • **技能定义**：扩展能力范围、优化技能效果，让 Agent 具备特定领域的操作能力
* • **工具配置**：增强工具能力、调整工具参数，让 Agent 的工具调用适配领域需求
* • **MCP 插件**：接入外部服务、调整服务参数，让 Agent 连通领域相关的数据源和 API
* • **Rail 扩展**：注入场景特定的全生命周期功能钩子，让 Agent 在领域约束下运行
* • **上下文资产**：渐进式披露的领域知识，让 Agent 按任务阶段逐步获取必要信息
* • **任务完成验证条件**：定义任务何时算完成，确保 Agent 的输出符合领域质量标准
* • **角色画像**：定义 Agent 的身份与人格，让 Agent 以领域专家的姿态与用户交互

以一个编程场景的 Expert Harness 扩展为例，其目录结构如下：

```
coding_expert/  
  harness_config.yaml       # 基础信息（名称、描述、优先级）  
  config.json               # 配置（工具选择、MCP 接入等）  
  prompt_sections/          # 提示词段落  
  tools/                    # 工具配置  
  skills/                   # 技能定义  
  mcps/                     # MCP 服务配置  
  rails/                    # Rail 扩展  
  context/                  # 上下文资产  
  soul.md                   # Agent 人格  
  identity.md               # Agent 身份  
  stop_eval_conditions/     # 任务完成验证条件
```

一个 Agent 实例由 Meta Harness + 0 或多个 Expert Harness 扩展组合构成。接口协议支持热加载：即时加载 Expert Harness 扩展到当前 Agent、延迟加载（下次对话时自动激活），多个 Expert Harness 扩展可叠加挂载到同一 Agent（Rails 按序追加、Tools 去重、Skills 合并、提示词按优先级排序拼接）。

**Auto Harness 的两个优化层级**，正是对应 openJiuwen Harness 框架的基座-扩展两层：

* • **基座优化（Meta Harness）**——提升所有 Expert Harness 扩展共享的底层能力上限
* • **扩展优化（Expert Harness）**——让 Agent 在不同角色、垂域场景、个人诉求下精准适配

### Auto Harness 两层优化架构

Auto Harness 的核心是一个**评测驱动的闭环优化流程**：评测 → 规划 → 实施 → 再评测，循环迭代直到达到预期或超出最大次数。Expert Harness 优化基本遵循此核心流程；Meta Harness 优化在此基础上增加了定时任务（流程前）、业界调研（流程前）、提交 PR（流程后）。

![](assets/images/image-b180d4184dbaa488.png)

*图2 Auto Harness 两层优化架构*

每个环节的关键机制：

* • **评测集生成**：接收用户的自然语言优化目标，LLM 分析任务维度并生成覆盖不同场景的评测数据集；用户已提供评测集时直接加载
* • **评测&结果评估**：用当前 Harness 配置创建 Agent 并在评测集上运行，收集成功率、耗时、质量评分等指标，判断是否达到预期
* • **设计优化计划**：从评测结果中识别问题根因，检索经验库中的历史优化经验，约束本轮可修改范围，输出结构化优化动作清单（含依赖关系）
* • **实施优化动作**：每个动作在独立 git worktree 中隔离执行，依赖关系按拓扑排序分波并行；所有动作完成后 fix loop 两阶段修复（CI 直接修复 + 评审质量修复）
* • **经验沉淀**：优化生效时自动提取经验写入经验库——问题类型、归因、修复策略、效果度量，形成飞轮效应

整个优化过程都采用了严格的控制和约束机制——预算控制（超预算自动停止）、编辑安全（限制可修改路径）、安全保护（不可变文件需额外审批）、失败回滚（worktree 自动回滚）。

#### Expert Harness 优化——扩展层优化（DIY Expert Harness）

优化 Agent 在特定角色、垂域场景下的表现，优化对象是 Expert Harness 的八大配置组件。标准八组优化动作与可优化要素一一对应：

| 动作组 | 动作 | 功能 |
| --- | --- | --- |
| prompt | 新增 / 修改 / 移除提示词 | 提示词管理 |
| skill | 新增 / 修改 / 移除 / 搜索技能 | 技能管理 |
| tool | 新增 / 修改 / 移除工具 | 工具管理 |
| mcp | 新增 / 修改 / 移除 / 搜索 MCP 服务 | MCP 服务管理 |
| rail | 新增 / 修改 / 移除 Rail 扩展 | Rail 管理 |
| context | 新增 / 修改 / 移除上下文资产 | 上下文资产管理 |
| stop\_eval | 新增 / 修改 / 移除任务完成验证条件 | 验证条件管理 |
| soul | 新增 / 修改 / 移除角色画像 | 角色画像管理 |

产物为新版本 Expert Harness 扩展目录，支持版本回滚。

#### Meta Harness 优化——基座层优化（吸收业界优秀实现）

优化 Agent 的基座能力，优化对象是 Meta Harness 的运行时组件——需新增代码级动作（如新增 Rail 实现、新增子 Agent、修改工具实现）。Meta Harness 优化在核心流程的基础上有三项扩展：

* • **定时任务（流程前）**：按调度周期自动触发优化 session，持续监控基座能力
* • **业界调研（流程前）**：竞品差距分析，输出结构化 Gap 列表（按 impact × feasibility 排序），搜索业界较好实现作为优化策略参考
* • **提交 PR（流程后）**：代码变更提交 PR 到上游仓库供人工审核——基座层修改影响所有场景，需经审核才能合入

#### 关键特性

1. 1. **两层优化覆盖完整空间**：现有方案只优化单一层级，Auto Harness 双层架构覆盖基座到扩展的完整空间
2. 2. **评测驱动的闭环验证**：评测→优化→再评测闭环确保优化生效再回归
3. 3. **经验库飞轮效应**：自动提取并复用优化经验，越优化越精准
4. 4. **依赖关系排序并行执行**：拓扑排序分波执行，无依赖并行，失败动作不影响其他
5. 5. **安全兜底**：预算控制、编辑安全、不可变文件保护、失败回滚确保优化可控可回退
6. 6. **Expert Harness可热加载、可叠加**：Expert Harness 优化产出新版本扩展目录，可直接热加载到当前 Agent，且多个Expert Harness可叠加加载。

# 3. 使用示例

当前可通过 JiuwenSwarm TUI 试用 Auto Harness：

安装：`pip install jiuwenswarm-tui`

启动：`jiuwenswarm-tui`

即可在对话中使用 `/auto-harness` 命令触发优化。

### 示例一：Expert Harness 优化——生成办公能力增强的 Expert Harness

```
/auto-harness run --pipeline optimize_expert_harness 提升一下你自己的办公能力，要求能够：  
 1.擅长生成图文并茂，排版和布局美观，有逻辑性的PPT；  
 2.熟练进行word操作；  
 3.熟练处理财务相关的excel表格；  
 4.对生成的所有文件的文件名做敏感信息检查，这个是硬性约束，在写入文件前做强制检查
```

*演示视频：Expert Harness 优化——从输入命令到产出办公能力增强的 Expert Harness 扩展目录的完整执行过程*

[视频 1 Expert Harness 优化](assets/videos/video-01.mp4)

编排器自动执行核心架构流程：评测当前 Expert Harness 在办公场景下的表现（PPT 排版质量低、Excel 公式错误率高、敏感信息检查缺失）→ 设计优化计划（新增 PPT、Excel、Word 相关工具和技能，新增敏感信息检查 Rail）→ 实施优化动作（约束类先行，其余并行）→ fix loop 规则验证通过 → 再次评测达到预期 → 产出新版本办公 Expert Harness 扩展目录，产出的Expert Harness可在Web端直接激活使用。

### 示例二：Meta Harness 优化——吸收业界优秀实现合入基座

```
/auto-harness run --pipeline optimize_meta_harness 调研当前和 Claude Code 在上下文压缩特性上的差异和不足，吸收提升自己能力
```

*演示视频：Meta Harness 优化——业界调研、评测、代码级优化实施、CI 门控验证、提交 PR 的完整基座层优化流程*

[视频 2 Meta Harness 优化](assets/videos/video-02.mp4)

编排器自动执行基座层优化流程：业界调研 Claude Code 上下文压缩特性，输出 Gap 列表 → 评测当前 Meta Harness → 设计代码级优化动作（新增压缩 Rail + 修改触发逻辑，有依赖关系）→ 在独立 worktree 中按依赖波实施 + fix loop CI 门控验证通过 → 再次评测达到预期 → 提交 PR 供人工审核合并，流程完成。

### 示例三：Meta Harness 定时优化——定期调研吸收业界最新能力

```
/auto-harness schedule start --pipeline optimize_meta_harness --interval 48 调研 Hermes Agent 近期最新版本的更新信息，对新特性进行调研，选择一个最重要的特性进行补充提升
```

*演示视频：Meta Harness 定时优化——定时触发优化 session、自动调研 Hermes Agent 最新版本、持续监控吸收业界最新能力的完整过程*

[视频 3 Meta Harness 定时优化](assets/videos/video-03.mp4)

**定时任务（核心流程前）**：每 48 小时自动触发优化 session，调研 Hermes Agent 最新版本更新，持续监控和吸收业界最新能力。每次触发时自动执行完整的基座层优化流程（业界调研 → 评测 → 设计 → 实施 → 评测 → 提交 PR）。

# 4. 展望：Auto Harness + Coordination Engineering

单兵变强是蜂群变强的前提，但不是终点。Auto Harness 解决的是单个 Agent 的 Harness 自动进化——让基座更强、让扩展更精准。下一步的自然延伸是：**当每个 Agent 都通过 Auto Harness 拥有了自己的个性化 Harness，如何让这些不同角色、不同能力的 Agent 协同起来？**

**从"数字分身"到"数字团队"**：

* • **Auto Harness 构建个性化 Harness——专家的数字分身**：通过 Expert Harness 优化，同一个基座可以叠加出针对不同角色、不同垂域场景、不同个人诉求的个性化扩展。编程专家、设计师、营销策划师、法律审查员、医疗诊断专家……每个 Expert Harness 都是一个领域专家的数字分身。
* • **Coordination Engineering 实现不同 Harness 的协同——数字团队的协作**：自主分工、动态协商、经验沉淀为 Swarm Skills、技能在 Hub 中流通。而 Auto Coordinating Harness 中每个成员的 Expert Harness 优化，直接复用了 Auto Harness 的能力——**Auto Harness 是 Coordination Engineering 的基石**。

![](assets/images/image-51408d437fcd2605.png)

*图3 多Harness协同架构 —— Swarm 包含多个 Agent，每个 Agent 拥有不同的 Model和Harness*

**范式闭环**：

* • Auto Harness → 每个 Agent 拥有个性化 Harness（数字分身）
* • Coordination Engineering（JiuwenSwarm）→ 多个数字分身组成协同团队（数字团队）
* • Auto Coordinating Harness → 团队整体协作能力的自动进化，其中成员的个体进化由 Auto Harness 驱动

# 5. 结语

回过头看，openJiuwen 社区做了一件非常"直接"的事——

既然 Agent = Model + Harness，Model 的后训练解决了"通用好用"，那 Harness 的自动进化自然就是让 Agent 变强的另一半。不是训练模型权重，而是让 Harness 在实战中自动学习、自动优化。这条逻辑线一旦拉出来，接下来的工程命题就清晰了：评测驱动、闭环验证、经验飞轮、安全兜底——每一步都是上一个的必要延伸。

Auto Harness 不是学术论文的复现，而是一整套可跑、可验证、可共建的工程交付——基于 Meta Harness + Expert Harness 的双层架构天然解耦设计，评测驱动的闭环优化流程覆盖基座到扩展的完整空间，Expert Harness 优化让 Agent 在垂域场景下精准适配，Meta Harness 优化让基座能力持续攀升。

**让 Harness 学会自我进化。**

 

---

---

![](assets/images/image-022604c27a167d4f.png)
