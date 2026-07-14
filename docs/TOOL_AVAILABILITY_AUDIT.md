# Argus 工具真实可用性审计

审计日期: 2026-07-14
审计对象: 初始 173 个、退役 1 个并新增配置初始化后当前 173 个 FastMCP 工具
审计环境: 当前 `feature/intelligence-toolkit` 工作区与本机已安装运行时

## 结论

Argus 初始注册的 173 个工具都已纳入本次清点；永久下线的 Crossref Event Data 入口退役后曾为 172 个，新增安全配置初始化入口后当前公共面回到 173 个。本次审计得到以下关键结论:

- 初始 54 个外部 API 工具全部执行了最小真实请求；49 个至少一次返回真实数据。退役 1 个永久下线入口并修复 arXiv 可靠性后，当前 53 个外部 API 中已有 50 个真实可用，仍有 3 个阻塞。
- `universal_search` 和 `narrative_tracking` 已修复跨源参数与状态语义；真实 HN + Reddit FastMCP 探针先返回两源各 2 条，后续 Reddit 限流时正确保留 HN 结果并汇总为 partial。
- `search_all_academic` 已修复嵌套失败语义；真实限流探针保留 3 篇论文并报告 partial，后续四源 FastMCP 探针返回 complete。
- `analyze_with_ai` 已修复嵌套步骤语义；真实无 Key、无历史数据探针保留 `AUTH_REQUIRED` 与 `NO_LOCAL_DATA`，顶层正确返回 `ALL_STEPS_FAILED`。
- `system_health`、`get_system_status` 与 `system://health` 已共享同一 readiness 快照；真实 FastMCP 初始探针为 `ready=false/status=not_ready`，当前配置、509 条新闻和语义索引就绪后为 `ready=true/status=degraded`，Web `/api/health` 仍只声明 liveness。
- `initialize_config` 已在真实项目中首次返回 created、再次返回 exists；配置与 11 平台/84 RSS 源模板字节一致。
- 当前已有本地配置、覆盖 11 平台的 509 条新闻和 509 文档 BM25 索引；RSS 数据、launchd 任务、告警、路由和 MCP proxy 仍未配置。
- 通知健康检查存在一项已知误报：模板飞书 webhook 是非空占位符，当前被计为已配置。用户已明确不接入飞书/通知，因此该路径暂不整改，也不执行真实发送。
- Crawl4AI、Codex SDK、Jina Reader、Openverse 图片/音频、`gallery-dl` dry-run 和核心热榜爬虫都通过了真实安全探针。
- `research_video_metadata` 已注册为第 173 个 MCP 工具；Deno 2.9.2 已被 yt-dlp 识别为 YouTube JavaScript runtime，真实 FastMCP 调用返回公开白名单元数据且没有媒体下载或直链字段。
- 所有外部服务都存在认证、配额、速率、上游策略或网络波动风险，不存在可以合法承诺的“无限、永不失效”方案。
- 登录、付费墙、DRM、反爬和额度限制不能绕过。可行方向是使用公开 RSS、免费注册额度、用户已授权的 Codex/浏览器会话、本地服务，以及多源回退、缓存和退避。

## 状态定义

| 状态 | 含义 |
|---|---|
| 已验证 | 本次执行了非破坏性真实请求，并获得符合工具目的的数据或结果 |
| 条件可用 | 实现存在，但依赖本地数据、配置、登录、索引、外部进程或已有 artifact |
| 当前阻塞 | 当前环境缺少必要条件，或真实请求持续失败 |
| 误导性成功 | 顶层返回成功，但关键子步骤失败、为空或业务目标未完成 |
| 已废弃 | 上游已终止服务，不应继续作为可用工具宣传 |

## 审计方法与边界

