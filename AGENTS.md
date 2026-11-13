# 仓库协作说明

本仓库用于撰写、审校和归档微信公众号文章。技能及其脚本位于 `.agents/skills/`。安装命令、版本要求和自检步骤见 [README](README.md)。

## 按任务选择入口

| 任务 | 先读 |
| --- | --- |
| 准备技术素材，撰写、修改、审校或导出公众号文章 | [wechat-article](.agents/skills/wechat-article/SKILL.md) |
| 单独保存网页正文及图片 | [web-article-fetcher](.agents/skills/web-article-fetcher/SKILL.md) |
| 理解源码、追踪调用链或建立知识图谱 | [code-understanding](.agents/skills/code-understanding/SKILL.md) |
| 润色现有文字 | [humanizer](.agents/skills/humanizer/SKILL.md) |

按当前任务读取对应技能和相关参考。仅需直接阅读源码时，从目标文件和调用链入手。需要图谱时，使用技能自带的入口准备选定后端，并将分析绑定到用户指定的仓库、版本和范围。运行环境留在本机，依赖通过仓库里的锁文件和安装脚本重建。 [图谱后端运行说明](.agents/skills/code-understanding/references/runtime.md)

## 文章与素材

- 根据用户给出的主题、受众和用途选择写作场景。为 openJiuwen 公众号写作，或以 openJiuwen／WorkSwarm 的能力为传播主体时，使用 `openjiuwen` 场景。没有适用的专用场景时，使用通用写作流程。 [openJiuwen 场景约定](.agents/skills/wechat-article/references/scenarios/openjiuwen.md)
- `openjiuwen/` 是现有场景的归档目录。新稿优先使用用户指定的位置，也可按实际场景和主题归档。接续已有稿件时，沿用原目录和版本布局，按本次修改范围保留其他已确认段落。 [目录与版本管理](.agents/skills/wechat-article/references/versioning.md#目录)
- 落盘修改后，核对受影响的正文、大纲、元数据和相对媒体链接。技术主张应对应可核对的资料或目标版本源码。 [版本管理](.agents/skills/wechat-article/references/versioning.md) · [状态契约](.agents/skills/wechat-article/references/state-contract.md)
- `openjiuwen/**/article/**/assets/videos/*.mp4` 由 Git LFS 跟踪。默认克隆只检出指针。需要播放、校验或导出时，在仓库根目录按文章路径下载对应视频。 [视频下载命令](README.md#下载文章视频)
- 运行缓存、依赖安装目录、临时源码 checkout 和生成的导出 ZIP 保留在本机。提交时检查暂存范围。

## 验证改动

改动脚本时，在仓库根目录运行相关测试。Python 命令使用 [README](README.md#公众号写作和网页抓取) 中安装过依赖的解释器。

```powershell
python -B -X utf8 -m unittest discover -s .agents/skills/wechat-article/tests
python -B -X utf8 -m unittest discover -s .agents/skills/web-article-fetcher/scripts -p test_fetch_article.py
node .agents/skills/code-understanding/scripts/test-external-target.mjs
```

修改安装入口、依赖锁或内置扩展时，运行相应的干净克隆测试。它们会在临时目录重新安装依赖。

```powershell
node .agents/skills/code-understanding/scripts/test-preflight.mjs
node .agents/skills/gitnexus-cli/scripts/test-bootstrap.mjs
```
