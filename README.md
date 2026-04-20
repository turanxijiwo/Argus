# Argus

> 个人情报中枢 · 基于 [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) 的二次开发扩展
>
> 在原项目热榜聚合能力之上,新增 **154 个 MCP 工具** · 跨平台叙事追踪 · 本地 BM25 语义搜索 · 定时任务编排 · 飞书机器人反向通道 · Obsidian 导出。
>
> 协议:**GPL-3.0**(继承上游)· 完整归属见 [NOTICE.md](NOTICE.md)

---

## 🧭 这是什么

你每天要扫 10+ 个热榜,刷 5 个社媒,查几个 RSS 源,还想在一堆信息里做去重、找突发话题、看跨平台情感差异 —— Argus 把这些操作沉淀成 **154 个 MCP 工具 + 5 个 launchd 定时任务 + 1 个飞书机器人**,让 AI agent(Claude Code / Cherry Studio / 任何 MCP client)替你跑。

---

## ✨ Argus 新增能力(相对上游 TrendRadar)

| 模块 | 路径 | 作用 |
|---|---|---|
| **MCP Server** | `argus_server/` | 154 个工具,覆盖数据查询 / 分析 / 搜索 / 通知 / 自动化 |
| **跨平台叙事追踪** | `tools/cross_platform.py` | 对比同话题在 news/hn/reddit/xhs/bili/twitter 上的情感走向 |
| **本地语义搜索** | `tools/semantic_search.py` | BM25 + jieba 中文分词,跨天全文检索,<50ms 查询 |
| **Alert 规则引擎** | `tools/alerts.py` | keyword_count / anomaly / semantic_hit 三类规则 |
| **定时任务编排** | `tools/scheduler.py` + `scheduler_runner.py` | macOS launchd workflow DSL |
| **MCP client 反向挂载** | `tools/mcp_proxy.py` | 把外部 MCP server 的工具挂到本服务下 |
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
| [docs/HANDOFF.md](docs/HANDOFF.md) | 项目完整架构、MCP 工具清单、凭证位置、故障排查 |
| [docs/SCHEDULER_GUIDE.md](docs/SCHEDULER_GUIDE.md) | 定时任务 DSL 语法 / 接入飞书 / 调试方法 |
| [docs/FEISHU_BOT_SETUP.md](docs/FEISHU_BOT_SETUP.md) | 飞书反向通道接入:App 创建、Cloudflare Tunnel、联调 |
| [NOTICE.md](NOTICE.md) | 上游项目、依赖包、贡献者归属声明 |

---

## 🧩 154 个 MCP 工具速览

工具分类(详见 `argus_server/tools/` 各模块):

- **原生数据 (27)**:`get_latest_news` / `search_news` / `analyze_sentiment` / `trigger_crawl` ...
- **外部 API (54, 无 key)**:`search_arxiv` / `get_hackernews_top` / `search_reddit` / `search_gdelt` / `search_cve` ...
- **CLI 适配 (6)**:`run_bilibili` / `run_xhs` / `run_twitter` / `run_telegram` / `run_discord`
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
