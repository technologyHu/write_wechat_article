# 状态契约与离线工具

本文件规范落盘数据和操作；[大纲](outline-workflow.md)、[章节](chapter-workflow.md)及[媒体](media-workflow.md)流程决定确认范围。脚本检查一致性，不能证明用户真实回复、代码事实或视觉质量。

## 唯一数据契约

新进度和元数据使用[契约 3 JSON Schema](../assets/contracts/state.schema.json)。字段以 Schema 为准；[进度示例](../assets/examples/progress.example.json)和[元数据示例](../assets/examples/metadata.example.json)展示完整结构，其中确认、文件和散列均为合成测试数据，不可复制为真实批准。新单元从 `pending`、`confirmation: null` 开始。

| 对象 | 职责 |
| --- | --- |
| `progress.json` | 当前会话、阶段、工作文件、大纲／正文基线、章节、来源、媒体及候选；工作稿不占正式版本 |
| `sections` | 稳定 ID、实际标题、顺序、稿标识及来源关联；保存确认、继承或媒体更新依据 |
| `confirmation` | 实际确认的稿标识、用户回复、时间、原大纲、单元摘要及媒体快照 |
| `sources` | 唯一 ID、文档／代码类型、可读路径或 URL、所用版本、核对时间及说明；代码可作唯一来源，外部路径只读 |
| `media` | 唯一 ID、类型、用途角色、标题、所属章节、修订、文件／URL、散列、源文件、状态及采用依据 |
| `pending_media` | 仅关联媒体 ID，记录等待／延期、是否允许最终保留占位及真实依据，不重复媒体标题和路径 |
| `candidates` | 本篇 `.tmp` 候选副本的路径、散列和来源；工具全局原件不归本篇清理 |
| `metadata.json` | 正式大纲／正文记录及独立最新指针；大纲有真实确认和字节散列，新正文为 `record_schema_version: 3`，保存完整快照；素材日志只追加 |

`evidence`／`basis` 含 `kind`、`message`、带时区的 ISO 8601 `at`。`user` 用于实际用户依据；`task_completion` 仅说明成稿任务确已完成；`operation` 仅说明机械操作。后两者都不能替代素材采用、延期或最终保留占位的用户依据。

媒体状态为 `planned`（计划）、`ready`（到位待采用）、`approved`（有实际采用依据）、`retired`（撤下）。角色为 `body`、`cover`、`publishing`。正文图片是真实本地 PNG；未进入正文的封面／发布图可保留适用格式。仅在线视频到位时才必填 `filename_verified`、`verified_at`、`canonical_name` 三个命名核验字段；本地媒体和纯计划可省略，已有完整记录仍兼容。

## 整体状态与恢复位置

| `phase` | 含义 |
| --- | --- |
| `drafting` | 当前单元写作／核对 |
| `waiting_section` | 等待当前单元确认，不能预写后章 |
| `waiting_media` | 全部单元已确认或合法继承，统一处理视频等媒体待办；本章未落实图片须已有用户延期依据 |
| `ready_to_archive` | 所需确认、媒体处置及全文检查完成，可归档 |
| `archived` | 本轮已归档且非活动，可暂存废图，不自动删除 `.tmp` |
| `finalized` | 最终任务已完成，绑定最新归档正文和完成依据，待补项获准最终保留，可清理 `.tmp` |
| `reopened` | 新一轮活动改稿，清空旧完稿标记，保留历史记录 |

这些阶段是恢复位置，不是额外审批。一个软文目录只有一个活动 `session_id` 管理固定工作文件；另一独立稿件使用自己的目录，不覆盖活动会话。非完稿状态的 `finalized_article_version`、`completion_basis` 均为 `null`。

局部改稿未改章节可用 `status: inherited`、`confirmation: null`，在 `inheritance` 保存原正文版本、行区间和摘要。来源不得晚于本轮正文基线，归档时也不得继承自身或未来版本；内容须与来源一致，不补造新批准。

切换大纲后，仍适用的未改章节保留原确认／继承，补 `outline_revalidation: {outline_version, checked_at, note}`。这是适用性核对，不要求重确认；不适用的章节回到正常改稿流程。同一大纲下可省略此字段。

## 稳定章节边界与摘要

工作稿的文章 H1 之外按确认单元使用独立标记；主章含其子节，正文之外的状态、来源和批准语句留在 JSON 或内部说明：

```markdown
# 文章标题

<!-- section:lead -->
实际导语。
<!-- /section:lead -->

<!-- section:main-01 -->
## 主章节标题

本章正文和子章节。
<!-- /section:main-01 -->
```

