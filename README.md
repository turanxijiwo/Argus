# Argus

> 个人情报中枢 · 基于 [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) 的二次开发扩展
>
> 在原项目热榜聚合能力之上,新增 **169 个 MCP 工具** · 跨平台叙事追踪 · 本地 BM25 语义搜索 · 研究工具包 · 定时任务编排 · 飞书机器人反向通道 · Obsidian 导出。
>
> 协议:**GPL-3.0**(继承上游)· 完整归属见 [NOTICE.md](NOTICE.md)

---

## 🧭 这是什么

你每天要扫 10+ 个热榜,刷 5 个社媒,查几个 RSS 源,还想在一堆信息里做去重、找突发话题、看跨平台情感差异 —— Argus 把这些操作沉淀成 **169 个 MCP 工具 + 5 个 launchd 定时任务 + 1 个飞书机器人**,让 AI agent(Claude Code / Cherry Studio / 任何 MCP client)替你跑。

---

## ✨ Argus 新增能力(相对上游 TrendRadar)

| 模块 | 路径 | 作用 |
|---|---|---|
| **MCP Server** | `argus_server/` | 169 个工具,覆盖数据查询 / 分析 / 搜索 / 通知 / 自动化 |
| **跨平台叙事追踪** | `tools/cross_platform.py` | 对比同话题在 news/hn/reddit/xhs/bili/twitter 上的情感走向 |
| **本地语义搜索** | `tools/semantic_search.py` | BM25 + jieba 中文分词,跨天全文检索,<50ms 查询 |
| **Alert 规则引擎** | `tools/alerts.py` | keyword_count / anomaly / semantic_hit 三类规则 |
| **定时任务编排** | `tools/scheduler.py` + `scheduler_runner.py` | macOS launchd workflow DSL |
| **MCP client 反向挂载** | `tools/mcp_proxy.py` | 把外部 MCP server 的工具挂到本服务下 |
| **研究工具包** | `tools/research_toolkit.py` + `research_resources.py` / `research_resource_normalize.py` / `research_resource_workflow.py` / `research_resource_content.py` / `research_codex_summary.py` / `research_compare.py` / `research_compare_contract.py` / `research_compare_sources.py` / `research_compare_brief.py` / `research_citation.py` / `research_runtime.py` / `research_handoff.py` / `research_page.py` / `research_health.py` / `research_crawl.py` / `research_sources.py` / `research_source_ai.py` / `research_topic.py` / `research_images.py` / `research_pack.py` / `research_workflow.py` / `research_batch.py` / `research_gallery.py` / `research_render.py` / `research_web.py` / `research_brief.py` / `research_io.py` | 统一网页抓取、图书/论文/课程资源发现与公开内容读取、Codex 摘要、带 DOI/BibTeX 和证据 locator 的多 artifact 比较、图片发现、gallery-dl 安全封装、跨源研究聚合 |
| **多账号通知路由** | `tools/router.py` | 按关键词分流到多个飞书/钉钉/Bark 群 |
| **飞书机器人反向通道** | `feishu_bot.py` | 群里 @ 机器人触发命令 → 调用 MCP → 回复 |
| **Obsidian 导出** | `tools/exporter.py` | 每日简报 / 查询报告 / 异常报告自动落 vault |
| **内容安全扫描** | `tools/safety.py` | PII / 诈骗 / 广告 / NSFW 规则扫描 |
| **健康监控 + 遥测** | `tools/telemetry.py` | 工具调用统计 / 延迟 / 错误率 |
| **Web Dashboard** | `argus/web/` | Starlette + SSE 实时看板 |

上游 TrendRadar 原有的**热榜爬虫 + RSS + 通知分发 + AI 翻译 / 分析** 全部继承。

---

## 🚀 快速开始

### 1. 克隆 + 装依赖

```bash
git clone https://github.com/turanxijiwo/Argus.git
cd Argus
uv sync
```

### 2. 复制配置

```bash
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml, 填你的 feishu webhook / RSS 源 / AI API key 等
```

### 3. 抓一次数据试试

```bash
.venv/bin/argus --now
```

### 4. 接入 MCP client

Claude Code / Cherry Studio / 任何 MCP client 配置:

```json
{
  "mcpServers": {
    "argus": {
      "command": "/path/to/Argus/.venv/bin/argus-mcp"
    }
  }
}
```

### 5. (可选)启定时任务 / Web / 飞书 bot

