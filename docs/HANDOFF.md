# Argus 项目交接文档

> 给新 Claude 会话用的上下文压缩包。把这个文件完整发给新 tab 即可秒懂状态 + 接着做。

## 🎯 一句话总览

Argus（桌面 Mac 上的热点新闻聚合工具）+ 我在上面叠了一整套 agent-native 扩展：
**95 个 MCP 工具** / 68 RSS 源（其中 15 个走本地 RSSHub）/ 5 个 AI-agent CLI（B站/小红书/Twitter/TG/Discord）/ LiteLLM 集成 / 时序异常检测 / AI 语义去重 / 开发规范 20 章。

还差 Batch 4-7 没做完（**4 批共 7 个新能力**）。

---

## 📂 系统分布（不止 argus 一个地方）

| 位置 | 内容 | 大小 |
|---|---|---|
| `<PROJECT_ROOT>/` | 主系统 + MCP server + 配置 | 226 MB |
| `<HOME>/rsshub/` | 本地 RSSHub (Node 原生, 非 Docker) | 1.4 GB |
| `~/.local/share/uv/tools/` | bili/xhs/twitter/tg/discord CLI | 377 MB |
| `~/.bilibili-cli/credential.json` | B 站登录凭证（cookies 已认证） | - |
| `~/.xiaohongshu-cli/cookies.json` | 小红书登录凭证 | - |
| `~/Library/LaunchAgents/com.argus.rsshub.plist` | RSSHub 开机自启（未激活） | - |

## 🗂️ argus 关键文件

```
argus/
├── argus_server/
│   ├── server.py                       # 95 个 @mcp.tool 注册处
│   └── tools/
│       ├── external_apis.py            # 第 1-4 批外部 API (54 个 no-key 源)
│       ├── cli_tools.py                # Batch 0: 5 个 CLI 包装 (bili/xhs/...)
│       ├── ai_enhanced.py              # Batch 2: AI 摘要/翻译/简报/搜索
│       ├── ai_analytics.py             # Batch 3: 语义去重/异常检测
│       ├── data_query.py               # 原生 Argus 数据查询
│       ├── analytics.py                # 原生 Argus 分析
│       └── (其他原生工具)
├── config/config.yaml                  # 68 个 RSS 源 (含 15 个 localhost:1200 走 RSSHub)
├── docs/
│   └── HANDOFF.md                      # 本文件 (交接文档)
│   (注: 开发规范已抽出为独立产品,
│    在 ~/Desktop/AGENT_CLI_SPEC_v1.0.pdf
│    和 ~/Desktop/agent-cli-spec-v1.0.zip)
├── scripts/export_bundle.sh            # 一键打包到其他 Mac (9.6 MB tar.gz)
├── output/news/*.db                    # 7 天历史数据 (2025-12-21 ~ 27)
└── .venv/                              # uv 管理的 Python 3.14 venv
```

## 🛠️ 95 个 MCP 工具分类

### 原生 Argus (27)
`get_latest_news`, `get_trending_topics`, `search_news`, `analyze_sentiment`, `aggregate_news`, `compare_periods`, `generate_summary_report`, `trigger_crawl`, `sync_from_remote`, `read_article`, `send_notification` 等