1. 从 `@mcp.tool` 注册点提取工具名，初始总数为 173；退役 Crossref Event Data 后为 172，新增 `initialize_config` 后当前重新核对为 173，README 的 17 个工具族数量相加一致。
2. 对初始 54 个外部 API 工具逐一执行最小真实请求；对瞬时失败和空结果使用串行请求复核，并保留退役入口的历史证据。
3. 对 Crawl4AI、Codex SDK、Jina Reader、Openverse、`gallery-dl`、`yt-dlp` 和核心热榜爬虫执行不下载媒体、不登录、不写远端的真实探针。
4. 对发帖、点赞、通知、调度、proxy 调用、远端同步等有副作用工具，仅检查依赖、配置、调用链和空状态，不执行业务写操作。
5. 对收费、认证和额度结论核对上游官方资料。动态限额以本次响应头为证据，不保证未来不变。

## 当前 173 工具覆盖矩阵

| 工具族 | 数量 | 当前结论 | 主要证据或阻塞 |
|---|---:|---|---|
| 原生数据 | 28 | 核心链已验证 | 真实配置初始化、11/11 平台爬取、SQLite 写入和 `get_latest_news` 回读已通过；当前有 255 条新闻，RSS 仍为空 |
| 外部 API | 53 | 49 已验证，4 阻塞 | 初始 54/54 逐一真实请求；永久下线的 Crossref Event Data 已退役 |
| CLI 适配 | 7 | 当前阻塞 | 只有 `xhs` 安装但认证检查超时；`bili`、`twitter`、`tg`、`discord` 不存在 |
| AI 增强 | 8 | 当前阻塞，状态已可信 | 0/5 provider 可用；`analyze_with_ai` 已保留子步骤错误并派生 complete/partial/failed 状态 |
| 跨平台 | 2 | 条件可用，已验证 | HN + Reddit 真实聚合与叙事追踪通过；本地数据、社交登录、可选 CLI 和 Reddit 匿名额度仍影响默认源 |
| 定时任务 | 4 | 条件可用 | 当前 0 个任务；未执行 launchd 写操作 |
| MCP proxy | 5 | 条件可用 | 当前 0 个 proxy；未调用未知外部 MCP 服务 |
| 告警 | 5 | 条件可用 | 当前 0 个告警；模板飞书占位符被误报为 1/9 渠道配置，实际不可发送 |
| 导出 | 3 | 条件可用 | 已有 255 条本地新闻；导出产物仍需独立实测 |
| 语义搜索 | 4 | 已验证 | 255 文档/1,638 词 BM25 索引已构建；真实 `AI` 查询返回 5 条正分跨平台结果 |
| 健康监控 | 2 | 必需链已就绪，可选能力降级 | 配置/新闻/磁盘通过；索引/RSSHub/CLI/provider 降级，通知占位符存在 ready 误报 |
| 安全扫描 | 3 | 本地逻辑可用 | 标题和规则扫描无需外部服务；按日扫描依赖本地数据 |
| 社交细化 | 20 | 当前阻塞 | Bilibili CLI 缺失；小红书需要正常人工登录，认证检查本次超时 |
| 路由 | 5 | 条件可用 | 当前 0 个路由，实际派发还依赖通知渠道 |
| 微信公众号 RSS | 4 | 当前阻塞 | WeRSS `127.0.0.1:8080` 未运行 |
| 每日早报 | 2 | 条件可用 | 渲染依赖本地数据，推送还依赖通知渠道 |
| Research Toolkit | 18 | 混合，核心链路已验证 | Codex、Crawl4AI、Openverse、yt-dlp metadata-only、真实 crawl/workflow 通过；provider key 路径未配置 |

## 外部 API 逐项结果

### 已返回真实数据的 49 个工具

以下工具在本次环境中至少一次返回了非空真实数据。它们仍受上游限流、网络、服务政策和查询质量影响，不能据此视为永久可用。

