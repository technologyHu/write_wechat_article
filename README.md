# write_wechat_article

这个仓库用于撰写和归档 openJiuwen、WorkSwarm 的微信公众号技术文章。它包含文章正文、配图、演示视频和参考资料，也提供抓取参考文章、核对源码、评审大纲和导出稿件的技能。

## 快速开始

安装 Git 后，在终端克隆仓库。

```powershell
git clone https://github.com/technologyHu/write_wechat_article.git
cd write_wechat_article
```

在 Codex 等支持 `.agents/skills/` 的客户端中打开仓库根目录，按手头的任务选择技能。已有文章可以直接在 `openjiuwen/` 下阅读，演示视频按需下载。

| 要做什么 | 从哪里开始 |
| --- | --- |
| 撰写、修改或审校公众号文章 | [`wechat-article`](.agents/skills/wechat-article/SKILL.md) · [安装 Python 依赖](#公众号写作和网页抓取) |
| 把网页保存为 Markdown 和本地图片 | [`web-article-fetcher`](.agents/skills/web-article-fetcher/SKILL.md) · [安装 Python 依赖](#公众号写作和网页抓取) |
| 理解源码、追踪调用链或建立图谱 | [`code-understanding`](.agents/skills/code-understanding/SKILL.md) · [准备图谱后端](#代码理解和知识图谱) |
| 下载文章配套视频 | [Git LFS 下载命令](#下载文章视频) |

使用写作技能时，可以从一条具体请求开始，例如「用 `wechat-article` 写一篇面向开发者的 WorkSwarm 扩展机制介绍，先根据参考资料拟标题和大纲」。如果需要核对源码，可以附上目标仓库和版本。

## 安装技能依赖

技能说明、安装脚本和依赖清单随仓库分发。按任务安装所需依赖即可。下面的示例在仓库根目录执行。

### 公众号写作和网页抓取

需要 Python 3.11+ 和可访问的 Python 软件包源。以下 PowerShell 命令会在项目目录之外创建虚拟环境，并安装两个技能的依赖。

```powershell
$venv = Join-Path $env:LOCALAPPDATA 'write_wechat_article\venv'
python -m venv $venv
$skillPython = Join-Path $venv 'Scripts\python.exe'
& $skillPython -m pip install -r .agents/skills/wechat-article/scripts/requirements.txt requests beautifulsoup4 markdownify
& $skillPython -X utf8 .agents/skills/wechat-article/scripts/article_workflow.py --help
& $skillPython -X utf8 .agents/skills/web-article-fetcher/scripts/fetch_article.py --help
```

最后两条命令应打印脚本用法。之后请用 `$skillPython` 指向的解释器执行脚本。如果由客户端调用技能，把解释器的完整路径一并告诉它。

在 macOS 或 Linux 上，可用 `python3 -m venv ~/.local/share/write_wechat_article/venv` 创建环境，再用该目录下的 `bin/python` 执行相同的安装和自检。

网页抓取的 `--browser` 回退功能另需 Playwright 和 Chromium。大纲评审的本机一键回传需要支持 `queue` 的 Codex CLI，也可以用独立 HTML 页面复制反馈。 [浏览器抓取说明](.agents/skills/web-article-fetcher/SKILL.md) · [大纲评审说明](.agents/skills/wechat-article/references/outline-review-ui.md)

### 代码理解和知识图谱

三种图谱后端可以单独准备。GitNexus 和 Understand Anything 的首次安装需要访问 npm 软件包源。为同时满足两者的版本要求，请使用带 npm 的 Node.js 22.x（至少 22.18）或 24.x（至少 24.11）。Graphify 由 Node.js 入口启动，还需要 `uv` 或带 `venv` 和 `pip` 的 Python 3.10+，以及可访问的 Python 软件包源。

按任务运行对应命令。仅需阅读源码和 Markdown 时，可以直接使用 `code-understanding` 的源码阅读流程。

```powershell
# GitNexus：安装锁定的依赖并验证全文和向量查询
node .agents/skills/gitnexus-cli/scripts/gitnexus.mjs --verify-runtime

# Understand Anything：安装锁定的依赖并验证核心模块可加载
node .agents/skills/code-understanding/scripts/preflight.mjs --target . --backend understand --prepare

# Graphify：创建隔离运行环境并打印版本
node .agents/skills/code-understanding/scripts/preflight.mjs --target . --backend graphify --run -- --version
```

首次下载可能需要几分钟，后续会复用本机安装结果。

| 后端 | 自检通过时的输出 |
| --- | --- |
| GitNexus | FTS 全文查询与 VECTOR 最近邻查询通过 |
| Understand Anything | `"status": "ready"` |
| Graphify | `graphify` 和版本号 |

安装流程已在 Windows x64 的干净克隆中用 Node.js 24.15 和 Python 3.13 验证。GitNexus 随仓库提供 Windows x64、Linux x64/ARM64 和 macOS x64/ARM64 的原生扩展。 [GitNexus 平台与安装说明](.agents/skills/gitnexus-cli/README.md)

分析其他仓库时，把 `--target .` 换成目标路径。GitNexus 可以用下列命令为目标项目建立索引。Understand Anything 和 Graphify 的建图步骤见各自的技能说明。

```powershell
node .agents/skills/gitnexus-cli/scripts/gitnexus.mjs analyze '<目标源码目录>' --skip-agents-md --skip-skills
```

[代码理解后端说明](.agents/skills/code-understanding/references/runtime.md) · [Understand Anything](.agents/skills/understand/SKILL.md) · [Graphify](.agents/skills/graphify/SKILL.md)

## 下载文章视频

文章视频由 Git LFS 管理。普通 `git clone` 默认只检出视频的指针文件。需要播放视频或打包包含视频的稿件时，先安装 Git LFS，再运行以下命令下载当前版本的全部视频。

```powershell
git lfs install
git lfs pull --exclude=
```

只需要一篇文章的视频时，用 `--include` 指定该文章的视频路径。以下命令下载「扩展性特性宣发软文」的演示视频。

```powershell
git lfs pull --exclude= --include='openjiuwen/扩展性特性宣发软文/article/**/assets/videos/*.mp4'
```

## 目录说明

| 路径 | 内容 |
| --- | --- |
| [`.agents/skills/`](.agents/skills/) | 技能说明、脚本和安装配置 |
| [`openjiuwen/`](openjiuwen/) | 按主题保存的文章与素材 |
| `openjiuwen/<主题>/article/` | 正文、元数据和引用的图片、视频。版本化稿件放在 `v001/` 等版本目录下。 |
| `openjiuwen/<主题>/refs/` | 有独立参考资料时，存放开发指南、源码分析和参考文章。 |