### 外部 API (54, 全免 key)
- 学术 (8): `search_arxiv`, `search_semantic_scholar`, `search_openalex`, `search_pubmed`, `search_crossref`, `search_openreview`, `search_dblp`, `search_inspire_hep`
- 社区 (7): `get_hackernews_top`, `search_hackernews`, `search_reddit`, `search_mastodon`, `search_bluesky`, `search_lemmy`, `search_stackexchange`, `get_lobsters`
- 媒体 (3): `get_youtube_channel`, `search_wikipedia`, `get_wayback`
- 代码/包 (11): `get_github_trending/releases/code`, `search_crates/jsr/packages`, `search_docker_hub`, `search_homebrew`, `search_flathub`, `search_artifact_hub`, `get_package_info`, `get_pypi_stats`
- 全球新闻 (1): `search_gdelt` (100+ 国家)
- 市场 (5): `get_crypto_trending/markets/details`, `get_exchange_rates`, `search_sec_edgar`
- 安全 (3): `search_cve`, `search_ghsa`, `search_exploit_db`
- 自然 (3): `get_earthquakes`, `get_nasa_data`, `get_weather`, `get_weather_history`
- 经济 (1): `get_worldbank_indicator`
- 人道 (1): `search_reliefweb`
- 知识图谱 (1): `query_wikidata`
- 音乐/书 (2): `search_musicbrainz`, `search_books`
- 论文影响 (1): `get_crossref_events`
- AI 生态 (1): `search_huggingface`

### CLI 包装 (6, Batch 0)
`check_cli_auth`, `run_bilibili`, `run_xhs`, `run_twitter`, `run_telegram`, `run_discord`

### AI 增强 (5, Batch 2)
`check_ai_providers`, `ai_summarize`, `ai_translate`, `ai_brief_news`, `ai_web_search`

### AI 分析 (3, Batch 3)
`semantic_deduplicate`, `detect_anomaly`, `analyze_with_ai`

## 🔌 服务与进程

| 服务 | 状态 | 管理 |
|---|---|---|
| MCP server (stdio) | Claude Code 自动拉起 | `claude mcp list` 查状态 |
| RSSHub (port 1200) | 运行中，PID 变化 | `<HOME>/rsshub/start.sh {bg\|stop}` |
| Chrome 147 for Puppeteer | 已装 | `rsshub/node_modules/.cache/puppeteer/` |

## 🔑 认证状态速查

| 工具 | 状态 | 凭证 |
|---|---|---|
| bili (CLI) | ✅ 已登录 "<YOUR_BILI_NICKNAME>" (UID <YOUR_BILI_UID>) | `~/.bilibili-cli/credential.json` |
| xhs (CLI) | ✅ 已登录 "<YOUR_XHS_NICKNAME>" | `~/.xiaohongshu-cli/cookies.json` |
| twitter (CLI) | ❌ 需登录 x.com 后自动提取 | - |
| tg (CLI) | ❌ 国内网络连不通，需代理 | - |
| discord (CLI) | ❌ 需 DISCORD_TOKEN | - |
| RSSHub 小红书 | ✅ cookie 在 `rsshub/.env` + 本地 patch | - |
| RSSHub B 站 | ✅ cookie + UID 在 `rsshub/.env` | - |
| AI_API_KEY | ❌ 未设置（影响 AI 摘要/翻译/去重） | 需在 `.env` 或 shell 设 |
| TAVILY/EXA/PERPLEXITY/BRAVE | ❌ 未设置 | 用户说有时间再弄 |

## ⚠️ 已知补丁 & 陷阱

1. **RSSHub 小红书 patch**：`<HOME>/rsshub/lib/routes/xiaohongshu/util.ts` 第 67-77 行手动加了 cookie 注入，RSSHub 升级会丢失
2. **Chrome 版本偏差**：RSSHub 源码期望 Chrome 136，装的是 147。通过 `rsshub/.env` 的 `PUPPETEER_EXECUTABLE_PATH` 强制指向，可用
3. **B 站 UID <YOUR_BILI_UID> 没投稿**：用 `run_bilibili("user-videos", ["<YOUR_BILI_UID>"])` 返回 empty 不是 bug，是账号本身没视频
4. **Argus venv 是 Python 3.14**：`.venv/bin/python` 而非系统 python
5. **uv tool 装的 CLI 在 `~/.local/bin`**：MCP server 子进程要在 PATH 里加这个

## ✅ 已完成的 Batch (1-3)

