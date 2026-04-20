# Argus

> Personal intelligence hub · A fork and extension of [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)
>
> On top of the original news aggregation core, Argus adds **154 MCP tools** · cross-platform narrative tracking · local BM25 semantic search · launchd-based scheduler · Feishu bot reverse channel · Obsidian exporter.
>
> License: **GPL-3.0** (inherited from upstream) · See [NOTICE.md](NOTICE.md) for attribution.

---

## 🧭 What is it

You scan 10+ hot lists, 5 social feeds, a dozen RSS sources daily, and want to deduplicate, spot emerging topics, and compare sentiment across platforms. Argus consolidates these operations into **154 MCP tools + 5 launchd scheduled jobs + 1 Feishu bot**, so any MCP client (Claude Code, Cherry Studio, etc.) can run them for you.

---

## ✨ What Argus adds (on top of TrendRadar)

| Module | Path | Purpose |
|---|---|---|
| **MCP Server** | `argus_server/` | 154 tools: query / analyze / search / notify / automate |
| **Cross-platform narrative** | `tools/cross_platform.py` | Compare sentiment on news/hn/reddit/xhs/bili/twitter for the same topic |
| **Local semantic search** | `tools/semantic_search.py` | BM25 + jieba Chinese segmentation, full-text across days, <50ms |
| **Alert rule engine** | `tools/alerts.py` | `keyword_count` / `anomaly` / `semantic_hit` |
| **Scheduler** | `tools/scheduler.py` + `scheduler_runner.py` | macOS launchd workflow DSL |
| **MCP reverse proxy** | `tools/mcp_proxy.py` | Mount external MCP servers as sub-tools |
| **Notification router** | `tools/router.py` | Route to multiple Feishu/DingTalk/Bark groups by keyword |
| **Feishu bot channel** | `feishu_bot.py` | `@bot` in a group → invoke MCP tool → reply |
| **Obsidian exporter** | `tools/exporter.py` | Daily brief / query report / anomaly report → markdown vault |
| **Safety scanner** | `tools/safety.py` | PII / scam / spam / NSFW rule scans |
| **Telemetry + health** | `tools/telemetry.py` | Tool call stats, latency, error rate |
| **Web Dashboard** | `argus/web/` | Starlette + SSE live dashboard |

All upstream TrendRadar features (crawlers / RSS / notifications / AI analysis) are preserved.

---

## 🚀 Quick start

```bash
git clone https://github.com/turanxijiwo/Argus.git
cd Argus
uv sync
cp config/config.example.yaml config/config.yaml   # then edit it
.venv/bin/argus --now                               # crawl once
```

MCP client config:
```json
{
  "mcpServers": {
    "argus": {
      "command": "/path/to/Argus/.venv/bin/argus-mcp"
    }
  }
}
```

Optional services:
```bash
./scripts/start-web.sh bg           # Web dashboard (:5173)
./scripts/start-feishu-bot.sh bg    # Feishu reverse channel (:6600)
```

---

## 📚 Docs

| File | Contents |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | Full architecture, 154-tool catalog, credentials, troubleshooting |
| [docs/SCHEDULER_GUIDE.md](docs/SCHEDULER_GUIDE.md) | Workflow DSL, Feishu integration, debugging |
| [docs/FEISHU_BOT_SETUP.md](docs/FEISHU_BOT_SETUP.md) | Feishu App creation, Cloudflare Tunnel, end-to-end setup |
| [NOTICE.md](NOTICE.md) | Attribution for upstream project, dependencies, contributors |

---

## 🛠️ Stack

- Python 3.12+ (tested on 3.14) · [uv](https://github.com/astral-sh/uv) package manager
- [FastMCP](https://github.com/jlowin/fastmcp) · [LiteLLM](https://github.com/BerriAI/litellm) · [Starlette](https://github.com/encode/starlette)
- [jieba](https://github.com/fxsjy/jieba) · [rank-bm25](https://github.com/dorianbrown/rank_bm25) · [ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/)
- macOS launchd (scheduler) · Cloudflare Tunnel (Feishu bot ingress)

---

## 🙏 Credits

- **[sansan0](https://github.com/sansan0)** — author of TrendRadar, whose crawler / notification / AI framework forms Argus' foundation
- **jackwener** — maintainer of `bili` / `xhs` / `twitter` / `tg` / `discord` agent-CLI suite
- **[DIYgod](https://github.com/DIYgod)** — author of RSSHub, source of 15 local RSS routes
- Plus maintainers of FastMCP, LiteLLM, jieba, rank-bm25 and other dependencies

Full list in [NOTICE.md](NOTICE.md).

---

## 📜 License

GPL-3.0 — inherited from [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar). See [LICENSE](LICENSE).
