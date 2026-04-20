# NOTICE — 上游项目与归属声明

Argus 是基于多个开源项目的二次开发与扩展。本文件列出所有关键上游项目、原作者、协议、以及具体的修改范围。

---

## 核心基础 — TrendRadar(GPL-3.0)

**原项目**:[sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)
**原作者**:**sansan0**
**协议**:GNU GPL-3.0
**沿用内容**:
- 多平台热榜爬虫框架(`trendradar` 包 → 在本项目中重命名为 `argus/`)
- 配置系统、定时调度、通知分发、AI 分析模块
- 原项目的 `config/config.yaml` 结构、`pyproject.toml` 骨架
- Docker 部署、Windows/Mac 安装脚本

**Argus 对 TrendRadar 做的主要修改**:
- 将 Python 包从 `trendradar` 重命名为 `argus`(仅改名,核心逻辑未改)
- 新增 `argus_server/`(原 `mcp_server/`)包,提供 154 个 MCP 工具
- 扩展飞书通知支持 HMAC-SHA256 签名校验(`argus/notification/senders.py`)

根据 GPL-3.0 第 5 条,本项目继续采用 **GPL-3.0** 协议发布,详见 [LICENSE](LICENSE)。

---

## 数据源:RSSHub

**项目**:[DIYgod/RSSHub](https://github.com/DIYgod/RSSHub)
**协议**:MIT
**使用方式**:运行时依赖,`config/config.yaml` 配置 15 个 `http://localhost:1200/*` 路由

**本项目对 RSSHub 自身未做修改**(只本地部署 + 配 cookie 注入)。

---

## Agent CLI 套件

以下 5 个 CLI 被 Argus 的 `run_*` MCP 工具调用,未修改其源码:

| 工具名 | 作用 | 项目 |
|---|---|---|
| `bili` | Bilibili 查询 / 发动态 / 点赞 | [public-clis/bilibili-cli](https://github.com/public-clis/bilibili-cli) |
| `xhs` | 小红书查询 / 发帖 / 评论 | [public-clis/xiaohongshu-cli](https://github.com/public-clis/xiaohongshu-cli) |
| `twitter` | Twitter/X 时间线 / 搜索 | [public-clis/twitter-cli](https://github.com/public-clis/twitter-cli) |
| `tg` | Telegram 本地同步 / 搜索 | [public-clis/kabi-tg-cli](https://github.com/public-clis/kabi-tg-cli) |
| `discord` | Discord 本地同步 / 搜索 | [public-clis/kabi-discord-cli](https://github.com/public-clis/kabi-discord-cli) |

> 注:如 URL 不准,以 `uv tool search` 或 PyPI 为准。本项目仅通过 subprocess 调用这些 CLI,不 vendoring 其代码。

---

## Python 运行时依赖

核心框架:

| 包 | 作者 / 项目 | 协议 |
|---|---|---|
| [FastMCP](https://github.com/jlowin/fastmcp) | Jeremiah Lowin | Apache-2.0 |
| [LiteLLM](https://github.com/BerriAI/litellm) | BerriAI | MIT |
| [Starlette](https://github.com/encode/starlette) | Tom Christie (Encode) | BSD-3 |
| [Uvicorn](https://github.com/encode/uvicorn) | Tom Christie (Encode) | BSD-3 |
| [jieba](https://github.com/fxsjy/jieba) | 孙君意 | MIT |
| [rank-bm25](https://github.com/dorianbrown/rank_bm25) | Dorian Brown | Apache-2.0 |
| [ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/) | Anthon van der Neut | MIT |
| [requests](https://github.com/psf/requests) | Kenneth Reitz | Apache-2.0 |
| [feedparser](https://github.com/kurtmckee/feedparser) | Kurt McKee | BSD-2 |

完整依赖见 [`pyproject.toml`](pyproject.toml) 和 [`uv.lock`](uv.lock)。

---

## 本项目原创部分

Argus 在上游基础上新增了以下模块,全部位于 `argus_server/`(原 `mcp_server/`)下:

| 模块 | 作用 |
|---|---|
| `tools/daily_brief.py` | 飞书早报生成器(含 jieba 分词去冗余) |
| `tools/alerts.py` | 规则引擎(keyword_count / anomaly / semantic_hit) |
| `tools/exporter.py` | Obsidian vault 导出 |
| `tools/cross_platform.py` | 跨平台叙事追踪 + 统一搜索 |
| `tools/scheduler.py` + `scheduler_runner.py` | launchd 定时任务编排 |
| `tools/mcp_proxy.py` | 反向挂载外部 MCP 服务器 |
| `tools/router.py` | 多账号通知路由 |
| `tools/semantic_search.py` | BM25 本地语义搜索 |
| `tools/telemetry.py` | 工具调用遥测 + 健康监控 |
| `tools/safety.py` | 内容安全扫描(PII/诈骗/广告) |
| `tools/social_ops.py` | bili/xhs 细化操作(只读/互动/发帖) |
| `tools/wechat.py` | 微信公众号 RSS 集成 |
| `feishu_bot.py` | 飞书机器人反向通道 |
| `argus/web/` | Web Dashboard (Starlette + HTMX) |

---

## 贡献的协议承诺

向本项目(Argus)提交的 Pull Request,默认以 **GPL-3.0** 授权融入本仓库。
如你的贡献包含第三方代码,请在 PR 中声明其原协议。