### Batch 1: 开发规范 + 模板 (已抽出为独立产品)
- `~/Desktop/AGENT_CLI_SPEC_v1.0.pdf` (1.4 MB, 可打印/分享)
- `~/Desktop/agent-cli-spec-v1.0.zip` (18 KB, 含 README + spec + 4 模板)
- 项目内已删除, 不再占用 Argus docs 目录

### Batch 2: AI 增强（5 个 MCP 工具）
- `argus_server/tools/ai_enhanced.py`
- 工具: `check_ai_providers`, `ai_summarize`, `ai_translate`, `ai_brief_news`, `ai_web_search`
- LLM 复用 `argus.ai.AIClient` (litellm 封装)
- AI 搜索支持 Tavily/Exa/Perplexity/Brave 4 家（留 env 占位）

### Batch 3: AI 分析（3 个 MCP 工具）
- `argus_server/tools/ai_analytics.py`
- 工具: `semantic_deduplicate`, `detect_anomaly`, `analyze_with_ai`
- 异常检测已实测：扫 7120 关键词找到 8 个新突发话题

---

## 📋 剩余 4 个 Batch (7 个新能力)

### Batch 4a: 跨平台叙事追踪 ⏳
**目标**：把同一事件在 Twitter/微博/HN/Reddit 上的情感走向做对比。
**实现**：
- 新增工具 `narrative_tracking(topic, platforms, window)` 在 `ai_analytics.py` 或新文件 `cross_platform.py`
- 逻辑：
  1. 对每个 platform（热榜/RSS/CLI）拉与 topic 相关的条目
  2. 对每组用 LLM 或 VADER 打情感分
  3. 返回 `{platform: {mean_sentiment, volume, top_titles, top_outlets}}`
  4. 输出"哪个平台最正面/最负面""哪个平台报道量最大"的对比
- 依赖：`search_news` (热榜) + `search_reddit` + `get_hackernews_top` + `run_xhs("search")` + `run_bilibili("search")` 等
- 需 AI_API_KEY（也可用 `argus/ai/analyzer.py` 的 VADER fallback）

### Batch 4b: search_news → CLI 套件自动桥 ⏳
**目标**：Claude 问"今天小红书/B站上关于 Nvidia 的讨论"，MCP 能自动路由到 `run_xhs` + `run_bilibili` 而不是只查本地新闻。
**实现**：
- 新工具 `universal_search(query, sources=["news","xhs","bili","twitter","hn","reddit"], limit)`
- 内部并发调用对应 MCP 工具 + 汇总
- 需处理：各平台返回格式不同 → 归一化到统一的 `{title, url, source, author, engagement}` 结构
- 归一化到统一 `{title, url, source, author, engagement}` 结构

### Batch 5a: 定时任务 skill ⏳
**目标**：像"每天 9 点抓 15 平台 → AI 简报 → 推到飞书"能一键编排。
**实现**：
- 新工具 `schedule_task(cron_expr, workflow_dsl)`
- 内部用 macOS `launchd` 生成 `~/Library/LaunchAgents/com.argus.task.<name>.plist`
- workflow_dsl 示例：
  ```yaml
  steps:
    - tool: trigger_crawl
    - tool: ai_brief_news
      args: { style: headline }
    - tool: send_notification
      args: { channel: feishu }
  ```
- 管理：`list_scheduled_tasks()`, `remove_scheduled_task(name)`

### Batch 5b: MCP client 反向挂载 ⏳
**目标**：让 Argus MCP server 反过来挂载其他 MCP server（Brave Search、Playwright 等）作为自己的 "sub-tools"。
**实现**：
- 用 `mcp` 库的 client 能力连接外部 MCP
- 把外部 MCP 的工具列表 proxy 暴露为 Argus MCP 的工具
- 优点：不用在 Claude Code 里单独注册多个 MCP，统一在 Argus 里
- 需要考虑：名字冲突、超时、错误传播

