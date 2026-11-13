# 状态契约与离线工具

本文件规范落盘数据和操作；[大纲](outline-workflow.md)、[章节](chapter-workflow.md)及[媒体](media-workflow.md)流程决定确认范围。脚本检查一致性，不能证明用户真实回复、代码事实或视觉质量。

## 唯一数据契约

新进度和元数据使用[契约 3 JSON Schema](../assets/contracts/state.schema.json)。字段以 Schema 为准；[进度示例](../assets/examples/progress.example.json)和[元数据示例](../assets/examples/metadata.example.json)展示完整结构，其中确认、文件和散列均为合成测试数据，不可复制为真实批准。新单元从 `pending`、`confirmation: null` 开始。

新稿的元数据 `scenario` 记录实际采用的场景 ID。没有明确适用的专用场景时填 `general`。接续稿件沿用原记录，除非本次用途变更需要切换场景。

版本目录布局见[版本规范](versioning.md#目录)。`working_file` 使用相对于 `article/` 的路径，如 `v001/article-working.md`。媒体和编辑源文件的 `file` 也相对于 `article/`，正文里的媒体链接相对于实际 Markdown 文件。续写已有进度时使用其登记的路径。

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

工作稿的文章 H1 之外按实际确认单元使用独立标记。按主章确认时，子节留在主章标记内。逐子节确认时，主章单元保留 H2 及章导语，各子节单元使用 H3，并在进度和归档记录中加 `parent_section_id`。子节按顺序紧跟所属主章，媒体直接关联实际使用单元。正文之外的状态、来源和批准语句留在 JSON 或内部说明：

```markdown
# 文章标题

<!-- section:lead -->
实际导语。
<!-- /section:lead -->

<!-- section:main-01 -->
## 主章节标题

本章导语。
<!-- /section:main-01 -->

<!-- section:main-01-01 -->
### 子章节标题

子章节正文。
<!-- /section:main-01-01 -->
```

标记不可嵌套、重复；围栏内的标记是普通代码。`pending` 只能为空或保留该单元标题。单元摘要统一 LF、去首尾空行后以 UTF-8 计算，内部空白及 Markdown 保留；全文导语不含 H1。`edit-section` 将获准重开的单元标记为 `awaiting_confirmation`，记录 `reopened_at`，保留在此之前已确认且未受影响的后续单元。收到本单元的新确认后，移除 `reopened_at` 并记录真实回复，才进入归档。

`assemble` 去除标记并给出各节一基行区间，归档保存到 `chapter_confirmations[].span`。区间及确认链核对章节内容；大纲／正文文件的 `content_sha256` 则对实际保存字节计算，不能混用两种摘要。

### 媒体更新链

仅[免重确认的媒体变化](media-workflow.md#确认与归档边界)使用 `media_updates`，保留原确认。每项含 `kind: format/adopt/caption`、前后单元摘要、更新后的媒体快照、`basis` 和 `replacements`。`adopt` 须有真实用户采用依据；`caption` 须有用户编辑指令并验证同一文件、散列、修订和显示编号，只更改其图注／视频文案。改变媒体事实或用途时走受影响单元的确认流程。

每条替换为 `{after_start, before, after}`。`after_start` 是该次更新后规范化单元文本的零基 Unicode 字符位置（Python 索引），同一次替换均按同一份结果定位、不得重叠。工具从当前文本逆序重放并逐步检查摘要，只允许同一媒体的有效路径修正、占位落实和声明过的图注修改；普通论述及图注意义变化须重新确认受影响单元。纯登记更新可没有文本替换；`caption` 必须对应实际读者文案的替换。既有 `adopt` 更新链可继续读取。

其他排版可保持原文只替换准确路径；无法证明的内容变化按章节流程处理。转换后的信息、呈现和采用范围仍需实际核对，不由散列替代。

## 工具使用

复用现有 Python 环境；缺依赖时安装[依赖清单](../scripts/requirements.txt)。脚本为本技能的 `scripts/article_workflow.py`；从项目根调用时使用下方完整相对路径，其他工作目录用绝对路径。

| 命令 | 作用 |
| --- | --- |
| `check` | 检查契约、来源定位、确认链、章节顺序、标题／命名、PNG、散列、版本映射和引用；不联网取证 |
| `sections` | 输出工作单元摘要，不生成批准 |
| `assemble` | 输出候选正文与区间，不归档或推进状态 |
| `archive --version <vNNN>` | 校验拟归档版本、章节及媒体；加 `--apply` 提交正式正文、版本记录和进度 |
| `finalize --version <vNNN> --basis <用户完稿回复>` | 校验当前稿，确认、归档并标记完稿，导出正式 ZIP。同版重试覆盖原 ZIP；用户明确要求清理时加 `--cleanup`，在正式导出通过后清理工作稿和未引用的临时文件 |
| `export --version <vNNN>` | 校验并列出该版本的正文和可达本地资产；加 `--apply` 写入 [ZIP](versioning.md#导出指定版本) |
| `adopt-media --media-number <图N或视频N> --source <本地文件> --basis <用户采用指令>` | 用正文显示编号落实占位或替换媒体。仅在用户明确要求时用 `--delete-previous` 或 `--delete-source`，确认采用副本校验通过且待删文件无引用后清理。加 `--apply` 提交 |
| `register-temp --temp-file <.tmp 内的文件> --origin <来源> --version <vNNN>` | 记录临时输出的路径、来源、版本和散列。可重复传入 `--temp-file`，加 `--apply` 写入登记 |
| `review-media --media-number <图N或视频N>` | 并排返回正文上下文、实际媒体说明和大纲中的对应原文。可用 `--version` 指定版本 |
| `preferences` | 输出合并场景默认和本篇文件后的编辑偏好 |
| `review-format` | 只读报告读者可见的 Markdown 排版问题，可加 `--version <vNNN>` |
| `preview-mobile --output <HTML 文件>` | 可加 `--version <vNNN>` 选择版本；加 `--apply` 写入本地手机宽度预览 |
| `revise --plan <JSON 文件>` | [预览或提交局部修订](revision-workflow.md)，可同步大纲、媒体和文件名 |
| `reconcile` | 预览手动修改导致的确认差异；选定章节并提供当前散列与用户确认后加 `--apply` 更新该节 |
| `plan-cleanup` | 只读输出未引用图片暂存计划 |
| `save-work --working <候选正文> --progress <候选进度>` | 校验并协同保存工作稿及进度；真实来源和确认由调用方记录 |
| `edit-section --section <ID> --expect-sha256 <当前单元摘要> --draft-ref <新轮次> --text <UTF-8 文件>` | 只改指定单元；加 `--old-text <UTF-8 文件>` 可限定为唯一原文片段。应用时在当前正文目录 `.drafts/` 保存原单元快照。用 `--restore-from <快照>` 代替 `--text` 可精确回退文字。只有快照与重开时记录的原确认摘要吻合且仍适用，才一并恢复原确认 |
| `edit-caption --media-id <内部 ID> --basis <用户原指令>` | 配合 `--title`、`--description` 或 `--remove-description` 修改读者图注／视频文案，校验媒体和未变单元确认。默认预览，加 `--apply` 写入正文和进度 |
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

修改类命令没有 `--apply` 时仅校验／预览；有该开关也先校验条件，无需先重复执行一遍预览。开关是执行既有授权，不是用户审批。`plan-cleanup` 等只读命令始终不写入。暂存和删除的不同阶段、保护集合及未知文件处理统一见媒体规范。

`save-work`、`revise`、`reconcile` 和 `archive` 先校验候选，再写同目录待替换文件及 `article/transaction.json`，依次替换目标。`recover` 对照全部前后散列，验证候选状态后才写入；外部修改、候选无效或结果不明时保留现场。旧式独立素材操作仅按实际文件／散列追加结果，不重复移动或删除；候选登记只有在已证实删除且路径当前不存在时才移除，同路径新生成的候选仍保留。

退出码 0 表示检查通过，2 表示数据或操作错误。旧契约 1／2 只读检查并提醒，不代表已满足新校验；接续操作前补齐可核对的契约 3 字段，历史正文保留旧记录版本，不补造批准。旧大纲散列取实际原文件；确认缺失按[旧稿接续](versioning.md#旧稿接续)处理。

## 离线回归

```powershell
python -B -X utf8 -m unittest discover -s .agents/skills/wechat-article/tests -p "test_*.py" -v
```

测试使用独立临时稿件，覆盖逐章确认、媒体更新、继承／版本、兼容、素材保护／清理和中断恢复。`test_jiuwenswarm_feedback.py` 复放真实反馈中的标题锁定、C1 与导语区分、切换到聊天、子节确认、回退、视频落实和删除图注。`test_outline_review_browser.py` 在已安装 Playwright 和 Chromium 时用无头浏览器验证同页刷新、断线复制、确认回执和宽窄屏目录。回传模拟本机命令，测试不发送真实对话，也不写入原稿及素材目录。