标记不可嵌套、重复；围栏内的标记是普通代码。`pending` 只能为空或保留本章 H2。单元摘要统一 LF、去首尾空行后以 UTF-8 计算，内部空白及 Markdown 保留；导语不含 H1，主章含 H2。

`assemble` 去除标记并给出各节一基行区间，归档保存到 `chapter_confirmations[].span`。区间及确认链核对章节内容；大纲／正文文件的 `content_sha256` 则对实际保存字节计算，不能混用两种摘要。

### 媒体更新链

仅[免重确认的媒体变化](media-workflow.md#确认与归档边界)使用 `media_updates`，保留原确认。每项含 `kind: format/adopt`、前后单元摘要、更新后的媒体快照、`basis` 和 `replacements`；`adopt` 须真实用户采用依据。

每条替换为 `{after_start, before, after}`。`after_start` 是该次更新后规范化单元文本的零基 Unicode 字符位置（Python 索引），同一次替换均按同一份结果定位、不得重叠。工具从当前文本逆序重放并逐步检查摘要，只允许同编号、同标题的已登记路径／URL替换，或 `adopt` 中规范占位与 Markdown 图片加图注／视频链接的落实；普通论述及图注意义变化须重新确认章节。正文未变时替换列表可为空、前后摘要相同。

其他排版可保持原文只替换准确路径；无法证明的内容变化按章节流程处理。转换后的信息、呈现和采用范围仍需实际核对，不由散列替代。

## 工具使用

复用现有 Python 环境；缺依赖时安装[依赖清单](../scripts/requirements.txt)。脚本为本技能的 `scripts/article_workflow.py`；从项目根调用时使用下方完整相对路径，其他工作目录用绝对路径。

| 命令 | 作用 |
| --- | --- |
| `check` | 检查契约、来源定位、确认链、章节顺序、标题／命名、PNG、散列、版本映射和引用；不联网取证 |
| `sections` | 输出工作单元摘要，不生成批准 |
| `assemble` | 输出候选正文与区间，不归档或推进状态 |
| `plan-cleanup` | 只读输出未引用图片暂存计划 |
| `save-work --working <候选正文> --progress <候选进度>` | 校验并协同保存工作稿及进度；真实来源和确认由调用方记录 |
| `recover` | 核对中断的文件对及素材操作并恢复记录 |
| `stage-unused` | 正文归档后暂存未引用图片 |
| `clean-temp` | 正式完稿后删除本篇已登记临时素材 |

```powershell
$wechatArticleTool = '.agents/skills/wechat-article/scripts/article_workflow.py'
python -B -X utf8 $wechatArticleTool check <软文目录>
python -B -X utf8 $wechatArticleTool save-work <软文目录> --working <候选正文.md> --progress <候选进度.json> --apply
python -B -X utf8 $wechatArticleTool recover <软文目录> --apply
python -B -X utf8 $wechatArticleTool stage-unused <软文目录> --apply
python -B -X utf8 $wechatArticleTool clean-temp <软文目录> --apply
```

后四类操作没有 `--apply` 时仅校验／预览；有该开关也先校验条件，无需先重复执行一遍预览。开关是执行既有授权，不是用户审批。`plan-cleanup` 等只读命令始终不写入。暂存和删除的不同阶段、保护集合及未知文件处理统一见媒体规范。

`save-work` 先校验候选，再写同目录待替换文件及 `article/transaction.json`，依次替换工作文件。`recover` 对照全部前后散列，验证待恢复完整文件对及全部素材操作后才写入；外部修改、候选无效或结果不明时保留现场。素材恢复仅按实际文件／散列追加结果，不重复移动或删除；候选登记只有在已证实删除且路径当前不存在时才移除，同路径新生成的候选仍保留。

退出码 0 表示检查通过，2 表示数据或操作错误。旧契约 1／2 只读检查并提醒，不代表已满足新校验；接续操作前补齐可核对的契约 3 字段，历史正文保留旧记录版本，不补造批准。旧大纲散列取实际原文件；确认缺失按[旧稿接续](versioning.md#旧稿接续)处理。

## 离线回归

```powershell
python -B -X utf8 -m unittest discover -s .agents/skills/wechat-article/tests -p "test_*.py" -v
```

测试使用独立临时稿件及合成回复，覆盖逐章确认、媒体更新、继承／版本、兼容、素材保护／清理和中断恢复，不操作真实文章或工具全局素材。