```text
get_crypto_details, get_crypto_markets, get_crypto_trending,
get_earthquakes, get_exchange_rates, get_github_releases,
get_github_trending, get_hackernews_top, get_lobsters, get_nasa_data,
get_package_info, get_pypi_stats, get_wayback, get_weather,
get_weather_history, get_wikipedia_trending, get_worldbank_indicator,
get_youtube_channel, query_wikidata, search_all_academic,
search_artifact_hub, search_bluesky, search_books, search_crates,
search_crossref, search_cve, search_dblp, search_docker_hub,
search_exploit_db, search_flathub, search_gdelt, search_ghsa,
search_gitlab, search_hackernews, search_homebrew, search_huggingface,
search_inspire_hep, search_jsr, search_lemmy, search_mastodon,
search_musicbrainz, search_openalex, search_openreview, search_pubmed,
search_sec_edgar, search_semantic_scholar, search_stackexchange,
search_vscode_extensions, search_wikipedia
```

### 初始不可用的 5 个工具（1 个已退役）

| 工具 | 实测结果 | 根因 | 合规处理建议 |
|---|---|---|---|
| `get_crossref_events`（已退役） | 两次 SSL/EOF 失败 | Crossref Event Data 已于 2026-04-23 关闭公共 API | 已从 MCP 注册和底层适配器删除；不能靠重试恢复 |
| `search_arxiv`（已修复） | 当前官方 API 真实请求成功；新进程断网探针从持久缓存返回同一论文 | 旧实现没有遵守官方的同查询缓存和 3 秒间隔建议，且把 429 误报为网络错误 | 24 小时缓存、3 秒节流、一次有界重试和 `RATE_LIMITED` 诊断已实装；仍不承诺无限实时请求 |
| `search_github_code` | `AUTH_REQUIRED` | 当前无 `GITHUB_TOKEN`，代码搜索需要认证 | 使用用户创建的免费细粒度 token，并真正接入请求头；不能绕过 GitHub 认证 |
| `search_reddit` | Reddit JSON 返回 HTTP 403 | 当前匿名 JSON 入口被拒 | 优先使用公开 subreddit Atom/RSS；需要完整搜索时遵守 Reddit API 条款并认证 |
| `search_reliefweb` | HTTP 406 | 默认 `appname=argus` 未获批准 | 免费申请已批准 appname 并配置；申请前保持不可用状态 |

### 返回契约问题

- `search_all_academic` 修复前会在 Semantic Scholar 等子源失败时无条件返回成功；现在有论文的混合结果返回 `status=partial`，全失败或零论文返回失败 envelope，并保留来源错误与计数。
- `get_wikipedia_trending(limit=1)` 先截断再过滤 `Main_Page`，会产生假空结果；较大 limit 能返回真实数据。
- `search_ghsa(query=..., per_page=1)` 只对第一页做本地过滤，可能产生假阴性。
- `search_semantic_scholar` 首次 429、串行复测成功，说明匿名共享配额不稳定。
- GDELT 首次失败、串行复测成功，但一次请求耗时约 16 秒，需更合理的超时和缓存。
- `ExternalAPITools` 的提示提到 `GITHUB_TOKEN` 和 `SEMANTIC_SCHOLAR_API_KEY`，但当前实现没有读取这些环境变量并附加请求头；现在设置 key 不会生效。

## 本地、CLI 与聚合链路

### 原生数据

- 当前项目已通过 `initialize_config` 创建忽略跟踪的 `config/config.yaml`；重复调用返回 exists 且不覆盖，文件与模板字节一致。
- 在隔离临时目录复制 `config/config.example.yaml` 后，百度和哔哩哔哩热榜爬取成功，共返回 60 条真实标题，说明核心 crawler 可用。
- `trigger_crawl` 保留 `save_to_local` 作为兼容参数，它只控制额外 TXT/HTML 快照；SQLite 作为下游分析依赖的核心数据路径始终尝试写入。响应现在分别报告 database/snapshot 的 complete/partial/failed 状态，不再把两层持久化压缩成一个布尔值。
- 本地 storage 现有 `2026-07-14.db`：255 条新闻覆盖 11 平台、2 条 crawl record，`get_latest_news` 可真实回读；RSS 和 S3 仍未配置。
- Jina Reader 匿名读取 `https://example.com` 成功。响应头本次显示 20 次/分钟；代码内“100 RPM / 2 concurrent”的提示已经过期。