### Batch 6: Web UI Dashboard ⏳
**目标**：现有只有静态 HTML 报告。加 FastAPI + 简单前端实时看板。
**实现**：
- `argus/web/` 新目录
- FastAPI 后端暴露 REST + SSE
- 前端用 HTMX 或简单 React（不要太复杂，单 HTML）
- 端点：
  - `GET /api/latest` 最新新闻
  - `GET /api/trending` 热点
  - `GET /api/anomalies` 异常检测（可复用 Batch 3 的 `detect_anomaly`）
  - `SSE /api/stream` 实时推送新抓到的条目
- 启动脚本：`start-web.sh` (类似 start-http.sh)

### Batch 7: 微信公众号 via WeRSS ⏳
**目标**：订阅微信公众号文章。
**实现**（两条路选一）：
- **路径 A**：本地部署 WeRSS（Node 原生，类 RSSHub）
  - https://github.com/0x2E/werss
  - 类似 RSSHub：Docker 或 Node 原生
  - 每个公众号生成一个 `http://localhost:<port>/feed/<id>` RSS URL
  - 加到 Argus config.yaml
- **路径 B**：用 RSSHub 的 `/wechat/ce/<id>` 路由
  - 依赖第三方 "CE" 服务（如 wechat.kanba.icu）
  - 不稳定
- 推荐 A。

---

## 🌟 高价值扩展对照表（用户明确标为"高价值"的 10 项）

### 已完成的 (5/10)
| 项 | 所属 Batch | 状态 |
|---|---|---|
| AI 搜索 API 骨架 (Tavily/Exa/Perplexity/Brave) | Batch 2 | ✅ env 占位已做, 拿到 key 即激活 |
| AI 摘要 + 翻译 | Batch 2 | ✅ |
| AI 事件语义去重 (升级 aggregate_news) | Batch 3 | ✅ 实测通过 |
| 时序异常检测 (话题突发预警) | Batch 3 | ✅ 实测识别 8 个新热点 |
| 开发规范 | Batch 1 | ✅ 20 章 + 4 模板 |

### 待做的 (5/10) — 就是 Batch 4-7
| 项 | Batch | 工作量 | 依赖 |
|---|---|---|---|
| 跨平台叙事追踪 (情感对比) | 4a | ~25 min | 无硬依赖，可用 VADER fallback |
| Argus → CLI 套件自动桥 (universal_search) | 4b | ~30 min | CLI 套件已装 |
| 定时任务 skill (launchd workflow) | 5a | ~45 min | macOS launchd |
| MCP client 反向挂载 | 5b | ~45 min | mcp 库 client 能力 |
| Web UI Dashboard (FastAPI + HTMX) | 6 | ~60 min | FastAPI (需 uv add) |
| 微信公众号 via WeRSS | 7 | ~30 min | 需装 WeRSS（Node 原生） |

## 🧩 Batch 8+ 可选扩展（问题 3 的"中价值"清单）

下面是之前对话里列出的 "中价值" 数据源扩展, **不在主路线图**, 但有意义时可按需做。每个预估 15-30 分钟:

### 社交/媒体（需 key 或特殊处理）
- **Twitter/X API v2**: 比 `twitter-cli` 稳定, 但 $100/月起
- **YouTube Data API v3**: 比 RSS 多评论/字幕/订阅数, 免费 10k 配额/天
- **Reddit OAuth API**: 比公开 JSON 多 user-specific (需 OAuth app)
- **LinkedIn**: OAuth + 企业 / 个人 API 区分, 严格
- **TikTok / 抖音**: 只能走逆向, 风险高
- **Pinterest**: Public API 极有限

### 生产力 / 个人
- **Gmail API** (`gmail_read_recent`, `gmail_search`): 个人邮件查询
- **Google Calendar API**: 日程查询 + 冲突检测
- **Notion API**: 个人知识库搜索 (集成 trend 数据到笔记)
- **Linear API**: 产品 issue 搜索
- **Slack API** (user token): 聊天历史搜索

