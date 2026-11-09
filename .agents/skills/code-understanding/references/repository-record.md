# 仓库绑定与记录

本文件规定如何绑定用户提供的源码、核对版本和记录覆盖范围。调用方传入已确认的来源与范围，由 code-understanding 复核。

## 确定源码仓库

1. 用户给出 URL、本地路径或对话中已明确的项目时，按指定范围分析，记录仓库的真实身份和访问、版本或覆盖限制。
2. 用户未指定仓库时，不自行搜索、选用或下载候选仓库。源码会影响结论时，可一次性引导用户提供仓库链接或本地路径，说明可以跳过。用户已跳过时沿用该选择。
3. 跳过源码后，以已有的设计稿、产品说明、测试记录等材料继续处理，标明材料来源及缺少源码验证的结论。若任务必须阅读源码且没有可替代材料，说明缺少的输入和目前能回答的范围。已提供的仓库无法访问时同样记录缺口。

先按本次要求的论文或发布版本核对 tag 与 commit 的映射，再按问题匹配实际实现角色。版本不符的材料可以作为明确标注的背景。未指定历史版本时固定本次读取的快照，要求最新时核查已指定仓库的远端。非 Git 源码可用内容快照定位，发布版本另需映射证据。

按问题分配核心算法、训练、推理、评测、SDK、数据处理等角色，允许多个仓库共同覆盖。SDK 或部分评测不能证明核心算法／服务端实现公开；跨仓库静态覆盖不证明已经组合运行。分别记录源码可读性和运行状态：缺权重、数据或 GPU 不排除可读实现，已有测试或外部复现报告也不等于本次跑通。

复用记录前核对其来源是否仍在用户指定范围内，以及当前问题、版本和源码状态。记录覆盖缺口时，说明核查的是哪些仓库、路径和调用点。

## 已指定仓库的最小记录

对已指定的单仓或多仓逐一运行 preflight。将仓库来源、checkout 路径、分支或 tag、完整 commit、工作树及未提交变更摘要、分析范围与承担的角色集中记在交付物或工作笔记中。

跨仓关系分别记录依赖文件声明的 ref、锁文件实际解析的 commit（如有），以及本次读取的 checkout commit。给出版本和依赖声明的证据位置。只有分支声明时，将锁定提交记为未知。

需要比较用户提供的多个候选、核对独立版本映射，或调用方明确要求结构化覆盖记录时，才填写 JSON 并运行选择检查。普通指定多仓直接使用上述最小记录。

## 保存和执行

需要完整记录时，独立任务沿用用户指定的位置，未要求交付文件时使用本次临时位置，不为记录修改目标仓库。仅在已安装 research 且由其调用时，每个对象保存一份 `scratch/code/<item_id>/repository-selection.json`，多仓库放在同一份记录中，沿用当前对象与问题 ID；选择记录不新增 research 结果字段，路径隔离与证据回写按兄弟技能的 `research/references/code-understanding.md` 执行。

从 [JSON 模板](repository-record.example.json) 开始，填入用户指定的仓库和实际核查结果。

```sh
node <skill-dir>/scripts/repository-selection.mjs --input <facts.json> --output <task-dir>/scratch/code/<item_id>/repository-selection.json
node <skill-dir>/scripts/repository-selection.mjs --input <current-facts.json> --previous <previous-record.json> --output <current-record.json>
```

脚本仅用 Node 内置模块，clone 后即可运行，无须准备三种后端。退出码 0 表示记录格式和选择计算成功，仍须检查 `decision.status` 和 `gaps`；无合格仓库也可退出 0。格式错误退出 1。命令不会搜索网络、下载源码或运行被研究项目，也不能替代事实核查。

## 输入约定（schema_version: 1）

| 字段 | 填写要求 |
|---|---|
| `request.object` / `version` | 研究对象和要求版本；无特定历史版本时显式为 `null`，仍须固定实际源码快照。论文 v1、v2 与软件 tag 是不同标识，需有映射依据 |
| `request.questions` | `{id, roles}` 列表；full 复用 field_id，light 使用稳定问题 ID。roles 是该问题**全部需要**的实现角色，可用 core、training、inference、evaluation、sdk、data_processing 或明确的自定义角色。仅需任一实现时用 `any` |
| `request.specified_ids` | 填入用户指定的候选 ID，包括无法取得的指定地址。跳过源码时直接记录缺口，无需调用工具 |
| `request.latest` / `refresh` | 要求最新或重新核查时填 true，强制复核已指定来源的旧记录 |
| `search` | 兼容既有 schema 的核查记录。填写实际 `checked_at` 和已完成的检查，未检查的标志保留 false |
| `candidates` | 每个候选的 id、url、access、authority、relevance、version、components、runtime；保留被排除候选的原始依据，由输出生成排除理由 |