```bash
# Web Dashboard (端口 5173)
./scripts/start-web.sh bg

# 飞书机器人反向通道 (端口 6600)
./scripts/start-feishu-bot.sh bg

# 定时任务编排 — 在 MCP client 里让 AI 调用 schedule_task
```

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | 当前项目交接入口、验证命令、Research Toolkit 流程与运行时风险 |
| [docs/RESEARCH_TOOLKIT_BOUNDARIES.md](docs/RESEARCH_TOOLKIT_BOUNDARIES.md) | Research Toolkit 第一阶段边界: 内置能力、可选依赖、非目标、后续候选 |
| [docs/RESEARCH_TOOLKIT_PHASE2A_AUDIT.md](docs/RESEARCH_TOOLKIT_PHASE2A_AUDIT.md) | Research Toolkit Phase 2A 本机可选运行时与真实公开源 readiness 审计 |
| [docs/RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md](docs/RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md) | Research Toolkit Phase 2 交付基线、验证证据与剩余运行时风险 |
| [docs/RESEARCH_WORKFLOW_EXAMPLES.md](docs/RESEARCH_WORKFLOW_EXAMPLES.md) | `research_workflow` MCP prompt 示例、工具参数、保存产物和失败检查点 |
| [docs/SCHEDULER_GUIDE.md](docs/SCHEDULER_GUIDE.md) | 定时任务 DSL 语法 / 接入飞书 / 调试方法 |
| [docs/FEISHU_BOT_SETUP.md](docs/FEISHU_BOT_SETUP.md) | 飞书反向通道接入:App 创建、Cloudflare Tunnel、联调 |
| [NOTICE.md](NOTICE.md) | 上游项目、依赖包、贡献者归属声明 |

---

## 🧩 169 个 MCP 工具速览

工具分类(详见 `argus_server/tools/` 各模块):

- **原生数据 (27)**:`get_latest_news` / `search_news` / `analyze_sentiment` / `trigger_crawl` ...
- **外部 API (54, 无 key)**:`search_arxiv` / `get_hackernews_top` / `search_reddit` / `search_gdelt` / `search_cve` ...
- **CLI 适配 (7)**:`check_cli_auth` / `xhs_auth_status` / `run_bilibili` / `run_xhs` / `run_twitter` / `run_telegram` / `run_discord`
- **AI 增强 (8)**:`ai_summarize` / `ai_brief_news` / `semantic_deduplicate` / `detect_anomaly` ...
- **跨平台 (2)**:`narrative_tracking` / `universal_search`
- **定时任务 (4)**:`schedule_task` / `list_scheduled_tasks` / `run_scheduled_task` / `remove_scheduled_task`
- **MCP proxy (5)**:`mcp_proxy_add/remove/list/list_tools/call`
- **告警 (5)**:`alert_add/list/remove/test/run_all`
- **导出 (3)**:`export_daily_brief` / `export_query_report` / `export_anomalies`
- **语义搜索 (4)**:`semantic_index_rebuild` / `semantic_search` / `semantic_similar` / `semantic_index_status`
- **健康监控 (2)**:`system_health` / `tool_stats`
- **安全扫描 (3)**:`safety_scan_titles/scan_day/list_rules`
- **社交细化 (20)**:`bili_*` / `xhs_*`(只读 / 轻互动 / 需 confirm 的发帖)
- **路由 (5)**:`route_add/list/remove/test/dispatch`
- **微信公众号 RSS (4)**:`wechat_*`
- **每日早报 (2)**:`push_daily_brief` / `render_daily_brief`
- **研究工具包 (14)**:`research_toolkit_health` / `research_runtime_probe` / `crawl_url` / `discover_page_images` / `research_images` / `find_research_resource` / `research_resource_workflow` / `research_compare_artifacts` / `research_pack` / `research_workflow` / `research_batch_workflow` / `research_review_artifact` / `download_gallery` / `research_topic`(含可选 `codex` 和 `web:tavily/exa/perplexity/brave` 源)