### CLI 与社交平台

| 运行时 | 当前状态 | 可用性结论 |
|---|---|---|
| `xhs` 0.6.4 | 已安装，认证/状态检查 20 秒超时 | 小红书业务工具当前不可用；只能人工正常登录或使用已有授权浏览器会话，不能绕过登录刷新机制 |
| `bili` | 未安装 | Bilibili 9 个细化工具和通用 CLI 适配不可用 |
| `twitter` / `tg` / `discord` | 未安装 | 对应 CLI 适配不可用 |
| `gallery-dl` 1.32.5 | 已安装 | `download_gallery(confirm=False)` dry-run 可用；真实 JSON 模拟探针成功且未下载媒体 |
| `yt-dlp` 2026.07.04 | 已接入 `research_video_metadata` | 使用 Deno 2.9.2 的真实 FastMCP 探针成功；输出采用白名单且剔除格式、下载、缩略图和字幕直链 |
| Scrapy 2.16.0 | 已安装但未接入 MCP | 仅健康清单可见，不等于 Argus 中已有可调用爬虫工具 |
| Codex CLI 0.144.2 | 已安装 | Codex SDK 真实研究探针成功，但消耗用户 Codex 套餐额度 |
| Node.js 20.20.2 | 已安装 | 低于 yt-dlp 当前稳定 YouTube EJS 建议版本，但不再承担该任务 |
| Deno 2.9.2 | 已安装 | yt-dlp verbose 诊断确认 `deno-2.9.2` 与 Deno challenge provider 可用 |
| ffmpeg | 未安装 | 对 metadata-only 审计和未来元数据适配器不是必需 |

### 聚合与 AI

- 修复前，`universal_search("OpenAI", limit=1)` 会在 HN 参数错误、Reddit 403、xhs 参数错误、Bilibili CLI 缺失和本地新闻为空时仍返回 `success=true`、0 条结果。
- 修复后，HN 使用实际 `hits` 契约，xhs/bili/twitter/tg/discord 使用各自 CLI 参数，Reddit 改用匿名 Atom RSS 并保留动态额度头；全失败和零结果返回失败 envelope，混合结果返回 `status=partial`。
- 真实 FastMCP `universal_search` HN + Reddit 探针返回两源各 2 条和 `status=complete`；紧接的 `narrative_tracking` 请求遇到 Reddit 匿名限流后仍保留 2 条 HN 结果，并正确返回 `status=partial` 和一个失败来源。默认五源仍可能因本地数据、人工登录、可选 CLI 缺失或匿名限流而降级，但不会再伪装成完整成功。
- `ai_summarize`、`ai_translate`、`ai_brief_news`、`semantic_deduplicate` 返回 `AUTH_REQUIRED`；`ai_web_search` 需要 provider key；`detect_anomaly` 返回 `NO_LOCAL_DATA`。
- `analyze_with_ai(mode="full")` 现在从 dedup 和 anomaly envelope 派生状态：至少一步成功时返回 complete/partial，全部失败时返回 `ALL_STEPS_FAILED`。真实无 Key、无历史数据探针保留 `AUTH_REQUIRED` 与 `NO_LOCAL_DATA`，顶层不再误报成功。

## Research Toolkit 实测