候选的结构：

- `url` 为 http/https URL 或本地 `file:` URI。`access` 为 readable、blocked、missing 或 unverified，表示**代码可读性**。
- `authority.kind` 为 official、reproduction、other 或 unverified。按已核实的论文、官网、作者关联或复现证据记录身份。身份未核实时填 unverified。
- `relevance.status` 为 matched、unrelated 或 unverified；matched 需要实际核对的相关性证据。
- `version` 记录 `requested`（须与 request.version 一致）、matched／mismatch／unverified 的 `status`、实际 `ref` 和完整 `commit`。非 Git 源码使用内容快照的 `snapshot_sha256`；存在本地修改时还需记录其摘要，并交给 preflight 核对。指定研究版本时附 tag_mapping／paper／official_page／reproduction_report 类型的版本映射证据；commit 固定本身不证明它对应某篇论文。
- `components` 为 `{role, paths, question_ids, evidence}` 列表。paths 使用仓库内相对路径，需已核实的 source_code 证据。空仓库为 `[]`；SDK 只能覆盖 SDK 问题。原论文与复现实现存在差异时在证据 note 中明确限制。
- `runtime.status` 为 not_run（默认）、blocked 或 verified。缺少权重、数据、GPU 等记入 `missing`，不会排除可读源码。verified 需实际 execution 证据；外部复现报告不能代替本次运行。运行行为仍遵循 research 的执行约定。

每条 evidence 包含 `kind`、`url`、精确 `locator`、说明支持关系与条件的 `note`、布尔值 `verified`。模板全部为 false；仅在实际打开原始来源、代码或执行记录核实后改为 true，不能为了让检查通过而填写。工具只能检查已记录的事实是否满足规则，不能证明填入的网页或代码事实真实。

## 输出和复用

`decision` 包含选中仓库、逐问题／角色的 `assignments`、未覆盖的 `gaps`、每个候选的 `assessments.reasons` 以及指纹。

| status | 后续处理 |
|---|---|
| selected | 问题要求的实现角色均有可读代码，进入源码分析；不代表研究字段已证实或运行通过 |
| partial | 分析已覆盖部分，保留 gaps，不能用一个仓库概括整个方法 |
| unavailable | 相关或指定地址访问受阻／无法取得，说明访问限制 |
| unverified | 身份、版本映射、固定快照或源码事实尚待核实，说明缺口 |
| specified_uncovered | 用户指定代码与版本／问题不符，说明边界，不自动替换 |
| search_incomplete | 兼容状态。说明已指定来源的核查缺口，按可读材料继续 |
| not_found | 兼容状态。按本次实际核查范围说明未覆盖的实现角色 |

用户指定多个仓库时按用户顺序和实际覆盖情况分配角色。selected／partial 表示可分析的源码范围，研究结论和运行结果另行核实。

续查时可比较旧记录：同一冻结版本、相同问题和证据可提示复用；版本、问题、候选依据改变，或 latest／refresh 时须重新核对。负面结果不作为长期缓存。指纹只是**已登记事实**的变化检查，不检测远端新提交、伪造记录或工作树变化；仍需按任务要求检查实际 checkout、变更摘要和索引。旧记录中 `verified` 不等于本轮已核实最新事实。

选择记录保留在当前任务期间；清理前把报告需要的仓库身份、版本、范围、关键依据及日期写入已有笔记／证据和正式报告。报告引用原始固定源码，不引用将被清理的此 JSON；跨任务可从这些保留资料重新建立记录，不能声称临时文件永久可用。

## 行为测试

```sh
node --test <skill-dir>/scripts/tests/repository-selection.test.mjs
```

测试用离线候选和证据夹具调用真实选择函数，并验证 CLI 保存、重载与错误退出。覆盖用户指定优先、版本匹配、权威性／热度、空仓库、角色覆盖、运行缺件、访问受阻和复用失效；不依赖实时 Star 或网络响应，也不将这些夹具视为真实网页事实。