研究工具包第一版不新增依赖,默认提供网页抓取、图片候选发现、主题驱动图片研究、跨源情报搜索、证据包生成、研究流水线、批量保存型研究流水线、单 artifact 质量审查、显式可选 runtime probe 和 `gallery-dl` 安全 dry-run 封装; `research_toolkit_health` 会返回包/CLI/配置准备状态,而 `research_runtime_probe` 会按明确请求验证 Crawl4AI 或 Codex SDK 是否真的可运行; `crawl_url(render_js=True)` 可在本地安装 Crawl4AI 后启用动态渲染,`research_topic` 可复用已配置的 Tavily / Exa / Perplexity / Brave 作为 `web:<provider>` 搜索源,也可在本地安装 `openai-codex` 后使用 `codex` 源控制本地 Codex SDK 做个人研究检索,`ARGUS_CODEX_MODEL` 可覆盖默认模型; `research_pack` 会先找页面再抓取正文,保留 source/page 错误和可继续交给 AI 总结的结构化证据; `research_images` 会先找相关页面再抽取图片候选并保留来源页上下文; `research_workflow` 会自动选择可用搜索源,一次完成主题搜索、页面抓取、图片候选抽取、可重试错误记录、Markdown 研究简报生成,并可选保存 JSON + Markdown 文件; `research_batch_workflow` 会为多个查询批量生成 JSON/Markdown 产物和一份项目内 Markdown 审查报告,`research_review_artifact` 可直接审查单个已保存 JSON 并返回分数、状态、警告和计数,响应只返回计数、相对路径和质量摘要。后续按活跃度、License、CLI/API 稳定性、结构化输出、速率限制能力逐个接入 Crawl4AI / gallery-dl / yt-dlp / Scrapy / SearXNG 等开源工具。

`find_research_resource` 使用 Open Library / Project Gutenberg、arXiv / Semantic Scholar / OpenReview / Crossref 和 Codex 官方课程搜索,统一标记公开下载、在线阅读、借阅、预览、仅元数据或未验证状态,且不绕过登录、付费墙、DRM 或校园权限。

`research_resource_workflow` 会选择一个资源结果,通过 Jina Reader 读取已验证的公开 PDF 或课程页,可选用本机 Codex SDK 生成摘要,并保存项目内 JSON + Markdown 产物。摘要使用本机 Codex 登录状态,不要求单独 API key; `summarize=False` 可完全跳过 Codex。默认拒绝未验证、借阅、预览和仅元数据资源;图书若只有 EPUB/Kindle 文件,当前只读取资源页,不声称已读取全文。

`research_compare_artifacts` 消费 2–6 个已保存 JSON artifact,不重新联网抓取,用本机 Codex 生成共识、差异、证据陈述与开放问题,并可选保存 comparison JSON/Markdown 及 `argus.research.comparison.handoff.v1`。每条可核验陈述必须同时引用已知 `S1...Sn` 和 `S1:L1` 形式 locator; locator 记录原 artifact 的 document index、section/page(若原文明确提供)、paragraph 与字符区间。来源表同时从现有 metadata 导出 DOI、arXiv、ISBN 和 BibTeX, 不会猜测缺失的 DOI 或 PDF 页码。这仍是结构追溯,不等于独立事实核验。

小红书 `xhs_*` 细化工具会先检查 `xhs_auth_status`, 未安装、未登录或 cookie 存储不可用时直接返回明确的人工处理提示; 评论、发帖、删除仍需 `confirm=True`。

---

## 🛠️ 技术栈

- Python 3.12+(开发用 3.14)· uv 包管理
- [FastMCP](https://github.com/jlowin/fastmcp) · [LiteLLM](https://github.com/BerriAI/litellm) · [Starlette](https://github.com/encode/starlette)
- [jieba](https://github.com/fxsjy/jieba) · [rank-bm25](https://github.com/dorianbrown/rank_bm25) · [ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/)
- macOS launchd(定时任务)· Cloudflare Tunnel(飞书 bot 公网入口)

上游 TrendRadar 的所有组件(热榜爬虫 / RSS / 通知 / AI 分析)保留使用。

---

## 🙏 致谢

- **[sansan0](https://github.com/sansan0)** —— TrendRadar 原作者,Argus 的全部底层爬虫与通知框架来自该项目
- **jackwener** —— 提供 `bili` / `xhs` / `twitter` / `tg` / `discord` 五个 AI-agent CLI 套件
- **[DIYgod](https://github.com/DIYgod)** —— RSSHub 作者,Argus 15 个本地 RSS 源的数据来源
- 以及 FastMCP / LiteLLM / jieba / rank-bm25 等开源依赖的维护者

完整归属见 [NOTICE.md](NOTICE.md)。

---

## 📜 协议

GPL-3.0 —— 继承上游 [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) 的协议。
本项目的所有二次开发内容同样以 GPL-3.0 发布。详见 [LICENSE](LICENSE)。