| 能力 | 实测结果 | 限制 |
|---|---|---|
| Crawl4AI 0.9.0 | 真实网页正文抓取成功 | 需要本机包、浏览器依赖和用户级缓存写权限 |
| Codex SDK | 搜索返回 URL，完整 topic -> crawl -> workflow 冒烟通过 | 不需要单独 Argus API key，但会消耗 ChatGPT/Codex 套餐用量，额度耗尽会暂停 |
| Openverse 图片 | 3 条真实 Flickr 公共领域结果，结构检查通过 | 本次匿名响应头为 20/分钟、200/天；许可仍需独立复核 |
| Openverse 音频 | 3 条 Freesound 结果，含 BY/CC0 许可元数据 | 同样观察到 20/分钟、200/天；只返回元数据，不下载音频 |
| Jina Reader | 匿名正文读取成功 | 本次观察到 20/分钟动态限额 |
| `gallery-dl` | dry-run 与模拟 JSON 探针成功 | 真实下载需要显式确认，站点规则仍可能变化 |
| `research_video_metadata` | 真实 FastMCP 调用返回 27 个公开视频元数据字段 | 只接受单项 http/https URL；不读 Cookie、不下载、不处理播放列表、不返回临时媒体直链 |
| `research_codex_smoke.py` | 1 个 URL 结果、1 个成功文档、brief、3 张图片、0 错误 | 依赖 Codex 套餐和本机用户状态 |
| `research_crawl_quality_smoke.py` | fixture 和公开 workflow 全部通过 | 公开网页仍可能临时超时或变更 |

## 认证、额度与付费审计

| 服务 | 当前 Argus 状态 | 官方限制结论 | 建议定位 |
|---|---|---|---|
| Tavily | 未配置 | 免费 key 每月 1,000 credits，之后付费 | 可选 provider，不作为唯一默认源 |
| Exa | 未配置 | API 按请求/内容计费，试用不等于长期免费 | 保持可选 |
| Perplexity | 未配置 | Search API 和 Sonar 均按请求/Token 计费 | 保持可选 |
| Brave Search API | 未配置 | 需要账户、订阅计划和信用卡；不能作为免 key 默认源 | 更新现有“免费 2,000/月”旧说明 |
| Codex SDK | 已验证 | 与 ChatGPT/Codex 套餐共享 credits/usage limits；API-key 模式另按 token 计费 | 适合个人研究回退和综合，不应描述为无限免费 |
| OpenAlex | 匿名 demo 成功 | 2026 年政策要求 key 才能稳定使用；免费 key 含每日额度，超出后按量计费 | 增加免费 key 配置，匿名仅作探针 |
| Semantic Scholar | 匿名复测成功 | 匿名共享配额不稳定；免费 key 推荐，初始通常约 1 RPS | 正确接入免费 key 与退避 |
| GitHub REST | 公共端点可用，代码搜索阻塞 | 匿名核心 REST 60 次/小时；认证通常 5,000 次/小时，搜索另有更紧桶 | 免费 token 是正规方案，不绕过认证 |
| ReliefWeb | 406 | 需要免费申请并获批 `appname` | 申请后配置 |
| Openverse | 匿名已验证 | 支持匿名但限额动态；可注册 OAuth 提高稳定性 | 保留默认元数据源并缓存 |
| arXiv | 无 key 真实查询和持久缓存已验证 | 官方建议连续请求间隔 3 秒；同查询结果一天内无需重复请求 | 使用 24 小时缓存与有界退避，持续限流保持失败诊断 |
| 小红书/Bilibili 等 | 当前 CLI 不就绪 | 平台登录、风控和服务条款持续生效 | 只使用正常登录或已有授权会话 |

官方资料:

- [Tavily API credits](https://docs.tavily.com/documentation/api-credits)
- [Exa API pricing](https://exa.ai/pricing?tab=api)
- [Perplexity API pricing](https://docs.perplexity.ai/docs/getting-started/pricing)
- [Brave Search API quickstart](https://api-dashboard.search.brave.com/documentation/quickstart)
- [Openverse API](https://api.openverse.org/)
- [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html)
- [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2026-03-10)
- [Semantic Scholar API](https://www.semanticscholar.org/product/api)
- [Crossref Event Data sunset](https://www.crossref.org/documentation/event-data/)
- [ReliefWeb API documentation](https://apidoc.reliefweb.int/index.html)
- [Reddit Data API terms](https://redditinc.com/policies/data-api-terms)
- [OpenAlex API pricing changes](https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/)
- [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md) 与 [EJS runtime guidance](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- [Codex pricing](https://learn.chatgpt.com/docs/pricing.md)

## 可替代方案

| 当前问题 | 可采用方案 | 不能承诺的内容 |
|---|---|---|
| 通用网页搜索 provider 需要付费 key | 公共垂直 API + Codex 回退；后续独立评估本地 SearXNG | SearXNG 也会受上游搜索引擎封锁和限流，不是无限出口 |
| Reddit JSON 403 | 公开 subreddit Atom/RSS 作为只读回退 | RSS 不提供完整站内搜索，也不能绕过私有/登录内容 |
| arXiv 429 | 24 小时缓存、3 秒节流与一次有界重试已实装；聚合路径仍可保留 Semantic Scholar/OpenAlex/Crossref 结果 | 持续限流仍可发生；回退源不能冒充 arXiv 原始响应 |
| GitHub 代码搜索认证 | 用户免费 token，或用户已授权的 GitHub/Codex 浏览器能力 | 不能跳过认证或伪造更高额度 |
| ReliefWeb 406 | 免费申请 approved appname | 未批准前不能声称可用 |
| Crossref Event Data 下线 | 已删除工具；按具体需求改用 GDELT、Crossref Works 或来源 RSS | 这些来源不是 Event Data 的一比一替代 |
| AI 摘要/翻译/去重缺 key | 增加 Codex SDK 可选后端 | 使用的是用户套餐额度，不是免费无限 API |
| 小红书登录失效 | 正常人工登录，或在用户已登录浏览器中由 Codex 操作 | 不能绕过登录、自动窃取/刷新 cookie 或规避风控 |
| YouTube 元数据 | Deno runtime 与严格 metadata-only yt-dlp MCP 适配器均已就绪 | 不下载受限媒体，不返回临时直链，不导入浏览器 Cookie |

## 整改优先级

### P0: 先让状态可信

1. ~~删除或禁用 `get_crossref_events`。~~ 已于 2026-07-14 从 MCP 注册、底层适配器和启动清单退役。
2. ~~修复 `universal_search` / `narrative_tracking` 的 Hacker News 参数、Reddit 回退、xhs 参数和 partial/failed 语义。~~ 已于 2026-07-14 完成，并通过真实 HN + Reddit 完整及限流降级探针。
3. ~~统一健康检查，明确区分“检查执行成功”和“业务已就绪”，纳入配置、数据、索引、CLI、provider 和通知渠道。~~ 已于 2026-07-14 完成；真实 FastMCP 初始返回 `ready=false/status=not_ready`，配置与数据就绪后转为 `ready=true/status=degraded`，公开入口共享同一快照。
4. ~~让 `search_all_academic` 和 `analyze_with_ai` 正确返回 partial/failed，不能隐藏关键子步骤失败。~~ 已于 2026-07-14 分两项完成，并分别通过真实受限环境探针与回归测试。

### P1: 恢复基础业务就绪

1. ~~增加本地配置初始化流程，并修正 `save_to_local=False` 的误导性持久化响应。~~ 两项均已完成；真实 FastMCP 配置创建/幂等、单平台爬取、SQLite 回读和分层持久化回归均已通过。
2. ~~扩充本地新闻覆盖并构建语义索引。~~ 11/11 平台、359 条新闻、359 文档 BM25 索引和真实跨平台查询均已通过。
3. ~~Reddit RSS 回退和 arXiv 缓存/退避已完成。~~ ReliefWeb 仍需免费申请 approved appname 后配置。
4. 真正接入 GitHub、Semantic Scholar、OpenAlex 的认证头，并暴露动态 rate-limit 信息。
5. 更新 Jina、OpenAlex、Brave 和 Codex 的额度说明。

明确不在当前范围：飞书与其他通知集成。模板占位符的 readiness 误报仅保留已知问题记录，不排入当前开发计划。

### P2: 扩充个人研究能力

1. 给摘要、翻译和去重增加显式 Codex SDK 后端，并显示会消耗 Codex 套餐额度。
2. Deno 与 metadata-only yt-dlp MCP 适配器已完成；后续只需维护真实站点兼容性，不扩大到 Cookie 或媒体下载。
3. 独立审计 Docker 本地 SearXNG 的搜索质量、失败率和上游限流后，再决定是否接入。

## 完整注册清单

以下清单用于证明当前 173 个注册工具都被纳入工具族审计。混合状态工具族的具体例外以前文为准。

- 原生数据 28: `resolve_date_range`, `get_latest_news`, `get_trending_topics`, `get_latest_rss`, `search_rss`, `get_rss_feeds_status`, `get_news_by_date`, `analyze_topic_trend`, `analyze_data_insights`, `analyze_sentiment`, `find_related_news`, `generate_summary_report`, `aggregate_news`, `compare_periods`, `search_news`, `initialize_config`, `get_current_config`, `get_system_status`, `check_version`, `trigger_crawl`, `sync_from_remote`, `get_storage_status`, `list_available_dates`, `read_article`, `read_articles_batch`, `get_channel_format_guide`, `get_notification_channels`, `send_notification`.
- 外部 API 53: 前述 50 个已验证工具，加仍阻塞的 `search_github_code`, `search_reddit`, `search_reliefweb`；已退役的 `get_crossref_events` 仅保留在历史审计表中。
- AI 增强 8: `check_ai_providers`, `ai_summarize`, `ai_translate`, `ai_brief_news`, `ai_web_search`, `semantic_deduplicate`, `detect_anomaly`, `analyze_with_ai`。
- 跨平台 2: `narrative_tracking`, `universal_search`。
- Research Toolkit 18: `research_toolkit_health`, `crawl_url`, `discover_page_images`, `download_gallery`, `research_topic`, `find_research_resource`, `research_resource_workflow`, `research_compare_artifacts`, `research_audit_comparison`, `research_resolve_locators`, `research_images`, `research_audio`, `research_video_metadata`, `research_pack`, `research_workflow`, `research_batch_workflow`, `research_review_artifact`, `research_runtime_probe`。
- 定时任务 4: `schedule_task`, `list_scheduled_tasks`, `remove_scheduled_task`, `run_scheduled_task`。
- MCP proxy 5: `mcp_proxy_add`, `mcp_proxy_remove`, `mcp_proxy_list`, `mcp_proxy_list_tools`, `mcp_proxy_call`。
- 微信公众号 RSS 4: `wechat_rss_status`, `wechat_add_feed`, `wechat_list_feeds`, `wechat_remove_feed`。
- 语义搜索 4: `semantic_index_rebuild`, `semantic_index_status`, `semantic_search`, `semantic_similar`。
- 告警 5: `alert_add`, `alert_list`, `alert_remove`, `alert_test`, `alert_run_all`。
- 导出 3: `export_daily_brief`, `export_query_report`, `export_anomalies`。
- 健康监控 2: `system_health`, `tool_stats`。
- 安全扫描 3: `safety_scan_titles`, `safety_scan_day`, `safety_list_rules`。
- 社交细化 20: `bili_my_dynamics`, `bili_history`, `bili_following`, `bili_feed`, `bili_hot`, `bili_like`, `bili_triple`, `bili_publish_dynamic`, `bili_delete_dynamic`, `xhs_my_notes`, `xhs_notifications`, `xhs_favorites`, `xhs_feed`, `xhs_hot`, `xhs_comments`, `xhs_like`, `xhs_favorite`, `xhs_comment`, `xhs_publish_note`, `xhs_delete_note`。
- 路由 5: `route_add`, `route_list`, `route_remove`, `route_test`, `route_dispatch`。
- 每日早报 2: `push_daily_brief`, `render_daily_brief`。
- CLI 适配 7: `check_cli_auth`, `xhs_auth_status`, `run_bilibili`, `run_xhs`, `run_twitter`, `run_telegram`, `run_discord`。

## 审计解释

这份报告证明的是“当前日期、当前机器、当前配置下”的真实状态，不是对第三方服务未来可用性的担保。Argus 当前 173 个工具仍是注册面统计，不能整体描述为“全部可直接使用”。