### 数据/AI 生态
- **Kaggle Datasets API**: 找 ML 数据集 (需免费 key)
- **HuggingFace Hub Private**: 公共部分已有, 私有模型需 token
- **Replicate API**: 跑模型 inference
- **OpenAI / Anthropic / Gemini 直接 API**: 已通过 litellm 覆盖

### 生活/个人数据
- **Spotify API**: 个人播放历史 (OAuth)
- **Apple Music API**: iOS 个人数据 (developer token)
- **Strava**: 运动数据 (OAuth)
- **Garmin Connect**: 健康数据
- **Apple Health**: 本地数据库查询 (私有)

### 金融 (需 key)
- **Alpha Vantage** / **Finnhub** / **IEX Cloud**: 股票实时/历史
- **Interactive Brokers API**: 交易 (真实账户风险)
- **FRED (美联储经济数据)**: 免费需注册 key

### 其他
- **OpenSecrets / FEC**: 美国政治献金
- **GovInfo**: 美国政府文件
- **EIA (美国能源署)**: 能源数据
- **OECD**: 复杂 SDMX 协议
- **NASA ADS**: 天文学论文库

## 🚫 不推荐 (问题 3 的"低价值"清单)

- Facebook / Instagram (封闭, Meta Graph API 企业认证复杂)
- 微信个人号 (腾讯严打, 封号)
- 企业微信 (私域, 除非你公司用)
- 抖音 (封闭 API + 反爬强)
- Google Scholar 无官方 API (scholarly 库易被封)

---

## 🚀 新会话接手指引

### Step 1: 环境验证（1 分钟）

在新 Claude Code 会话里跑：

```bash
# 确认 MCP 还活着
claude mcp list

# 确认 95 个工具都注册了
<PROJECT_ROOT>/.venv/bin/python -c "
from argus_server.server import mcp
import asyncio
print('总工具:', len(asyncio.run(mcp.get_tools())))
"

# 确认 RSSHub 运行
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:1200/

# 确认 CLI 可用
~/.local/bin/bili status --yaml | head -3
```

期望输出：MCP ✓ Connected, 95 工具, HTTP 200, bili 认证 ok

### Step 2: 选择继续方式

**方式 A：顺序继续 Batch 4-7**
告诉新 Claude："按 docs/HANDOFF.md 里 Batch 4a 开始，做完一个做下一个"

**方式 B：只做最关键的**
告诉它："只做 Batch 4a (跨平台叙事) + Batch 7 (微信公众号)"

**方式 C：跳过某个你不想要的**
比如："跳过 Batch 5b (MCP client 反向)，因为 Claude Code 可以直接挂其他 MCP"

### Step 3: 完工后打包

```bash
<PROJECT_ROOT>/scripts/export_bundle.sh ~/Desktop
# 产出 ~9.6 MB tar.gz, 可拷到新 Mac 运行 install_on_new_mac.sh
```

---

## 📝 最后几个贴士

- **重启 Claude Code 才能看到新增的 MCP 工具**（每做完一个 Batch 提醒用户）
- **改代码不用重启**：`claude mcp list` 会自动健康检查，下次 tool 调用时用新代码
- **Argus 的 venv 路径**：`./.venv/bin/python`（不是 python3）
- **RSSHub 日志**：`/tmp/rsshub.log`
- **测试时用 `--yaml`**：CLI 套件默认在非 TTY 下是 YAML
- **add 新 MCP 工具的套路**（已用过 4 次，模式固定）：
  1. 写 `argus_server/tools/<name>.py` 里的适配器类
  2. 在 `server.py` import + `_get_tools()` 实例化
  3. 加 `@mcp.tool async def ...` 注册
  4. 单独跑 `.venv/bin/python -c "..."` 实测
  5. `claude mcp list` 验 healthy

祝新 tab 顺利！
