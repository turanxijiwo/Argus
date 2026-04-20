"""
Argus MCP Server - FastMCP 2.0 实现

使用 FastMCP 2.0 提供生产级 MCP 工具服务器。
支持 stdio 和 HTTP 两种传输模式。
"""

import asyncio
import json
from typing import Any, List, Optional, Dict, Union

from fastmcp import FastMCP

from .tools.data_query import DataQueryTools
from .tools.analytics import AnalyticsTools
from .tools.search_tools import SearchTools
from .tools.config_mgmt import ConfigManagementTools
from .tools.system import SystemManagementTools
from .tools.storage_sync import StorageSyncTools
from .tools.article_reader import ArticleReaderTools
from .tools.notification import NotificationTools
from .tools.external_apis import ExternalAPITools
from .tools.cli_tools import CLIToolsAdapter
from .tools.ai_enhanced import AIEnhancedTools
from .tools.ai_analytics import AIAnalyticsTools
from .tools.cross_platform import CrossPlatformTools
from .tools.scheduler import SchedulerTools
from .tools.mcp_proxy import MCPProxyTools
from .tools.wechat import WechatRSSTools
from .tools.semantic_search import SemanticSearchTools
from .tools.alerts import AlertTools
from .tools.exporter import ExporterTools
from .tools.telemetry import HealthTools, TelemetryStore
from .tools.safety import SafetyTools
from .tools.social_ops import SocialOpsTools
from .tools.router import RouterTools
from .tools.daily_brief import DailyBriefTools
from .utils.date_parser import DateParser
from .utils.errors import MCPError


# 创建 FastMCP 2.0 应用
mcp = FastMCP('argus')

# 全局工具实例（在第一次请求时初始化）
_tools_instances = {}


def _get_tools(project_root: Optional[str] = None):
    """获取或创建工具实例（单例模式）"""
    if not _tools_instances:
        _tools_instances['data'] = DataQueryTools(project_root)
        _tools_instances['analytics'] = AnalyticsTools(project_root)
        _tools_instances['search'] = SearchTools(project_root)
        _tools_instances['config'] = ConfigManagementTools(project_root)
        _tools_instances['system'] = SystemManagementTools(project_root)
        _tools_instances['storage'] = StorageSyncTools(project_root)
        _tools_instances['article'] = ArticleReaderTools(project_root)
        _tools_instances['notification'] = NotificationTools(project_root)
        _tools_instances['external'] = ExternalAPITools(project_root)
        _tools_instances['cli'] = CLIToolsAdapter(project_root)
        _tools_instances['ai'] = AIEnhancedTools(project_root)
        _tools_instances['ai_analytics'] = AIAnalyticsTools(project_root)
        _tools_instances['cross'] = CrossPlatformTools(
            project_root,
            cli_adapter=_tools_instances['cli'],
            external_api=_tools_instances['external'],
            search_tools=_tools_instances['search'],
        )
        _tools_instances['scheduler'] = SchedulerTools(project_root)
        _tools_instances['mcp_proxy'] = MCPProxyTools(project_root)
        _tools_instances['wechat'] = WechatRSSTools(project_root)
        _tools_instances['semantic'] = SemanticSearchTools(project_root)
        _tools_instances['alerts'] = AlertTools(
            project_root,
            notification_adapter=_tools_instances['notification'],
            ai_analytics_adapter=_tools_instances['ai_analytics'],
            semantic_adapter=_tools_instances['semantic'],
        )
        _tools_instances['exporter'] = ExporterTools(
            project_root,
            storage_adapter=_tools_instances['storage'],
            ai_analytics_adapter=_tools_instances['ai_analytics'],
            semantic_adapter=_tools_instances['semantic'],
        )
        _tools_instances['health'] = HealthTools(project_root)
        _tools_instances['safety'] = SafetyTools(project_root)
        _tools_instances['social'] = SocialOpsTools(project_root, cli_adapter=_tools_instances['cli'])
        _tools_instances['router'] = RouterTools(project_root)
        _tools_instances['daily_brief'] = DailyBriefTools(
            project_root,
            notification_adapter=_tools_instances['notification'],
        )
        # 确保 telemetry store 启动 (单例)
        TelemetryStore.instance(project_root)
    return _tools_instances


# ==================== MCP Resources ====================

@mcp.resource("config://platforms")
async def get_platforms_resource() -> str:
    """
    获取支持的平台列表

    返回 config.yaml 中配置的所有平台信息，包括 ID 和名称。
    """
    tools = _get_tools()
    config = await asyncio.to_thread(
        tools['config'].get_current_config, section="crawler"
    )
    return json.dumps({
        "platforms": config.get("platforms", []),
        "description": "Argus 支持的热榜平台列表"
    }, ensure_ascii=False, indent=2)


@mcp.resource("config://rss-feeds")
async def get_rss_feeds_resource() -> str:
    """
    获取 RSS 订阅源列表

    返回当前配置的所有 RSS 源信息。
    """
    tools = _get_tools()
    status = await asyncio.to_thread(tools['data'].get_rss_feeds_status)
    return json.dumps({
        "feeds": status.get("today_feeds", {}),
        "description": "Argus 支持的 RSS 订阅源列表"
    }, ensure_ascii=False, indent=2)


@mcp.resource("data://available-dates")
async def get_available_dates_resource() -> str:
    """
    获取可用的数据日期范围

    返回本地存储中可查询的日期列表。
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['storage'].list_available_dates, source="local"
    )
    return json.dumps({
        "dates": result.get("data", {}).get("local", {}).get("dates", []),
        "description": "本地存储中可查询的日期列表"
    }, ensure_ascii=False, indent=2)


@mcp.resource("config://keywords")
async def get_keywords_resource() -> str:
    """
    获取关注词配置

    返回 frequency_words.txt 中配置的关注词分组。
    """
    tools = _get_tools()
    config = await asyncio.to_thread(
        tools['config'].get_current_config, section="keywords"
    )
    return json.dumps({
        "word_groups": config.get("word_groups", []),
        "total_groups": config.get("total_groups", 0),
        "description": "Argus 关注词配置"
    }, ensure_ascii=False, indent=2)


# ==================== Batch 11: 新增 MCP resource ====================

@mcp.resource("data://today-summary")
async def get_today_summary_resource() -> str:
    """
    今日热点速览 (最新日期的总数 / 平台分布 / top 10 关键词)

    供 AI 订阅上下文, 不用每次手动调多个工具。
    """
    tools = _get_tools()
    try:
        dates_result = await asyncio.to_thread(
            tools['storage'].list_available_dates, source="local"
        )
        dates = (dates_result.get("data") or {}).get("local", {}).get("dates") or []
        if not dates:
            return json.dumps({"error": "no_data"}, ensure_ascii=False)
        latest = dates[0]
        news = await asyncio.to_thread(
            tools['data'].get_latest_news, date_range={"start": latest, "end": latest}, limit=1
        )
        summary_data = (news.get("data") or {}) if isinstance(news, dict) else {}
        return json.dumps({
            "latest_date": latest,
            "total_dates_available": len(dates),
            "hint": "用 get_latest_news / semantic_search 获取详情",
            "summary": summary_data,
        }, ensure_ascii=False, indent=2, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


@mcp.resource("data://anomalies-latest")
async def get_latest_anomalies_resource() -> str:
    """最近一次异常检测结果 (z_threshold=2.0, 7 天)"""
    tools = _get_tools()
    try:
        result = await asyncio.to_thread(
            tools['ai_analytics'].detect_anomaly,
            lookback_days=7, z_threshold=2.0, top_n=20,
        )
        anomalies = (result.get("data") or {}).get("anomalies") or []
        return json.dumps({
            "count": len(anomalies),
            "anomalies": anomalies,
        }, ensure_ascii=False, indent=2, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


@mcp.resource("system://health")
async def get_system_health_resource() -> str:
    """系统健康快照 (数据/索引/RSSHub/磁盘/任务/告警)"""
    tools = _get_tools()
    try:
        result = await asyncio.to_thread(tools['health'].system_health)
        return json.dumps(result.get("data") or result, ensure_ascii=False, indent=2, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


@mcp.resource("system://tool-stats")
async def get_tool_stats_resource() -> str:
    """工具调用统计快照"""
    tools = _get_tools()
    try:
        result = await asyncio.to_thread(tools['health'].tool_stats, top_n=20)
        return json.dumps(result.get("data") or result, ensure_ascii=False, indent=2, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


# ==================== 日期解析工具（优先调用）====================

@mcp.tool
async def resolve_date_range(
    expression: str
) -> str:
    """
    【推荐优先调用】将自然语言日期表达式解析为标准日期范围

    **为什么需要这个工具？**
    用户经常使用"本周"、"最近7天"等自然语言表达日期，但 AI 模型自己计算日期
    可能导致不一致的结果。此工具在服务器端使用精确的当前时间计算，确保所有
    AI 模型获得一致的日期范围。

    **推荐使用流程：**
    1. 用户说"分析AI本周的情感倾向"
    2. AI 调用 resolve_date_range("本周") → 获取精确日期范围
    3. AI 调用 analyze_sentiment(topic="ai", date_range=上一步返回的date_range)

    Args:
        expression: 自然语言日期表达式，支持：
            - 单日: "今天", "昨天", "today", "yesterday"
            - 周: "本周", "上周", "this week", "last week"
            - 月: "本月", "上月", "this month", "last month"
            - 最近N天: "最近7天", "最近30天", "last 7 days", "last 30 days"
            - 动态: "最近5天", "last 10 days"（任意天数）

    Returns:
        JSON格式的日期范围，可直接用于其他工具的 date_range 参数：
        {
            "success": true,
            "expression": "本周",
            "date_range": {
                "start": "2025-11-18",
                "end": "2025-11-26"
            },
            "current_date": "2025-11-26",
            "description": "本周（周一到周日，11-18 至 11-26）"
        }

    Examples:
        用户："分析AI本周的情感倾向"
        AI调用步骤：
        1. resolve_date_range("本周")
           → {"date_range": {"start": "2025-11-18", "end": "2025-11-26"}, ...}
        2. analyze_sentiment(topic="ai", date_range={"start": "2025-11-18", "end": "2025-11-26"})

        用户："看看最近7天的特斯拉新闻"
        AI调用步骤：
        1. resolve_date_range("最近7天")
           → {"date_range": {"start": "2025-11-20", "end": "2025-11-26"}, ...}
        2. search_news(query="特斯拉", date_range={"start": "2025-11-20", "end": "2025-11-26"})
    """
    try:
        result = await asyncio.to_thread(DateParser.resolve_date_range_expression, expression)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except MCPError as e:
        return json.dumps({
            "success": False,
            "error": e.to_dict()
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }, ensure_ascii=False, indent=2)


# ==================== 数据查询工具 ====================

@mcp.tool
async def get_latest_news(
    platforms: Optional[List[str]] = None,
    limit: int = 50,
    include_url: bool = False
) -> str:
    """
    获取最新一批爬取的新闻数据，快速了解当前热点

    Args:
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        limit: 返回条数限制，默认50，最大1000
        include_url: 是否包含URL链接，默认False（节省token）

    Returns:
        JSON格式的新闻列表

    **数据展示建议**
    - 默认展示全部返回数据，除非用户明确要求总结
    - 用户说"总结"或"挑重点"时才进行筛选
    - 用户问"为什么只显示部分"说明需要完整数据
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['data'].get_latest_news,
        platforms=platforms, limit=limit, include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_trending_topics(
    top_n: int = 10,
    mode: str = 'current',
    extract_mode: str = 'keywords'
) -> str:
    """
    获取热点话题统计

    Args:
        top_n: 返回TOP N话题，默认10
        mode: 时间模式
            - "daily": 当日累计数据统计
            - "current": 最新一批数据统计（默认）
        extract_mode: 提取模式
            - "keywords": 统计预设关注词（基于 config/frequency_words.txt，默认）
            - "auto_extract": 自动从新闻标题提取高频词（无需预设，自动发现热点）

    Returns:
        JSON格式的话题频率统计列表

    Examples:
        - 使用预设关注词: get_trending_topics(mode="current")
        - 自动提取热点: get_trending_topics(extract_mode="auto_extract", top_n=20)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['data'].get_trending_topics,
        top_n=top_n, mode=mode, extract_mode=extract_mode
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== RSS 数据查询工具 ====================

@mcp.tool
async def get_latest_rss(
    feeds: Optional[List[str]] = None,
    days: int = 1,
    limit: int = 50,
    include_summary: bool = False
) -> str:
    """
    获取最新的 RSS 订阅数据（支持多日查询）

    RSS 数据与热榜新闻分开存储，按时间流展示，适合获取特定来源的最新内容。

    Args:
        feeds: RSS 源 ID 列表，如 ['hacker-news', '36kr']，不指定则返回所有源
        days: 获取最近 N 天的数据，默认 1（仅今天），最大 30 天
        limit: 返回条数限制，默认50，最大500
        include_summary: 是否包含文章摘要，默认False（节省token）

    Returns:
        JSON格式的 RSS 条目列表

    Examples:
        - get_latest_rss()
        - get_latest_rss(days=7, feeds=['hacker-news'])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['data'].get_latest_rss,
        feeds=feeds, days=days, limit=limit, include_summary=include_summary
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_rss(
    keyword: str,
    feeds: Optional[List[str]] = None,
    days: int = 7,
    limit: int = 50,
    include_summary: bool = False
) -> str:
    """
    搜索 RSS 数据

    在 RSS 订阅数据中搜索包含指定关键词的文章。

    Args:
        keyword: 搜索关键词（必需）
        feeds: RSS 源 ID 列表，如 ['hacker-news', '36kr']
               - 不指定时：搜索所有 RSS 源
        days: 搜索最近 N 天的数据，默认 7 天，最大 30 天
        limit: 返回条数限制，默认50
        include_summary: 是否包含文章摘要，默认False

    Returns:
        JSON格式的匹配 RSS 条目列表

    Examples:
        - search_rss(keyword="AI")
        - search_rss(keyword="machine learning", feeds=['hacker-news'], days=14)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['data'].search_rss,
        keyword=keyword,
        feeds=feeds,
        days=days,
        limit=limit,
        include_summary=include_summary
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_rss_feeds_status() -> str:
    """
    获取 RSS 源状态信息

    查看当前配置的 RSS 源及其数据统计信息。

    Returns:
        JSON格式的 RSS 源状态，包含：
        - available_dates: 有 RSS 数据的日期列表
        - total_dates: 总日期数
        - today_feeds: 今日各 RSS 源的数据统计
            - {feed_id}: { name, item_count }
        - generated_at: 生成时间

    Examples:
        - get_rss_feeds_status()  # 查看所有 RSS 源状态
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['data'].get_rss_feeds_status)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_news_by_date(
    date_range: Optional[Union[Dict[str, str], str]] = None,
    platforms: Optional[List[str]] = None,
    limit: int = 50,
    include_url: bool = False
) -> str:
    """
    获取指定日期的新闻数据，用于历史数据分析和对比

    Args:
        date_range: 日期范围，支持多种格式:
            - 范围对象: {"start": "2025-01-01", "end": "2025-01-07"}
            - 自然语言: "今天", "昨天", "本周", "最近7天"
            - 单日字符串: "2025-01-15"
            - 默认值: "今天"
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        limit: 返回条数限制，默认50，最大1000
        include_url: 是否包含URL链接，默认False（节省token）

    Returns:
        JSON格式的新闻列表，包含标题、平台、排名等信息
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['data'].get_news_by_date,
        date_range=date_range,
        platforms=platforms,
        limit=limit,
        include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)



# ==================== 高级数据分析工具 ====================

@mcp.tool
async def analyze_topic_trend(
    topic: str,
    analysis_type: str = "trend",
    date_range: Optional[Union[Dict[str, str], str]] = None,
    granularity: str = "day",
    spike_threshold: float = 3.0,
    time_window: int = 24,
    lookahead_hours: int = 6,
    confidence_threshold: float = 0.7
) -> str:
    """
    统一话题趋势分析工具 - 整合多种趋势分析模式

    建议：使用自然语言日期时，先调用 resolve_date_range 获取精确日期范围。

    Args:
        topic: 话题关键词（必需）
        analysis_type: 分析类型
            - "trend": 热度趋势分析（默认）
            - "lifecycle": 生命周期分析
            - "viral": 异常热度检测
            - "predict": 话题预测
        date_range: 日期范围，格式 {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}，默认最近7天
        granularity: 时间粒度，默认"day"
        spike_threshold: 热度突增倍数阈值（viral模式），默认3.0
        time_window: 检测时间窗口小时数（viral模式），默认24
        lookahead_hours: 预测未来小时数（predict模式），默认6
        confidence_threshold: 置信度阈值（predict模式），默认0.7

    Returns:
        JSON格式的趋势分析结果

    Examples:
        - analyze_topic_trend(topic="AI", date_range={"start": "2025-01-01", "end": "2025-01-07"})
        - analyze_topic_trend(topic="特斯拉", analysis_type="lifecycle")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].analyze_topic_trend_unified,
        topic=topic,
        analysis_type=analysis_type,
        date_range=date_range,
        granularity=granularity,
        threshold=spike_threshold,
        time_window=time_window,
        lookahead_hours=lookahead_hours,
        confidence_threshold=confidence_threshold
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def analyze_data_insights(
    insight_type: str = "platform_compare",
    topic: Optional[str] = None,
    date_range: Optional[Union[Dict[str, str], str]] = None,
    min_frequency: int = 3,
    top_n: int = 20
) -> str:
    """
    统一数据洞察分析工具 - 整合多种数据分析模式

    Args:
        insight_type: 洞察类型，可选值：
            - "platform_compare": 平台对比分析（对比不同平台对话题的关注度）
            - "platform_activity": 平台活跃度统计（统计各平台发布频率和活跃时间）
            - "keyword_cooccur": 关键词共现分析（分析关键词同时出现的模式）
        topic: 话题关键词（可选，platform_compare模式适用）
        date_range: **【对象类型】** 日期范围（可选）
                    - **格式**: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
                    - **示例**: {"start": "2025-01-01", "end": "2025-01-07"}
                    - **重要**: 必须是对象格式，不能传递整数
        min_frequency: 最小共现频次（keyword_cooccur模式），默认3
        top_n: 返回TOP N结果（keyword_cooccur模式），默认20

    Returns:
        JSON格式的数据洞察分析结果

    Examples:
        - analyze_data_insights(insight_type="platform_compare", topic="人工智能")
        - analyze_data_insights(insight_type="platform_activity", date_range={"start": "2025-01-01", "end": "2025-01-07"})
        - analyze_data_insights(insight_type="keyword_cooccur", min_frequency=5, top_n=15)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].analyze_data_insights_unified,
        insight_type=insight_type,
        topic=topic,
        date_range=date_range,
        min_frequency=min_frequency,
        top_n=top_n
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def analyze_sentiment(
    topic: Optional[str] = None,
    platforms: Optional[List[str]] = None,
    date_range: Optional[Union[Dict[str, str], str]] = None,
    limit: int = 50,
    sort_by_weight: bool = True,
    include_url: bool = False
) -> str:
    """
    分析新闻的情感倾向和热度趋势

    建议：使用自然语言日期时，先调用 resolve_date_range 获取精确日期范围。

    Args:
        topic: 话题关键词（可选）
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        date_range: 日期范围，格式 {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}，默认今天
        limit: 返回新闻数量，默认50，最大100（会对标题去重）
        sort_by_weight: 是否按热度权重排序，默认True
        include_url: 是否包含URL链接，默认False（节省token）

    Returns:
        JSON格式的分析结果，包含情感分布、热度趋势和相关新闻

    Examples:
        - analyze_sentiment(topic="AI", date_range={"start": "2025-01-01", "end": "2025-01-07"})
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].analyze_sentiment,
        topic=topic,
        platforms=platforms,
        date_range=date_range,
        limit=limit,
        sort_by_weight=sort_by_weight,
        include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def find_related_news(
    reference_title: str,
    date_range: Optional[Union[Dict[str, str], str]] = None,
    threshold: float = 0.5,
    limit: int = 50,
    include_url: bool = False
) -> str:
    """
    查找与指定新闻标题相关的其他新闻（支持当天和历史数据）

    Args:
        reference_title: 参考新闻标题（完整或部分）
        date_range: 日期范围（可选）
            - 不指定: 只查询今天的数据
            - "today", "yesterday", "last_week", "last_month": 预设值
            - {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}: 自定义范围
        threshold: 相似度阈值，0-1之间，默认0.5（越高匹配越严格）
        limit: 返回条数限制，默认50
        include_url: 是否包含URL链接，默认False（节省token）

    Returns:
        JSON格式的相关新闻列表，按相似度排序

    Examples:
        - find_related_news(reference_title="特斯拉降价")
        - find_related_news(reference_title="AI突破", date_range="last_week")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['search'].find_related_news_unified,
        reference_title=reference_title,
        date_range=date_range,
        threshold=threshold,
        limit=limit,
        include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def generate_summary_report(
    report_type: str = "daily",
    date_range: Optional[Union[Dict[str, str], str]] = None
) -> str:
    """
    每日/每周摘要生成器 - 自动生成热点摘要报告

    Args:
        report_type: 报告类型（daily/weekly）
        date_range: **【对象类型】** 自定义日期范围（可选）
                    - **格式**: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
                    - **示例**: {"start": "2025-01-01", "end": "2025-01-07"}
                    - **重要**: 必须是对象格式，不能传递整数

    Returns:
        JSON格式的摘要报告，包含Markdown格式内容
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].generate_summary_report,
        report_type=report_type,
        date_range=date_range
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def aggregate_news(
    date_range: Optional[Union[Dict[str, str], str]] = None,
    platforms: Optional[List[str]] = None,
    similarity_threshold: float = 0.7,
    limit: int = 50,
    include_url: bool = False
) -> str:
    """
    跨平台新闻聚合 - 对相似新闻进行去重合并

    将不同平台报道的同一事件合并为一条聚合新闻，显示跨平台覆盖情况和综合热度。

    Args:
        date_range: 日期范围，不指定则查询今天
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        similarity_threshold: 相似度阈值，0.3-1.0，默认0.7（越高越严格）
        limit: 返回聚合新闻数量，默认50
        include_url: 是否包含URL链接，默认False

    Returns:
        JSON格式的聚合结果，包含去重统计、聚合新闻列表和平台覆盖统计

    Examples:
        - aggregate_news()
        - aggregate_news(similarity_threshold=0.8)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].aggregate_news,
        date_range=date_range,
        platforms=platforms,
        similarity_threshold=similarity_threshold,
        limit=limit,
        include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def compare_periods(
    period1: Union[Dict[str, str], str],
    period2: Union[Dict[str, str], str],
    topic: Optional[str] = None,
    compare_type: str = "overview",
    platforms: Optional[List[str]] = None,
    top_n: int = 10
) -> str:
    """
    时期对比分析 - 比较两个时间段的新闻数据

    对比不同时期的热点话题、平台活跃度、新闻数量等维度。

    **使用场景：**
    - 对比本周和上周的热点变化
    - 分析某个话题在两个时期的热度差异
    - 查看各平台活跃度的周期性变化

    Args:
        period1: 第一个时间段（基准期）
            - {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}: 日期范围
            - "today", "yesterday", "this_week", "last_week", "this_month", "last_month": 预设值
        period2: 第二个时间段（对比期，格式同 period1）
        topic: 可选的话题关键词（聚焦特定话题的对比）
        compare_type: 对比类型
            - "overview": 总体概览（默认）- 新闻数量、关键词变化、TOP新闻
            - "topic_shift": 话题变化分析 - 上升话题、下降话题、新出现话题
            - "platform_activity": 平台活跃度对比 - 各平台新闻数量变化
        platforms: 平台过滤列表，如 ['zhihu', 'weibo']
        top_n: 返回 TOP N 结果，默认10

    Returns:
        JSON格式的对比分析结果，包含：
        - periods: 两个时期的日期范围
        - compare_type: 对比类型
        - overview/topic_shift/platform_comparison: 具体对比结果（根据类型）

    Examples:
        - compare_periods(period1="last_week", period2="this_week")  # 周环比
        - compare_periods(period1="last_month", period2="this_month", compare_type="topic_shift")
        - compare_periods(
            period1={"start": "2025-01-01", "end": "2025-01-07"},
            period2={"start": "2025-01-08", "end": "2025-01-14"},
            topic="人工智能"
          )
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['analytics'].compare_periods,
        period1=period1,
        period2=period2,
        topic=topic,
        compare_type=compare_type,
        platforms=platforms,
        top_n=top_n
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 智能检索工具 ====================

@mcp.tool
async def search_news(
    query: str,
    search_mode: str = "keyword",
    date_range: Optional[Union[Dict[str, str], str]] = None,
    platforms: Optional[List[str]] = None,
    limit: int = 50,
    sort_by: str = "relevance",
    threshold: float = 0.6,
    include_url: bool = False,
    include_rss: bool = False,
    rss_limit: int = 20
) -> str:
    """
    统一搜索接口，支持多种搜索模式，可同时搜索热榜和RSS

    建议：使用自然语言日期时，先调用 resolve_date_range 获取精确日期范围。

    Args:
        query: 搜索关键词或内容片段
        search_mode: 搜索模式
            - "keyword": 精确关键词匹配（默认）
            - "fuzzy": 模糊内容匹配
            - "entity": 实体名称搜索（人物/地点/机构）
        date_range: 日期范围，格式 {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}，默认今天
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        limit: 热榜返回条数限制，默认50
        sort_by: 排序方式 - "relevance"（相关度）/ "weight"（权重）/ "date"（日期）
        threshold: 相似度阈值（仅fuzzy模式），0-1，默认0.6
        include_url: 是否包含URL链接，默认False
        include_rss: 是否同时搜索RSS数据，默认False
        rss_limit: RSS返回条数限制，默认20

    Returns:
        JSON格式的搜索结果，包含热榜新闻列表和可选的RSS结果

    Examples:
        - search_news(query="AI")
        - search_news(query="AI", include_rss=True)
        - search_news(query="特斯拉", date_range={"start": "2025-01-01", "end": "2025-01-07"})
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['search'].search_news_unified,
        query=query,
        search_mode=search_mode,
        date_range=date_range,
        platforms=platforms,
        limit=limit,
        sort_by=sort_by,
        threshold=threshold,
        include_url=include_url,
        include_rss=include_rss,
        rss_limit=rss_limit
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 配置与系统管理工具 ====================

@mcp.tool
async def get_current_config(
    section: str = "all"
) -> str:
    """
    获取当前系统配置

    Args:
        section: 配置节，可选值：
            - "all": 所有配置（默认）
            - "crawler": 爬虫配置
            - "push": 推送配置
            - "keywords": 关键词配置
            - "weights": 权重配置

    Returns:
        JSON格式的配置信息
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['config'].get_current_config, section=section)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_system_status() -> str:
    """
    获取系统运行状态和健康检查信息

    返回系统版本、数据统计、缓存状态等信息

    Returns:
        JSON格式的系统状态信息
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['system'].get_system_status)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def check_version(
    proxy_url: Optional[str] = None
) -> str:
    """
    检查版本更新（同时检查 Argus 和 MCP Server）

    比较本地版本与 GitHub 远程版本，判断是否需要更新。

    Args:
        proxy_url: 可选的代理URL，用于访问 GitHub（如 http://127.0.0.1:7890）

    Returns:
        JSON格式的版本检查结果，包含两个组件的版本对比和是否需要更新

    Examples:
        - check_version()
        - check_version(proxy_url="http://127.0.0.1:7890")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['system'].check_version, proxy_url=proxy_url)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def trigger_crawl(
    platforms: Optional[List[str]] = None,
    save_to_local: bool = False,
    include_url: bool = False
) -> str:
    """
    手动触发一次爬取任务（可选持久化）

    Args:
        platforms: 平台ID列表，如 ['zhihu', 'weibo']，不指定则使用所有平台
        save_to_local: 是否保存到本地 output 目录，默认 False
        include_url: 是否包含URL链接，默认False（节省token）

    Returns:
        JSON格式的任务状态信息，包含成功/失败平台列表和新闻数据

    Examples:
        - trigger_crawl(platforms=['zhihu'])
        - trigger_crawl(save_to_local=True)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['system'].trigger_crawl,
        platforms=platforms, save_to_local=save_to_local, include_url=include_url
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 存储同步工具 ====================

@mcp.tool
async def sync_from_remote(
    days: int = 7
) -> str:
    """
    从远程存储拉取数据到本地

    用于 MCP Server 等场景：爬虫存到远程云存储（如 Cloudflare R2），
    MCP Server 拉取到本地进行分析查询。

    Args:
        days: 拉取最近 N 天的数据，默认 7 天
              - 0: 不拉取
              - 7: 拉取最近一周的数据
              - 30: 拉取最近一个月的数据

    Returns:
        JSON格式的同步结果，包含：
        - success: 是否成功
        - synced_files: 成功同步的文件数量
        - synced_dates: 成功同步的日期列表
        - skipped_dates: 跳过的日期（本地已存在）
        - failed_dates: 失败的日期及错误信息
        - message: 操作结果描述

    Examples:
        - sync_from_remote()  # 拉取最近7天
        - sync_from_remote(days=30)  # 拉取最近30天

    Note:
        需要在 config/config.yaml 中配置远程存储（storage.remote）或设置环境变量：
        - S3_ENDPOINT_URL: 服务端点
        - S3_BUCKET_NAME: 存储桶名称
        - S3_ACCESS_KEY_ID: 访问密钥 ID
        - S3_SECRET_ACCESS_KEY: 访问密钥
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['storage'].sync_from_remote, days=days)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_storage_status() -> str:
    """
    获取存储配置和状态

    查看当前存储后端配置、本地和远程存储的状态信息。

    Returns:
        JSON格式的存储状态信息，包含本地/远程存储状态和拉取配置
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['storage'].get_storage_status)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def list_available_dates(
    source: str = "both"
) -> str:
    """
    列出本地/远程可用的日期范围

    查看本地和远程存储中有哪些日期的数据可用。

    Args:
        source: 数据来源
            - "local": 仅本地
            - "remote": 仅远程
            - "both": 同时列出并对比（默认）

    Returns:
        JSON格式的日期列表，包含各来源的日期信息和对比结果

    Examples:
        - list_available_dates()
        - list_available_dates(source="local")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['storage'].list_available_dates, source=source)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 文章内容读取工具 ====================

@mcp.tool
async def read_article(
    url: str,
    timeout: int = 30
) -> str:
    """
    读取指定 URL 的文章内容，返回 LLM 友好的 Markdown 格式

    通过 Jina AI Reader 将网页转换为干净的 Markdown，自动去除广告、导航栏等噪音内容。
    适合用于：阅读新闻正文、获取文章详情、分析文章内容。

    **典型使用流程：**
    1. 先用 search_news(include_url=True) 搜索新闻获取链接
    2. 再用 read_article(url=链接) 读取正文内容
    3. AI 对 Markdown 正文进行分析、摘要、翻译等

    Args:
        url: 文章链接（必需），以 http:// 或 https:// 开头
        timeout: 请求超时时间（秒），默认 30，最大 60

    Returns:
        JSON格式的文章内容，包含完整 Markdown 正文

    Examples:
        - read_article(url="https://example.com/news/123")

    Note:
        - 使用 Jina AI Reader 免费服务（100 RPM 限制）
        - 每次请求间隔 5 秒（内置速率控制）
        - 部分付费墙/登录墙页面可能无法完整获取
    """
    tools = _get_tools()
    timeout = min(max(timeout, 10), 60)
    result = await asyncio.to_thread(
        tools['article'].read_article,
        url=url, timeout=timeout
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def read_articles_batch(
    urls: List[str],
    timeout: int = 30
) -> str:
    """
    批量读取多篇文章内容（最多 5 篇，间隔 5 秒）

    逐篇请求文章内容，每篇之间自动间隔 5 秒以遵守速率限制。

    **典型使用流程：**
    1. 先用 search_news(include_url=True) 搜索新闻获取多个链接
    2. 再用 read_articles_batch(urls=[...]) 批量读取正文
    3. AI 对多篇文章进行对比分析、综合报告

    Args:
        urls: 文章链接列表（必需），最多处理 5 篇
        timeout: 每篇的请求超时时间（秒），默认 30

    Returns:
        JSON格式的批量读取结果，包含每篇的完整内容和状态

    Examples:
        - read_articles_batch(urls=["https://a.com/1", "https://b.com/2"])

    Note:
        - 单次最多读取 5 篇，超出部分会被跳过
        - 5 篇约需 25-30 秒（每篇间隔 5 秒）
        - 单篇失败不影响其他篇的读取
    """
    tools = _get_tools()
    timeout = min(max(timeout, 10), 60)
    result = await asyncio.to_thread(
        tools['article'].read_articles_batch,
        urls=urls, timeout=timeout
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 通知推送工具 ====================


@mcp.tool
async def get_channel_format_guide(channel: Optional[str] = None) -> str:
    """
    获取通知渠道的格式化策略指南

    返回各渠道支持的 Markdown 特性、格式限制和最佳格式化提示词。
    在调用 send_notification 之前使用此工具，可以了解目标渠道的格式要求，
    从而生成最佳排版效果的消息内容。

    各渠道格式差异概览：
    - 飞书：支持 **粗体**、<font color>彩色文本、[链接](url)、--- 分割线
    - 钉钉：支持 ### 标题、**粗体**、> 引用、--- 分割线，不支持颜色
    - 企业微信：仅支持 **粗体**、[链接](url)、> 引用，不支持标题和分割线
    - Telegram：自动转为 HTML，支持粗体/斜体/删除线/代码/链接/引用块
    - ntfy：支持标准 Markdown，不支持颜色
    - Bark：iOS 推送，仅支持粗体和链接，内容需精简
    - Slack：自动转为 mrkdwn，*粗体*、~删除线~、<url|链接>
    - 邮件：自动转为完整 HTML 网页，支持标题/样式/分割线
    - 通用 Webhook：标准 Markdown 或自定义模板

    Args:
        channel: 指定渠道 ID（可选），不指定返回所有渠道策略
                 可选值: feishu, dingtalk, wework, telegram, email, ntfy, bark, slack, generic_webhook

    Returns:
        JSON格式的渠道格式化策略，包含支持特性、限制和格式化提示词

    Examples:
        - get_channel_format_guide()  # 获取所有渠道策略
        - get_channel_format_guide(channel="feishu")  # 获取飞书策略
        - get_channel_format_guide(channel="telegram")  # 获取 Telegram 策略
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['notification'].get_channel_format_guide,
        channel=channel
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_notification_channels() -> str:
    """
    获取所有已配置的通知渠道及其状态

    检测 config.yaml 和 .env 环境变量中的通知渠道配置。
    支持 9 个渠道：飞书、钉钉、企业微信、Telegram、邮件、ntfy、Bark、Slack、通用 Webhook。

    Returns:
        JSON格式的渠道状态，包含每个渠道是否已配置及配置来源

    Examples:
        - get_notification_channels()
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['notification'].get_notification_channels)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def send_notification(
    message: str,
    title: str = "Argus 通知",
    channels: Optional[List[str]] = None,
) -> str:
    """
    向已配置的通知渠道发送消息

    接受 markdown 格式内容，内部自动适配各渠道的格式要求和限制：
    - 飞书：Markdown 卡片消息（支持 **粗体**、<font color>彩色文本、[链接](url)、---）
    - 钉钉：Markdown（自动降级标题为 ###、剥离 <font> 标签和删除线）
    - 企业微信：Markdown（自动剥离 # 标题、---、<font> 标签、删除线）
    - Telegram：HTML（自动转换 **→<b>、*→<i>、~~→<s>、>→<blockquote>）
    - Email：HTML 邮件（完整网页样式，支持 # 标题、---、粗体斜体）
    - ntfy：Markdown（自动剥离 <font> 标签）
    - Bark：Markdown（自动简化为粗体+链接，适配 iOS 推送）
    - Slack：mrkdwn（自动转换 **→*、~~→~、[text](url)→<url|text>）
    - 通用 Webhook：Markdown（支持自定义模板）

    提示：发送前可调用 get_channel_format_guide 获取目标渠道的详细格式化策略，
    以生成最佳排版效果的消息内容。

    Args:
        message: markdown 格式的消息内容（必需）
        title: 消息标题，默认 "Argus 通知"
        channels: 指定发送的渠道列表，不指定则发送到所有已配置渠道
                  可选值: feishu, dingtalk, wework, telegram, email, ntfy, bark, slack, generic_webhook

    Returns:
        JSON格式的发送结果，包含每个渠道的发送状态

    Examples:
        - send_notification(message="**测试消息**\\n这是一条测试通知")
        - send_notification(message="紧急通知", title="系统告警", channels=["feishu", "dingtalk"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['notification'].send_notification,
        message=message, title=title, channels=channels
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 外部数据源 (学术/社区/代码) ====================

@mcp.tool
async def search_arxiv(
    query: str,
    category: Optional[str] = None,
    max_results: int = 20,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
) -> str:
    """
    搜索 arXiv 论文 (官方 API, 免费无 key)

    Args:
        query: 搜索关键词,如 "large language model", "diffusion model"
        category: 限定 arXiv 分类, 例如 cs.AI / cs.LG / cs.CL / cs.CV / cs.RO / stat.ML / q-fin.* / econ.*
        max_results: 返回条数, 默认 20, 最大 100
        sort_by: 排序字段, submittedDate / lastUpdatedDate / relevance
        sort_order: ascending / descending

    Returns:
        JSON: 论文列表(标题/作者/摘要/发布时间/分类/PDF 链接)

    Examples:
        - search_arxiv(query="LLM agent", category="cs.AI", max_results=30)
        - search_arxiv(query="reinforcement learning", sort_by="relevance")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_arxiv,
        query=query, category=category, max_results=max_results,
        sort_by=sort_by, sort_order=sort_order,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_semantic_scholar(
    query: str,
    limit: int = 20,
    year: Optional[str] = None,
    fields_of_study: Optional[List[str]] = None,
    min_citation_count: Optional[int] = None,
) -> str:
    """
    搜索 Semantic Scholar 论文 (含引用数 + AI TLDR 摘要)

    Args:
        query: 搜索关键词
        limit: 返回数量, 默认 20, 最大 100
        year: 年份过滤, 单年 "2024" 或范围 "2020-2024"
        fields_of_study: 学科领域列表, 如 ["Computer Science", "Medicine"]
        min_citation_count: 最少引用数

    Returns:
        JSON: 论文(含 TLDR 一句话总结 / 引用数 / 影响力引用 / 开放获取 PDF)

    Note:
        匿名 API 限流 1 RPS,失败时返回 RATE_LIMITED 可以稍后重试。
        如需高频调用,前往 semanticscholar.org/product/api 申请免费 key。
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_semantic_scholar,
        query=query, limit=limit, year=year,
        fields_of_study=fields_of_study, min_citation_count=min_citation_count,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_openalex(
    query: str,
    per_page: int = 25,
    from_publication_date: Optional[str] = None,
    sort: str = "relevance_score:desc",
) -> str:
    """
    搜索 OpenAlex (2.4 亿论文 + 机构 + 引用图谱, 完全免费)

    Args:
        query: 搜索关键词
        per_page: 每页条数, 默认 25, 最大 100
        from_publication_date: 起始发表日期, "YYYY-MM-DD"
        sort: 排序, relevance_score:desc / cited_by_count:desc / publication_date:desc

    Returns:
        JSON: works 列表(含 DOI / 引用数 / 概念分类 / 作者 / 开放获取链接)

    Examples:
        - search_openalex(query="quantum computing", sort="cited_by_count:desc")
        - search_openalex(query="diabetes", from_publication_date="2024-01-01")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_openalex,
        query=query, per_page=per_page,
        from_publication_date=from_publication_date, sort=sort,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_pubmed(query: str, max_results: int = 20) -> str:
    """
    搜索 PubMed (NIH 医学/生物论文库, 免费 E-utilities)

    Args:
        query: 搜索关键词, 支持 PubMed 检索语法
            如 "(cancer[Title]) AND (immunotherapy)"
        max_results: 返回条数, 默认 20, 最大 100

    Returns:
        JSON: 论文列表(PMID / 标题 / 作者 / 期刊 / DOI / PubMed 链接)

    Examples:
        - search_pubmed(query="CRISPR cancer therapy")
        - search_pubmed(query="long COVID symptoms 2024")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_pubmed, query=query, max_results=max_results,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_hackernews_top(story_type: str = "top", limit: int = 30) -> str:
    """
    获取 Hacker News 热门帖子 (官方 API, 含分数和评论数)

    比 RSS 更强: 返回完整的 score、descendants(评论数)、作者、链接。

    Args:
        story_type: 类型, top / new / best / ask / show / job
        limit: 返回数量, 默认 30, 最大 100

    Returns:
        JSON: stories 列表(含 score / comments 数 / 外链 / HN 讨论页)

    Examples:
        - get_hackernews_top(story_type="best", limit=50)
        - get_hackernews_top(story_type="show")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_hackernews_top,
        story_type=story_type, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_reddit(
    subreddit: str,
    sort: str = "hot",
    time_filter: str = "day",
    limit: int = 25,
) -> str:
    """
    抓取指定 subreddit 帖子 (官方公开 JSON, 无需 OAuth)

    Args:
        subreddit: subreddit 名称(不带 r/), 例如 "MachineLearning", "LocalLLaMA"
        sort: 排序, hot / new / top / rising / controversial
        time_filter: 时间窗(仅 top/controversial), hour / day / week / month / year / all
        limit: 返回条数, 默认 25, 最大 100

    Returns:
        JSON: posts 列表(含 score / 评论数 / 自帖正文 / flair 标签)

    Examples:
        - search_reddit(subreddit="LocalLLaMA", sort="top", time_filter="week")
        - search_reddit(subreddit="programming", sort="rising", limit=50)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_reddit,
        subreddit=subreddit, sort=sort, time_filter=time_filter, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_github_trending(
    language: Optional[str] = None,
    since: str = "daily",
    limit: int = 25,
) -> str:
    """
    获取 GitHub 'Trending' 热门仓库 (按时间窗内 stars 排序, 模拟 trending 算法)

    Args:
        language: 编程语言过滤, 如 "python", "rust", "typescript"
        since: 时间窗, daily / weekly / monthly
        limit: 返回数量, 默认 25, 最大 100

    Returns:
        JSON: repositories 列表(含 stars / 描述 / topics 标签 / 语言)

    Note: 匿名调用 60 RPH 限流,可设 GITHUB_TOKEN 环境变量提升至 5000 RPH。

    Examples:
        - get_github_trending(language="python", since="weekly")
        - get_github_trending(since="daily", limit=50)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_github_trending,
        language=language, since=since, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_github_releases(repo: str, limit: int = 10) -> str:
    """
    获取 GitHub 仓库最新发布版本 (适合追踪关键开源项目)

    Args:
        repo: 仓库全名 "owner/repo", 如 "anthropics/anthropic-sdk-python"
        limit: 返回条数, 默认 10, 最大 30

    Returns:
        JSON: releases 列表(含 tag / 发布时间 / changelog / 是否 prerelease)

    Examples:
        - get_github_releases(repo="ollama/ollama")
        - get_github_releases(repo="huggingface/transformers", limit=5)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_github_releases, repo=repo, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_all_academic(query: str, per_source: int = 10) -> str:
    """
    跨学术源统一搜索 - 一次查询同时命中四个论文库

    并行调用: arXiv + Semantic Scholar + OpenAlex + PubMed
    结果按源分组返回, 单源失败不影响其他源。

    Args:
        query: 搜索关键词
        per_source: 每个源返回的条数, 默认 10

    Returns:
        JSON: { sources: { arxiv: {...}, semantic_scholar: {...}, openalex: {...}, pubmed: {...} } }

    Examples:
        - search_all_academic(query="GPT-4 reasoning")
        - search_all_academic(query="mRNA vaccine", per_source=15)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_all_academic, query=query, per_source=per_source,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 第二批外部源 (元数据/社区/市场/政府) ====================

@mcp.tool
async def search_crossref(
    query: str,
    rows: int = 20,
    from_pub_date: Optional[str] = None,
    sort: str = "relevance",
) -> str:
    """
    CrossRef DOI 元数据搜索 (1.5 亿条目, 全球出版商权威库, 免费无 key)

    Args:
        query: 搜索关键词
        rows: 返回条数, 默认 20, 最大 100
        from_pub_date: 起始发表日期 "YYYY-MM-DD"
        sort: relevance / published / is-referenced-by-count

    Returns:
        JSON: works 列表 (DOI / 出版商 / 引用计数 / 期刊名)

    Examples:
        - search_crossref(query="quantum supremacy", sort="is-referenced-by-count")
        - search_crossref(query="climate change", from_pub_date="2024-01-01")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_crossref,
        query=query, rows=rows, from_pub_date=from_pub_date, sort=sort,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_openreview(
    query: str,
    venue: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    OpenReview 论文搜索 (NeurIPS/ICLR/ICML 等顶会的投稿与评审)

    可以提前看到尚未正式发表的会议投稿,适合追踪 AI/ML 研究热点。

    Args:
        query: 搜索关键词
        venue: 限定会议, 如 "ICLR.cc/2025/Conference"、"NeurIPS.cc/2024"
        limit: 返回条数, 默认 20, 最大 100

    Returns:
        JSON: papers 列表 (含 PDF 直链、forum 讨论页、TL;DR)

    Examples:
        - search_openreview(query="instruction tuning")
        - search_openreview(query="diffusion", venue="ICLR.cc/2025/Conference")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_openreview,
        query=query, venue=venue, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_wikipedia_trending(
    project: str = "en.wikipedia",
    date: Optional[str] = None,
    limit: int = 25,
) -> str:
    """
    Wikipedia 热门文章 (按浏览量, 趋势检测利器)

    可用于发现"全球网民正在搜什么"——比新闻热榜更直接反映关注度。

    Args:
        project: Wikipedia 语种, en.wikipedia / zh.wikipedia / ja.wikipedia
        date: 指定日期 "YYYY-MM-DD", 默认自动找最近可用日期 (通常 1-3 天前)
        limit: 返回条数, 默认 25, 最大 100

    Returns:
        JSON: articles 列表 (标题 / 浏览量 / 排名 / Wiki 链接)

    Examples:
        - get_wikipedia_trending()
        - get_wikipedia_trending(project="zh.wikipedia", limit=50)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_wikipedia_trending,
        project=project, date=date, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_mastodon(
    hashtag: Optional[str] = None,
    instance: str = "mastodon.social",
    limit: int = 20,
) -> str:
    """
    Mastodon 联邦社交网络搜索 (hashtag 模式无需登录)

    Args:
        hashtag: 话题标签, 如 "ai" 或 "#opensource" (推荐使用)
        instance: Mastodon 实例域名,默认 mastodon.social
                  其他选项: infosec.exchange, fosstodon.org, hachyderm.io
        limit: 返回条数, 默认 20, 最大 40

    Returns:
        JSON: posts 列表 (含正文、互动数、作者、tags)

    Examples:
        - search_mastodon(hashtag="ai")
        - search_mastodon(hashtag="security", instance="infosec.exchange")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_mastodon,
        hashtag=hashtag, instance=instance, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_stackexchange(
    query: str,
    site: str = "stackoverflow",
    sort: str = "votes",
    order: str = "desc",
    page_size: int = 20,
    tagged: Optional[List[str]] = None,
) -> str:
    """
    Stack Exchange 问答搜索 (StackOverflow / SuperUser / AskUbuntu / ServerFault 等)

    Args:
        query: 标题关键词
        site: 站点, stackoverflow / superuser / askubuntu / serverfault / unix /
              math / stats / softwareengineering / dba / security / tex
        sort: votes / activity / creation / relevance
        order: desc / asc
        page_size: 返回条数,默认 20,最大 100
        tagged: 标签过滤列表,如 ["python", "asyncio"]

    Returns:
        JSON: questions 列表 (含分数 / 回答数 / 浏览量 / 标签)

    Examples:
        - search_stackexchange(query="async await", tagged=["python"])
        - search_stackexchange(query="kubernetes networking", site="serverfault")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_stackexchange,
        query=query, site=site, sort=sort, order=order,
        page_size=page_size, tagged=tagged,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_crypto_trending(limit: int = 15) -> str:
    """
    CoinGecko 热门加密货币 (按搜索量, 7 天榜)

    Returns:
        JSON: { coins: [...], nfts: [...], categories: [...] }

    Examples:
        - get_crypto_trending()
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_crypto_trending, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_sec_edgar(
    query: Optional[str] = None,
    cik: Optional[str] = None,
    forms: Optional[List[str]] = None,
    limit: int = 20,
) -> str:
    """
    SEC EDGAR 美股上市公司公开文件搜索 (10-K/10-Q/8-K/13F 等)

    适合: 追踪上市公司动态、机构持仓变化、IPO 招股书、年报关键词扫描。

    Args:
        query: 全文搜索关键词
        cik: 特定公司 CIK 编号 (从 SEC 网站查询)
        forms: 文件类型过滤, 如 ["10-K", "8-K", "13F-HR"]
        limit: 返回条数, 默认 20, 最大 100

    Returns:
        JSON: filings 列表 (公司 / 表单类型 / 申报时间 / 链接)

    Examples:
        - search_sec_edgar(query="generative AI risks", forms=["10-K"])
        - search_sec_edgar(query="Nvidia GPU shortage")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_sec_edgar,
        query=query, cik=cik, forms=forms, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_youtube_channel(channel_id: str, limit: int = 15) -> str:
    """
    订阅 YouTube 频道最新视频 (官方 RSS, 免费无需 key)

    Args:
        channel_id: 频道 ID (UC 开头的 24 字符), 不是用户名
                    可在频道页面源代码搜 "channelId" 获取
                    示例: UC_x5XG1OV2P6uZZ5FSM9Ttw (Google Developers)
        limit: 返回条数, 默认 15, 最大 30

    Returns:
        JSON: videos 列表 (标题 / 链接 / 视频 ID / 发布时间)

    Examples:
        - get_youtube_channel(channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_youtube_channel,
        channel_id=channel_id, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_huggingface(
    kind: str = "models",
    query: Optional[str] = None,
    sort: str = "downloads",
    direction: str = "-1",
    limit: int = 25,
    filter_tag: Optional[str] = None,
) -> str:
    """
    Hugging Face Hub - 模型/数据集/Spaces 趋势 (无需 key)

    AI 生态最重要的趋势源,可以发现:
    - 当下最热的开源模型 (按下载/点赞排序)
    - 新发布的数据集
    - 流行的 Spaces 应用

    Args:
        kind: models / datasets / spaces
        query: 搜索关键词 (可选)
        sort: downloads / likes / lastModified / createdAt
        direction: -1=desc / 1=asc
        limit: 返回条数, 默认 25, 最大 100
        filter_tag: 标签过滤, 如 "text-generation"、"chinese"

    Returns:
        JSON: 模型/数据集列表 (含下载数 / 标签 / 库类型 / 更新时间)

    Examples:
        - search_huggingface(kind="models", filter_tag="text-generation")
        - search_huggingface(kind="datasets", sort="lastModified")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_huggingface,
        kind=kind, query=query, sort=sort, direction=direction,
        limit=limit, filter_tag=filter_tag,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_dblp(query: str, kind: str = "publ", limit: int = 30) -> str:
    """
    DBLP 计算机科学文献库 (顶会顶刊全收录, 含作者档案)

    Args:
        query: 关键词
        kind: publ (论文) / author (作者) / venue (会议/期刊)
        limit: 返回条数, 默认 30, 最大 1000

    Returns:
        JSON: 论文/作者/会议列表

    Examples:
        - search_dblp(query="vision transformer", kind="publ")
        - search_dblp(query="Yann LeCun", kind="author")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_dblp, query=query, kind=kind, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_inspire_hep(query: str, sort: str = "mostrecent", size: int = 25) -> str:
    """
    inspire-HEP 高能物理论文库 (CERN/SLAC 维护, 物理学权威库)

    Args:
        query: 搜索关键词
        sort: mostrecent / mostcited
        size: 返回条数, 默认 25, 最大 100

    Returns:
        JSON: papers 列表 (含 arXiv ID / 引用数 / 期刊)

    Examples:
        - search_inspire_hep(query="dark matter", sort="mostcited")
        - search_inspire_hep(query="LHC collision")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_inspire_hep, query=query, sort=sort, size=size,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_gdelt(
    query: str,
    timespan: str = "1d",
    max_records: int = 25,
    mode: str = "ArtList",
    sort: str = "DateDesc",
) -> str:
    """
    GDELT 全球新闻事件库 - 跨语言全球媒体监测 (1.5 亿+ 事件, 免费)

    覆盖 100+ 国家、65+ 语言的新闻报道,适合追踪全球事件、跨国比较、
    舆情倾向分析 (含每篇文章的情感打分 tone -10~+10)。

    Args:
        query: 搜索关键词 (支持引号短语、AND/OR、country:US 等)
        timespan: 时间窗 - 1h / 24h / 1d / 7d / 1m / 3m / 1y
        max_records: 返回条数, 默认 25, 最大 250
        mode: ArtList(文章列表) / TimelineVol(报道量趋势) /
              TimelineTone(情感趋势) / WordCloudEnglish(词云)
        sort: DateDesc / DateAsc / ToneDesc / ToneAsc / HybridRel

    Returns:
        JSON: articles 列表 (含语种 / 国别 / tone 情感分)

    Examples:
        - search_gdelt(query='"climate change" sourcecountry:CN', timespan='7d')
        - search_gdelt(query='Nvidia AI', mode='TimelineVol')
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_gdelt,
        query=query, timespan=timespan, max_records=max_records,
        mode=mode, sort=sort,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_crypto_markets(
    vs_currency: str = "usd",
    per_page: int = 25,
    order: str = "market_cap_desc",
) -> str:
    """
    CoinGecko 市场行情 - Top 币种价格/市值/24h 涨跌

    Args:
        vs_currency: 计价货币, usd / cny / eur / btc
        per_page: 返回数量, 默认 25, 最大 250
        order: market_cap_desc / volume_desc / id_asc

    Returns:
        JSON: coins 列表 (含价格 / 市值 / 24h-7d-30d 涨跌幅 / 历史最高)

    Examples:
        - get_crypto_markets()
        - get_crypto_markets(vs_currency="cny", per_page=50)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_crypto_markets,
        vs_currency=vs_currency, per_page=per_page, order=order,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_hackernews(
    query: str,
    tags: Optional[str] = None,
    sort: str = "search",
    hits: int = 30,
) -> str:
    """
    Hacker News 全文历史搜索 (官方 Algolia 引擎)

    与 get_hackernews_top 不同 - 这个能搜历史所有 story 和 comment。

    Args:
        query: 搜索关键词
        tags: 类型过滤, story / comment / poll / show_hn / ask_hn / front_page
        sort: search (按相关度) / search_by_date (按时间)
        hits: 返回数量, 默认 30, 最大 100

    Returns:
        JSON: hits 列表 (含 points / 评论数 / 评论文本)

    Examples:
        - search_hackernews(query="rust async runtime")
        - search_hackernews(query="OpenAI", tags="show_hn", sort="search_by_date")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_hackernews,
        query=query, tags=tags, sort=sort, hits=hits,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_wikipedia(query: str, language: str = "en", limit: int = 10) -> str:
    """
    Wikipedia 文章搜索 (含 snippet 摘要)

    Args:
        query: 搜索关键词
        language: 语种代码, en / zh / ja / fr / de
        limit: 返回数量, 默认 10, 最大 50

    Returns:
        JSON: articles 列表 (含 snippet / 字数 / 链接)

    Examples:
        - search_wikipedia(query="quantum computing")
        - search_wikipedia(query="人工智能", language="zh")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_wikipedia,
        query=query, language=language, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_github_code(query: str, limit: int = 20) -> str:
    """
    GitHub 代码搜索 (跨所有公开仓库)

    Note: GitHub 已禁用匿名代码搜索, 需要设置 GITHUB_TOKEN 环境变量。
          Token 创建: https://github.com/settings/tokens (无需任何 scope)

    Args:
        query: 搜索表达式, 支持 GitHub 代码搜索语法
               例: "asyncio.gather language:python"
                   "openai_api_key in:file"
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: results 列表 (含文件名 / 路径 / 仓库 / 语言)

    Examples:
        - search_github_code(query="from anthropic import language:python")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_github_code, query=query, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_cve(
    keyword: Optional[str] = None,
    cve_id: Optional[str] = None,
    days: int = 7,
    results_per_page: int = 25,
) -> str:
    """
    NVD CVE 漏洞库 (美国 NIST 维护, 安全情报必备, 免费)

    Args:
        keyword: 关键词搜索 (如 "openssl"、"chrome"、"log4j")
        cve_id: 直接查 CVE 编号 (如 "CVE-2021-44228")
        days: 关键词模式的回溯天数, 默认 7, 最大 120
        results_per_page: 返回数量, 默认 25, 最大 100

    Returns:
        JSON: cves 列表 (含 CVSS 分数 / 严重程度 / 描述 / 参考链接)

    Examples:
        - search_cve(keyword="openssl", days=30)
        - search_cve(cve_id="CVE-2021-44228")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_cve,
        keyword=keyword, cve_id=cve_id, days=days,
        results_per_page=results_per_page,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_earthquakes(
    period: str = "day",
    min_magnitude: str = "significant",
    limit: int = 50,
) -> str:
    """
    USGS 全球实时地震数据 (官方权威, 完全免费)

    Args:
        period: 时间窗 - hour / day / week / month
        min_magnitude: 震级阈值 - significant / 4.5 / 2.5 / 1.0 / all
        limit: 返回条数, 默认 50, 最大 200

    Returns:
        JSON: earthquakes 列表 (含震级 / 位置 / 时间 / 海啸预警 / 经纬度)

    Examples:
        - get_earthquakes(period="day", min_magnitude="significant")
        - get_earthquakes(period="week", min_magnitude="4.5", limit=100)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_earthquakes,
        period=period, min_magnitude=min_magnitude, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_nasa_data(
    kind: str = "apod",
    date: Optional[str] = None,
    days: int = 1,
) -> str:
    """
    NASA 公开数据接口 (天文图 / 近地小行星)

    Args:
        kind:
            - apod: NASA 每日天文图 (Astronomy Picture of the Day)
            - neo: 近地小行星 (Near Earth Objects)
        date: YYYY-MM-DD, 不指定则用今天
        days: neo 模式查询天数, 默认 1, 最大 7

    Returns:
        JSON: 天文图(标题/图片/解说) 或 小行星(尺寸/距离/速度/危险等级)

    Examples:
        - get_nasa_data(kind="apod")
        - get_nasa_data(kind="neo", days=3)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_nasa_data, kind=kind, date=date, days=days,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_weather(
    latitude: float,
    longitude: float,
    days: int = 3,
    timezone_str: str = "auto",
) -> str:
    """
    全球天气预报 + 当前观测 (Open-Meteo, 完全免费无 key)

    Args:
        latitude: 纬度 (例: 北京 39.9, 上海 31.2, 纽约 40.7)
        longitude: 经度 (例: 北京 116.4, 上海 121.5, 纽约 -74.0)
        days: 预报天数, 默认 3, 最大 16
        timezone_str: 时区, 默认 auto (按经纬度推断)

    Returns:
        JSON: { current: {...}, daily: [{...}] }

    Examples:
        - get_weather(latitude=39.9, longitude=116.4)  # 北京
        - get_weather(latitude=40.7, longitude=-74.0, days=7)  # 纽约一周
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_weather,
        latitude=latitude, longitude=longitude, days=days, timezone_str=timezone_str,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def query_wikidata(
    sparql: Optional[str] = None,
    search: Optional[str] = None,
    language: str = "en",
    limit: int = 20,
) -> str:
    """
    Wikidata 知识图谱查询 (10 亿+ 三元组结构化知识)

    两种模式:
        1. 简单实体搜索 (search 参数): 关键词 → 实体列表
        2. SPARQL 查询 (sparql 参数): 复杂结构化查询

    Args:
        sparql: 完整 SPARQL 查询语句 (高级)
        search: 简单关键词 (推荐入门)
        language: 标签语种, en/zh/ja
        limit: 返回数量, 默认 20

    Returns:
        JSON: entities 或 rows

    Examples:
        - query_wikidata(search="量子计算", language="zh")
        - query_wikidata(sparql="SELECT ?country ?countryLabel WHERE { ?country wdt:P31 wd:Q6256. SERVICE wikibase:label {bd:serviceParam wikibase:language 'en'.} } LIMIT 10")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].query_wikidata,
        sparql=sparql, search=search, language=language, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_bluesky(query: str, limit: int = 25, sort: str = "latest") -> str:
    """
    Bluesky AT Protocol 帖子搜索 (新兴去中心化社交, 公开端点无需登录)

    Args:
        query: 搜索关键词或 hashtag
        limit: 返回数量, 默认 25, 最大 100
        sort: latest (最新) / top (热度)

    Returns:
        JSON: posts 列表 (含点赞/转推/回复数 + 帖子链接)

    Examples:
        - search_bluesky(query="AI safety")
        - search_bluesky(query="#opensource", sort="top")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_bluesky, query=query, limit=limit, sort=sort,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_wayback(url: str, timestamp: Optional[str] = None) -> str:
    """
    Internet Archive Wayback Machine - 查询任意 URL 的历史快照

    适合: 看消失的网页、对比同一页面历史版本、检测内容是否被修改/删除。

    Args:
        url: 目标 URL
        timestamp: 优先靠近时间, YYYYMMDD 或 YYYYMMDDhhmmss

    Returns:
        JSON: 最接近的快照 URL 与时间

    Examples:
        - get_wayback(url="https://anthropic.com")
        - get_wayback(url="https://twitter.com", timestamp="20120101")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_wayback, url=url, timestamp=timestamp,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_worldbank_indicator(
    country: str,
    indicator: str = "NY.GDP.MKTP.CD",
    years: int = 10,
) -> str:
    """
    World Bank 国家指标查询 (200+ 国家, GDP/人口/通胀等, 完全免费)

    Args:
        country: ISO2 国家代码 (CN/US/JP/GB) 或 'all' (全球)
        indicator: 指标代码,常用:
            - NY.GDP.MKTP.CD: GDP (美元)
            - NY.GDP.PCAP.CD: 人均 GDP
            - SP.POP.TOTL: 总人口
            - SL.UEM.TOTL.ZS: 失业率
            - FP.CPI.TOTL.ZG: 通胀率
            - EN.ATM.CO2E.PC: 人均 CO2 排放
            完整: https://data.worldbank.org/indicator
        years: 回溯年数, 默认 10

    Returns:
        JSON: 时序数据 [{year, value, country, ...}]

    Examples:
        - get_worldbank_indicator(country="CN", indicator="NY.GDP.MKTP.CD")
        - get_worldbank_indicator(country="JP", indicator="SP.POP.TOTL", years=20)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_worldbank_indicator,
        country=country, indicator=indicator, years=years,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_pypi_stats(package: str, period: str = "recent") -> str:
    """
    PyPI 包下载量趋势 (pypistats.org BigQuery 镜像)

    Args:
        package: 包名
        period: recent (近 1 天/1 周/1 月) / overall (历史总量)

    Returns:
        JSON: 下载量数据

    Examples:
        - get_pypi_stats(package="anthropic")
        - get_pypi_stats(package="langchain", period="overall")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_pypi_stats, package=package, period=period,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_lobsters(kind: str = "hottest", page: int = 1) -> str:
    """
    Lobsters 技术社区 (高质量小众, 比 HN 更专业, 公开 JSON)

    Args:
        kind: hottest (热门) / newest (最新) / active (活跃)
        page: 页码

    Returns:
        JSON: stories 列表 (含 score / 评论数 / 标签 / 提交者)

    Examples:
        - get_lobsters(kind="hottest")
        - get_lobsters(kind="active", page=2)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_lobsters, kind=kind, page=page,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_ghsa(
    query: Optional[str] = None,
    ecosystem: Optional[str] = None,
    severity: Optional[str] = None,
    per_page: int = 25,
) -> str:
    """
    GitHub Advisory Database - 开源生态安全公告 (聚焦 OSS 依赖漏洞)

    与 NVD CVE 互补: GHSA 聚焦开源依赖包的漏洞, 并指明可用的补丁版本。

    Args:
        query: 关键词 (支持直接 CVE 编号, 如 "CVE-2021-44228")
        ecosystem: composer/go/maven/npm/nuget/pip/pub/rubygems/rust/actions
        severity: low / medium / high / critical
        per_page: 返回条数, 默认 25, 最大 100

    Returns:
        JSON: advisories 列表 (含 GHSA/CVE ID、CVSS、受影响包列表、补丁版本)

    Examples:
        - search_ghsa(ecosystem="npm", severity="critical")
        - search_ghsa(query="CVE-2021-44228")  # Log4shell
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_ghsa,
        query=query, ecosystem=ecosystem, severity=severity, per_page=per_page,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_books(query: str, limit: int = 20) -> str:
    """
    Open Library 图书搜索 (4000 万+ 书目, Internet Archive 维护)

    Args:
        query: 书名 / 作者 / 主题
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: books 列表 (含标题、作者、首发年份、主题标签、ISBN)

    Examples:
        - search_books("three body problem")
        - search_books("deep learning Goodfellow")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_books, query=query, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_crates(
    query: Optional[str] = None,
    sort: str = "downloads",
    per_page: int = 25,
) -> str:
    """
    Crates.io Rust 包仓库搜索 / 热门榜

    Args:
        query: 包名或关键词 (不填则返回全站按 sort 排序的榜单)
        sort: downloads / recent-downloads / recent-updates / new / alpha
        per_page: 返回数量, 默认 25, 最大 100

    Returns:
        JSON: crates 列表 (含版本、下载量、近期下载、关键词)

    Examples:
        - search_crates(sort="new")  # 新发布的 Rust 包
        - search_crates(query="tokio async runtime")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_crates,
        query=query, sort=sort, per_page=per_page,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_docker_hub(
    query: str,
    limit: int = 25,
    is_official: Optional[bool] = None,
) -> str:
    """
    Docker Hub 镜像搜索

    Args:
        query: 镜像名或关键词
        limit: 返回条数, 默认 25, 最大 100
        is_official: True=只看官方, False=只看非官方

    Returns:
        JSON: images 列表 (含 stars / pulls / 官方标识)

    Examples:
        - search_docker_hub("postgres", is_official=True)
        - search_docker_hub("llama ollama")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_docker_hub,
        query=query, limit=limit, is_official=is_official,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_reliefweb(
    query: Optional[str] = None,
    kind: str = "reports",
    limit: int = 25,
    appname: str = "argus",
) -> str:
    """
    ReliefWeb - UN OCHA 人道主义与灾难事件库

    Note: 2025 年起 ReliefWeb v2 API 要求已登记的 appname,
          免费注册: https://apidoc.reliefweb.int/

    Args:
        query: 搜索关键词
        kind: reports (报告) / disasters (灾情) / jobs (招聘) / training (培训) / countries (国家档案)
        limit: 返回条数, 默认 25, 最大 100
        appname: 你在 ReliefWeb 注册的 appname (注册后替换默认值)

    Returns:
        JSON: 报告/灾情列表 (含国家、发布日期、类型标签)

    Examples:
        - search_reliefweb(query="Ukraine", appname="your-approved-appname")
        - search_reliefweb(kind="disasters", appname="your-approved-appname")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_reliefweb,
        query=query, kind=kind, limit=limit, appname=appname,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_exchange_rates(
    base: str = "USD",
    symbols: Optional[List[str]] = None,
    date: Optional[str] = None,
) -> str:
    """
    汇率查询 (Frankfurter / 欧洲央行官方数据, 完全免费无 key, 含历史)

    Args:
        base: 基础货币代码, 默认 USD (可用 CNY/EUR/JPY/GBP 等)
        symbols: 目标货币列表, 如 ["CNY", "JPY", "EUR"]; 不填则返回全部
        date: YYYY-MM-DD, 不填则返回最新 (支持 1999-01-01 以来历史)

    Returns:
        JSON: { base, date, rates: {...} }

    Examples:
        - get_exchange_rates(base="USD", symbols=["CNY", "JPY"])
        - get_exchange_rates(base="CNY", date="2020-01-01")  # 历史
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_exchange_rates,
        base=base, symbols=symbols, date=date,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_jsr(query: str, limit: int = 20) -> str:
    """
    JSR JavaScript 包仓库搜索 (Deno 团队运营, 新一代 TS/JS 仓库)

    Args:
        query: 包名或关键词
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: packages 列表 (含最新版本、运行时兼容性、GitHub 仓库)

    Examples:
        - search_jsr("hono")
        - search_jsr("oak deno framework")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_jsr, query=query, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_lemmy(
    query: str,
    instance: str = "lemmy.world",
    type_: str = "All",
    sort: str = "TopDay",
    limit: int = 25,
) -> str:
    """
    Lemmy 联邦社区搜索 (开源 Reddit 替代, 免费)

    Args:
        query: 搜索关键词
        instance: Lemmy 实例域名, 默认 lemmy.world
                  其他: lemmy.ml, beehaw.org, programming.dev
        type_: All / Posts / Comments / Communities / Users
        sort: Active / Hot / New / TopDay / TopWeek / TopMonth / TopYear / TopAll
        limit: 返回数量, 默认 25, 最大 50

    Returns:
        JSON: posts 列表 (含 score / 评论数 / 社区 / 链接)

    Examples:
        - search_lemmy(query="linux", sort="TopWeek")
        - search_lemmy(query="self-hosted", instance="programming.dev")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_lemmy,
        query=query, instance=instance, type_=type_, sort=sort, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_crypto_details(coin_id: str = "btc-bitcoin") -> str:
    """
    CoinPaprika 加密货币详情 (免费替代 CoinGecko, 含完整历史统计)

    Args:
        coin_id: 格式 'symbol-fullname', 如:
            btc-bitcoin / eth-ethereum / sol-solana /
            bnb-binance-coin / doge-dogecoin / ada-cardano

    Returns:
        JSON: 完整信息 (含描述、市场数据、1h/24h/7d/30d/1y 涨跌幅、历史最高)

    Examples:
        - get_crypto_details(coin_id="btc-bitcoin")
        - get_crypto_details(coin_id="eth-ethereum")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_crypto_details, coin_id=coin_id,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_gitlab(
    query: str,
    scope: str = "projects",
    order_by: str = "last_activity_at",
    per_page: int = 25,
) -> str:
    """
    GitLab.com 公开项目搜索 (GitHub 的开源 Git 替代)

    Args:
        query: 关键词
        scope: projects / issues / merge_requests / users / groups / snippet_titles
        order_by: id / name / path / created_at / updated_at / last_activity_at / similarity
        per_page: 返回数量, 默认 25, 最大 100

    Returns:
        JSON: projects 列表 (含 stars / forks / 活动时间 / 话题标签)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_gitlab,
        query=query, scope=scope, order_by=order_by, per_page=per_page,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_homebrew(
    query: str,
    kind: str = "formula",
    limit: int = 20,
) -> str:
    """
    Homebrew 包搜索 (macOS/Linux, formula=命令行工具, cask=GUI 应用)

    Args:
        query: 关键词
        kind: formula (命令行包) / cask (macOS 桌面应用)
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: 包列表 (含版本 / 依赖 / 描述 / 主页)

    Examples:
        - search_homebrew("postgres", kind="formula")
        - search_homebrew("notion", kind="cask")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_homebrew,
        query=query, kind=kind, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_flathub(query: str, limit: int = 20) -> str:
    """
    Flathub Linux 应用商店搜索 (Flatpak 包)

    Args:
        query: 关键词
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: apps 列表 (含月安装量、类别、开发者)

    Examples:
        - search_flathub("obs")  # OBS Studio
        - search_flathub("steam")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_flathub, query=query, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_vscode_extensions(
    query: str,
    limit: int = 20,
    sort_by: int = 4,
) -> str:
    """
    VSCode Marketplace 扩展搜索

    Args:
        query: 搜索关键词
        limit: 返回数量, 默认 20, 最大 100
        sort_by:
            0=Relevance, 1=LastUpdated, 4=InstallCount (默认), 5=Rating,
            6=TrendingDaily, 7=TrendingWeekly, 8=TrendingMonthly,
            10=PublishedDate, 12=WeightedRating

    Returns:
        JSON: extensions 列表 (含安装数、评分、更新时间)

    Examples:
        - search_vscode_extensions("copilot", sort_by=4)
        - search_vscode_extensions("rust", sort_by=6)  # 本日趋势
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_vscode_extensions,
        query=query, limit=limit, sort_by=sort_by,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_weather_history(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    daily_vars: Optional[List[str]] = None,
) -> str:
    """
    Open-Meteo Archive - 1940 至今全球历史天气 (完全免费)

    适合: 气候对比、历史天气回溯、灾害复盘。

    Args:
        latitude / longitude: 地理坐标
        start_date / end_date: 日期区间 YYYY-MM-DD
        daily_vars: 每日变量列表,默认 [max_temp, min_temp, precipitation, wind]
                    可选: temperature_2m_mean, et0_fao_evapotranspiration,
                         relative_humidity_2m_max, surface_pressure_mean,
                         cloud_cover_mean, shortwave_radiation_sum 等

    Returns:
        JSON: 历史时间序列

    Examples:
        - get_weather_history(39.9, 116.4, "2020-01-01", "2020-12-31")  # 北京 2020 年
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_weather_history,
        latitude=latitude, longitude=longitude,
        start_date=start_date, end_date=end_date, daily_vars=daily_vars,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_exploit_db(query: Optional[str] = None, limit: int = 25) -> str:
    """
    Exploit-DB 漏洞利用代码库 (Offensive Security 维护)

    Args:
        query: 关键词过滤 (不填则返回所有最新)
        limit: 返回数量, 默认 25

    Returns:
        JSON: exploits 列表 (最新发布的漏洞 PoC)

    Examples:
        - search_exploit_db("wordpress")
        - search_exploit_db()  # 最新全部
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_exploit_db, query=query, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_musicbrainz(
    query: str,
    entity: str = "artist",
    limit: int = 20,
) -> str:
    """
    MusicBrainz 开放音乐百科 (50M+ 艺术家/专辑/歌曲)

    Args:
        query: 搜索关键词
        entity: artist / release / release-group / recording / label / work
        limit: 返回数量, 默认 20, 最大 100

    Returns:
        JSON: 音乐实体列表

    Examples:
        - search_musicbrainz("Beatles", entity="artist")
        - search_musicbrainz("Dark Side of the Moon", entity="release-group")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_musicbrainz,
        query=query, entity=entity, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def get_crossref_events(
    doi: Optional[str] = None,
    source: Optional[str] = None,
    rows: int = 25,
) -> str:
    """
    CrossRef Event Data - DOI 论文在社交媒体被提及事件

    可用来: 追踪论文的公众影响力、查看论文在 Wikipedia/Twitter/Reddit 的扩散。

    Args:
        doi: 目标 DOI (如 "10.1038/s41586-023-06747-5")
        source: 过滤来源 - wikipedia / twitter / reddit / newsfeed / f1000 / stackexchange
        rows: 返回数量, 默认 25, 最大 500

    Returns:
        JSON: events 列表 (含提及方 / 被引 DOI / 发生时间)

    Examples:
        - get_crossref_events(source="wikipedia")
        - get_crossref_events(doi="10.1038/s41586-023-06747-5")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_crossref_events,
        doi=doi, source=source, rows=rows,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def search_artifact_hub(
    query: str,
    kind: Optional[int] = None,
    limit: int = 25,
) -> str:
    """
    Artifact Hub - Kubernetes 生态包 (Helm / Operators / OPA / Argo 等)

    Args:
        query: 关键词
        kind: 0=Helm / 3=OLM operator / 8=Container image /
              11=Kyverno policy / 13=Backstage plugin / 14=Argo template
              完整: https://artifacthub.io/docs/topics/repositories/
        limit: 返回数量, 默认 25, 最大 60

    Returns:
        JSON: packages 列表 (含版本 / stars / 官方认证)

    Examples:
        - search_artifact_hub("prometheus", kind=0)
        - search_artifact_hub("cert-manager")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].search_artifact_hub,
        query=query, kind=kind, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
async def check_ai_providers() -> str:
    """
    一键检查 AI 能力配置状态 (LLM 对话模型 + 4 个 AI 搜索 provider)

    Returns:
        每个 provider 的 configured 状态 + 对应的环境变量名和注册链接
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['ai'].check_ai_providers)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def ai_summarize(
    text: str,
    style: str = "bullet",
    max_points: int = 5,
    target_language: str = "zh-CN",
) -> str:
    """
    LLM 驱动的文本摘要. 需 AI_API_KEY 环境变量.

    Args:
        text: 待摘要的文本
        style: bullet (要点) / paragraph (段落) / tldr (一句话)
        max_points: bullet 模式的条数, 默认 5
        target_language: 输出语种 (zh-CN / en / ja / ko / fr / de / ...)

    Returns:
        JSON envelope: { summary, style, language }

    Examples:
        - ai_summarize(text="一长篇论文...", style="tldr", target_language="zh-CN")
        - ai_summarize(text="英文新闻", max_points=7, target_language="zh-CN")

    Tip: 配合 read_article / search_news 可做"读完就摘要"的组合操作。
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai'].ai_summarize,
        text=text, style=style, max_points=max_points,
        target_language=target_language,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def ai_translate(
    text: str,
    target_language: str = "zh-CN",
    source_language: Optional[str] = None,
    preserve_format: bool = True,
) -> str:
    """
    LLM 驱动的翻译. 需 AI_API_KEY 环境变量.

    Args:
        text: 待翻译文本 (支持 markdown / HTML)
        target_language: 目标语种, 默认 zh-CN
        source_language: 源语种, 不填自动识别
        preserve_format: 是否保留原文格式标记 (默认 True)

    Returns:
        JSON envelope: { translated, target_language, source_language }

    Examples:
        - ai_translate(text="Hello world", target_language="zh-CN")
        - ai_translate(text="一段中文", target_language="en")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai'].ai_translate,
        text=text, target_language=target_language,
        source_language=source_language, preserve_format=preserve_format,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def ai_brief_news(
    news_items: List[Dict],
    style: str = "oneline",
    target_language: str = "zh-CN",
) -> str:
    """
    批量新闻 AI 简报 (把 N 条新闻合并成一张精简榜).

    Args:
        news_items: [{title, body?, url?, source?}, ...]
        style: oneline (一行) / headline (头条式) / digest (段落)
        target_language: 输出语种

    Returns:
        JSON envelope: { briefing, items_processed }

    Tip: 配合 get_latest_news 的输出可做"当日热点 AI 简报"
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai'].ai_brief_news,
        news_items=news_items, style=style, target_language=target_language,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def ai_web_search(
    query: str,
    provider: str = "tavily",
    max_results: int = 10,
    include_answer: bool = True,
    search_depth: str = "basic",
) -> str:
    """
    AI 优化型网络搜索 (专为 LLM 设计, 返回结构化结果 + 可选总结).

    Args:
        query: 搜索关键词
        provider:
            - tavily (1000/月免费, 专为 LLM, 推荐)
            - exa (语义搜索, 适合发现高质量长文)
            - perplexity (LLM 总结+引用, 付费)
            - brave (2000/月免费, 独立索引, 无审查)
        max_results: 返回数量, 默认 10
        include_answer: 是否返回 AI 生成的总结 (部分 provider 支持)
        search_depth: basic / advanced (部分 provider 的深度模式)

    环境变量 (按 provider):
        TAVILY_API_KEY / EXA_API_KEY / PERPLEXITY_API_KEY / BRAVE_API_KEY

    Returns:
        JSON envelope: { results, answer?, query, ... }

    Examples:
        - ai_web_search(query="GPT-5 发布时间", provider="tavily")
        - ai_web_search(query="climate change 2026", provider="perplexity")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai'].ai_web_search,
        query=query, provider=provider, max_results=max_results,
        include_answer=include_answer, search_depth=search_depth,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def semantic_deduplicate(
    news_items: List[Dict],
    group_threshold: str = "same_event",
    include_summary: bool = True,
    target_language: str = "zh-CN",
) -> str:
    """
    LLM 驱动的新闻语义去重 (比 aggregate_news 基于字符串相似度更智能)

    适合: 跨平台同一事件的多源报道合并 ("某新闻在微博/今日头条/知乎同时出现")

    Args:
        news_items: [{title, platform?, url?, ...}, ...] 最多 80 条
        group_threshold:
            - same_event:  同一具体事件才合并 (严格, 默认)
            - same_topic:  同一主题就合并 (宽松)
            - same_entity: 涉及同一人物/公司就合并 (最宽松)
        include_summary: 每组生成一句摘要 (默认 True)
        target_language: 输出语种

    Returns:
        JSON: { clusters: [{cluster_id, representative_title, summary, platforms, item_indices, size}], compression_ratio }

    环境变量: 需要 AI_API_KEY

    Examples:
        - 把 get_latest_news(limit=60) 输出喂给本工具 → 得到去重后的事件列表
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai_analytics'].semantic_deduplicate,
        news_items=news_items, group_threshold=group_threshold,
        include_summary=include_summary, target_language=target_language,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def detect_anomaly(
    topic: Optional[str] = None,
    lookback_days: int = 14,
    z_threshold: float = 2.0,
    min_frequency: int = 3,
    top_n: int = 20,
) -> str:
    """
    时序异常检测 - 发现突发增长或急剧衰退的话题 (基于 z-score)

    原理: 对每个关键词, 计算 (最新日频次 - 历史均值) / 历史标准差。
    |z| >= 阈值 → 异常。z > 0 = 突发, z < 0 = 衰退, inf = 新出现。

    Args:
        topic: 限定关键词 (不填扫全部)
        lookback_days: 回溯天数, 默认 14
        z_threshold: 异常阈值, 默认 2.0 (2σ 约 95% 置信)
        min_frequency: 最小基础频次 (过滤噪声), 默认 3
        top_n: 返回 TOP N 异常

    Returns:
        JSON: { anomalies: [{keyword, z_score, latest_count, baseline_mean, trend}], ... }

    Note: 需要本地有 Argus 历史数据 (output/news/*.db), 可用 trigger_crawl 累积。

    Examples:
        - detect_anomaly()                            # 全量扫
        - detect_anomaly(topic="AI")                  # 只看 AI 相关
        - detect_anomaly(z_threshold=3.0, top_n=5)    # 严苛阈值
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai_analytics'].detect_anomaly,
        topic=topic, lookback_days=lookback_days, z_threshold=z_threshold,
        min_frequency=min_frequency, top_n=top_n,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def analyze_with_ai(
    news_items: Optional[List[Dict]] = None,
    topic: Optional[str] = None,
    mode: str = "full",
) -> str:
    """
    组合分析 - 一次调用同时做"语义去重 + 异常检测"

    Args:
        news_items: 待去重的新闻列表 (mode=full/dedup 时需要)
        topic: 异常检测的话题过滤
        mode:
            - full    — 两样都做 (需 news_items)
            - dedup   — 只语义去重
            - anomaly — 只异常检测

    Returns:
        JSON: { mode, dedup?: {...}, anomaly?: {...} }
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['ai_analytics'].analyze_with_ai,
        news_items=news_items, topic=topic, mode=mode,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 跨平台 (Batch 4a / 4b) ====================

@mcp.tool
async def narrative_tracking(
    topic: str,
    platforms: Optional[List[str]] = None,
    limit_per_platform: int = 15,
    use_llm: bool = True,
) -> str:
    """
    跨平台叙事追踪: 对比同一话题在 news/hn/reddit/xhs/bili/twitter/tg/discord 上的情感走向

    逻辑:
        1. 并发拉各平台关于 topic 的条目
        2. LLM 打情感分 (无 AI_API_KEY 则自动降级规则打分)
        3. 汇总每平台的 mean_sentiment / volume / top_titles
        4. 给出 most_positive / most_negative / highest_volume 三个排名

    Args:
        topic: 话题关键词 (必需)
        platforms: 默认 ["news","hn","reddit","xhs","bili"]. 可加 "twitter","tg","discord"
        limit_per_platform: 每平台拉多少条, 默认 15
        use_llm: 是否用 LLM 打分; 默认 True. 未配置 key 自动回退到规则

    Examples:
        - narrative_tracking(topic="Nvidia")
        - narrative_tracking(topic="AI 监管", platforms=["news","xhs","bili"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cross'].narrative_tracking,
        topic=topic, platforms=platforms,
        limit_per_platform=limit_per_platform, use_llm=use_llm,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def universal_search(
    query: str,
    sources: Optional[List[str]] = None,
    limit: int = 10,
) -> str:
    """
    跨源统一搜索: 一次调用路由到多个 source 并归一化输出

    统一结构: {title, url, source, author, engagement, extra}

    Args:
        query: 查询关键词
        sources: 默认 ["news","hn","reddit","xhs","bili"]
                 支持: news/hn/reddit/xhs/bili/twitter/tg/discord
        limit: 每源返回条数, 默认 10

    Returns:
        JSON: { sources: {src: {count, items, error?}}, merged: [...] }

    Examples:
        - universal_search(query="Llama 4")
        - universal_search(query="老谭", sources=["bili","xhs"], limit=5)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cross'].universal_search,
        query=query, sources=sources, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 定时任务 (Batch 5a, launchd) ====================

@mcp.tool
async def schedule_task(
    name: str,
    workflow: Dict,
    schedule: Any,
    description: str = "",
    enabled: bool = True,
) -> str:
    """
    注册一个 macOS launchd 定时任务, 按 workflow DSL 顺序调用 MCP 工具

    workflow 示例:
        {
          "steps": [
            {"tool": "trigger_crawl", "args": {}},
            {"tool": "ai_brief_news", "args": {"style": "oneline"}},
            {"tool": "send_notification", "args": {"channel": "feishu"}}
          ]
        }

    schedule 支持:
        - "daily@09:00"              每天 09:00
        - "hourly"                   每小时 0 分
        - "every:30m"                每 30 分钟 (或 every:2h)
        - {"hour":9,"minute":0}      原生 StartCalendarInterval
        - [{"hour":9},{"hour":21}]   多触发点

    步骤间可引用上一步结果: "args": {"news_items": {"__prev__": "result.data.items"}}

    Args:
        name: 任务名 (字母开头, 2-48 位)
        workflow: {"steps": [...]}
        schedule: 见上
        description: 描述
        enabled: 立即 load 到 launchd (默认 True)

    Returns:
        JSON: 任务信息 + plist 路径
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['scheduler'].schedule_task,
        name=name, workflow=workflow, schedule=schedule,
        description=description, enabled=enabled,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def list_scheduled_tasks() -> str:
    """列出所有 Argus 定时任务 (名字/schedule/步骤数/是否 loaded)"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['scheduler'].list_scheduled_tasks)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def remove_scheduled_task(name: str) -> str:
    """卸载并删除一个定时任务 (launchctl unload + 删 plist/workflow)"""
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['scheduler'].remove_scheduled_task, name=name
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_scheduled_task(name: str) -> str:
    """立即手动触发一次已注册任务 (launchctl kickstart), 并返回 log tail"""
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['scheduler'].run_scheduled_task, name=name
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== MCP client 反向挂载 (Batch 5b) ====================

@mcp.tool
async def mcp_proxy_add(
    name: str,
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    description: str = "",
) -> str:
    """
    注册一个外部 MCP server (stdio), Argus 作为 client 代理调用

    Args:
        name: 逻辑名 (字母开头, <=31 位)
        command: 可执行文件路径或命令名 (如 "uvx")
        args: 参数列表 (如 ["mcp-server-fetch"])
        env: 额外环境变量
        description: 可选描述

    Examples:
        mcp_proxy_add(name="fetch", command="uvx", args=["mcp-server-fetch"])
        mcp_proxy_add(name="pw", command="npx", args=["-y","@modelcontextprotocol/server-playwright"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['mcp_proxy'].add,
        name=name, command=command, args=args, env=env, description=description,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def mcp_proxy_remove(name: str) -> str:
    """移除一个已注册的外部 MCP proxy"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['mcp_proxy'].remove, name=name)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def mcp_proxy_list() -> str:
    """列出所有已注册的外部 MCP proxy"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['mcp_proxy'].list_proxies)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def mcp_proxy_list_tools(
    name: Optional[str] = None,
    refresh: bool = False,
) -> str:
    """列出一个(或全部) proxy 上的可调用工具

    Args:
        name: 指定 proxy 名; 不传则列所有
        refresh: True 则重新连接拉取最新工具清单
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['mcp_proxy'].list_tools, name=name, refresh=refresh
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def mcp_proxy_call(
    name: str,
    tool: str,
    arguments: Optional[Dict] = None,
) -> str:
    """调用一个外部 MCP proxy 暴露的工具

    Args:
        name: proxy 名 (先用 mcp_proxy_add 注册)
        tool: 该 proxy 上的工具名 (用 mcp_proxy_list_tools 查)
        arguments: 工具参数字典

    Returns:
        JSON: { content: [{type:"text", text:"..."}], is_error }
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['mcp_proxy'].call, name=name, tool=tool, arguments=arguments,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 微信公众号 RSS (Batch 7) ====================

@mcp.tool
async def wechat_rss_status(port: int = 8080, host: str = "127.0.0.1") -> str:
    """
    探测本地 WeRSS (微信公众号 → RSS) 是否在运行

    WeRSS 安装: bash scripts/install-werss.sh install
    启动:       bash scripts/install-werss.sh bg
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['wechat'].werss_status, port=port, host=host
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def wechat_add_feed(
    url: str,
    name: str,
    feed_id: Optional[str] = None,
    enabled: bool = True,
    max_age_days: Optional[int] = None,
) -> str:
    """
    把一个微信公众号 RSS URL 加到 Argus config.yaml

    支持任意 RSS 源: 本地 werss (http://127.0.0.1:8080/feed/xxx) /
                    RSSHub /wechat/ce/xxx / feeddd / 自建

    Args:
        url: RSS 源 URL (必需)
        name: 显示名 (必需, 如 "公众号: 阮一峰的网络日志")
        feed_id: 自定义 ID, 留空自动生成 "wechat-<url末段>"
        enabled: 启用 (默认 True)
        max_age_days: 过滤 N 天前的文章, 0 或不填 = 不过滤

    写入会自动备份旧 config 到 config.yaml.bak
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['wechat'].add_feed,
        url=url, name=name, feed_id=feed_id,
        enabled=enabled, max_age_days=max_age_days,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def wechat_list_feeds(only_wechat: bool = True) -> str:
    """
    列出 Argus config.yaml 中已集成的 RSS feed

    Args:
        only_wechat: True 只列微信相关 (id=wechat-*, url 含 wechat/werss/mp.weixin)
                     False 列所有 feed
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['wechat'].list_feeds, only_wechat=only_wechat
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def wechat_remove_feed(feed_id: str) -> str:
    """从 Argus config.yaml 移除一个 feed"""
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['wechat'].remove_feed, feed_id=feed_id
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 本地语义搜索 (Batch 8, BM25 + jieba) ====================

@mcp.tool
async def semantic_index_rebuild(days: int = 30) -> str:
    """
    全量重建本地 BM25 索引 (跨天新闻标题)

    用途: 为 semantic_search / semantic_similar 提供底层索引
    建议在 schedule_task 里配每天 00:05 自动跑

    Args:
        days: 回溯天数, 默认 30
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['semantic'].rebuild, days=days)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def semantic_index_status() -> str:
    """查看本地 BM25 索引的元信息 (构建时间/文档数/词表大小)"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['semantic'].status)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def semantic_search(
    query: str,
    window_days: Optional[int] = None,
    limit: int = 20,
    platforms: Optional[List[str]] = None,
    min_score: float = 0.0,
) -> str:
    """
    跨天全文搜索 (BM25 + jieba 中文分词)

    比 search_news (字符串匹配) 更准: 支持词形/近义召回, 跨多天

    Args:
        query: 查询串 (中英混合, 如 "AI 监管" / "Nvidia H100")
        window_days: 只返回最近 N 天 (不传=索引全量)
        limit: 返回条数, 默认 20
        platforms: 平台过滤 (中文名列表)
        min_score: BM25 分数下限, 默认 0 (返回所有匹配)

    Examples:
        - semantic_search("AI 监管")
        - semantic_search("Nvidia", window_days=7, platforms=["知乎","微博"])
        - semantic_search("特斯拉降价", limit=50, min_score=2.0)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['semantic'].search,
        query=query, window_days=window_days, limit=limit,
        platforms=platforms, min_score=min_score,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def semantic_similar(title: str, limit: int = 10) -> str:
    """
    给一个标题, 找历史中最相似的标题 (BM25 近邻)

    用途: 去重 / 发现重复报道 / 找"这件事之前有没有发生过"

    Args:
        title: 参考标题
        limit: 返回条数, 默认 10
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['semantic'].similar, title=title, limit=limit
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== Alert 规则引擎 (Batch 9) ====================

@mcp.tool
async def alert_add(
    name: str,
    when: Dict,
    notify: Dict,
    description: str = "",
    enabled: bool = True,
) -> str:
    """
    添加告警规则 (落盘到 config/alerts.yaml)

    when 支持 3 种类型:
        1. keyword_count — 关键词命中次数 >= threshold
           {"type":"keyword_count","keyword":"Nvidia","window_days":1,"threshold":5}
        2. anomaly — 复用 detect_anomaly
           {"type":"anomaly","z_threshold":2.5,"min_frequency":3}
        3. semantic_hit — BM25 查询命中
           {"type":"semantic_hit","query":"AI 监管","min_score":1.5,"threshold":3}

    notify 示例:
        {"channel":"feishu","title":"⚡ Nvidia 声量激增",
         "template":"今天 {platforms} 共出现 {count} 次讨论\\n{top_titles}"}

    可用模板变量: {rule} {count} {platforms} {top_titles} {now}

    评估入口: alert_run_all() 或 schedule_task 配 workflow=[{tool:alert_run_all}]
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['alerts'].add,
        name=name, when=when, notify=notify,
        description=description, enabled=enabled,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def alert_list() -> str:
    """列出 config/alerts.yaml 里所有规则"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['alerts'].list_rules)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def alert_remove(name: str) -> str:
    """删除一条告警规则"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['alerts'].remove, name=name)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def alert_test(name: str) -> str:
    """干跑一条规则, 评估但不真推送 (用来调阈值)"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['alerts'].test, name=name)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def alert_run_all() -> str:
    """
    评估所有启用的规则, 命中就推送

    推荐用法: 在 schedule_task 里配
        workflow = [{"tool": "alert_run_all"}]
        schedule = "hourly"  或 "every:30m"
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['alerts'].run_all)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== Obsidian / Markdown 导出 (Batch 10) ====================

@mcp.tool
async def export_daily_brief(
    date: Optional[str] = None,
    output_dir: Optional[str] = None,
    vault_style: bool = True,
    top_keywords: int = 20,
    top_per_platform: int = 10,
    append: bool = False,
) -> str:
    """
    导出某日新闻简报为 markdown (兼容 Obsidian daily notes + Dataview frontmatter)

    默认落到 $ARGUS_VAULT 或 ~/Desktop/Argus-Vault/daily/YYYY-MM-DD.md

    Args:
        date: YYYY-MM-DD, 不传用最近可用日期
        output_dir: 自定义 vault 目录 (会自动建 daily/ 子目录)
        vault_style: 是否用 Obsidian 双链 [[关键词]]
        top_keywords: 顶部趋势词数量
        top_per_platform: 每平台展示多少条
        append: 同日文件存在时追加新 section (默认覆盖)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['exporter'].export_daily_brief,
        date=date, output_dir=output_dir, vault_style=vault_style,
        top_keywords=top_keywords, top_per_platform=top_per_platform,
        append=append,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def export_query_report(
    query: str,
    output_path: Optional[str] = None,
    window_days: int = 30,
    limit: int = 50,
) -> str:
    """
    把对 query 的 BM25 搜索结果导成 markdown 报告, 按日期分组

    落到 $ARGUS_VAULT/queries/query-<slug>-<ts>.md
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['exporter'].export_query_report,
        query=query, output_path=output_path,
        window_days=window_days, limit=limit,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def export_anomalies(
    output_path: Optional[str] = None,
    lookback_days: int = 14,
    z_threshold: float = 2.0,
) -> str:
    """
    把异常检测结果导为 markdown 表格

    落到 $ARGUS_VAULT/anomalies/anomaly-<ts>.md
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['exporter'].export_anomalies,
        output_path=output_path,
        lookback_days=lookback_days,
        z_threshold=z_threshold,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 健康监控 (Batch 11) ====================

@mcp.tool
async def system_health() -> str:
    """
    综合健康检查: 数据新鲜度 / BM25 索引 / RSSHub / 磁盘 / 定时任务 / 告警规则
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['health'].system_health)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def tool_stats(top_n: int = 30) -> str:
    """
    工具调用统计 (当前会话累计): 次数 / 错误率 / 延迟 p50/p95

    数据源: output/telemetry/tool_calls.<date>.jsonl
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['health'].tool_stats, top_n=top_n)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 内容安全扫描 (Batch 12) ====================

@mcp.tool
async def safety_scan_titles(titles: List[str]) -> str:
    """
    批量扫描标题, 命中规则返回标记 (PII/诈骗/广告/成人等)

    规则来自内置 + config/safety_rules.yaml (可选扩展)
    严重级别: high / medium / low
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['safety'].scan_titles, titles=titles)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def safety_scan_day(date: Optional[str] = None) -> str:
    """
    扫某日全量新闻标题 (不传 date 用最近日期)

    返回命中列表 + 按严重级别/类别/规则的计数
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['safety'].scan_day, date=date)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def safety_list_rules() -> str:
    """列出当前生效的所有安全规则 (regex + 关键词)"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['safety'].list_rules)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== bili/xhs 细化操作 (Batch 13) ====================
# 只读 (安全)
@mcp.tool
async def bili_my_dynamics(limit: int = 20) -> str:
    """查看自己发布的 B 站动态"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_my_dynamics, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_history(limit: int = 30) -> str:
    """查看 B 站观看历史"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_history, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_following(limit: int = 50) -> str:
    """查看 B 站关注列表"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_following, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_feed(limit: int = 20) -> str:
    """查看 B 站动态时间线 (关注的人的更新)"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_feed, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_hot(limit: int = 30) -> str:
    """查看 B 站热门视频"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_hot, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

# 轻互动 (可逆)
@mcp.tool
async def bili_like(video_id: str) -> str:
    """点赞 B 站视频 (再调一次取消)"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_like, video_id=video_id)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_triple(video_id: str) -> str:
    """B 站一键三连 (点赞+投币+收藏)"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_triple, video_id=video_id)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

# 发帖 (有副作用)
@mcp.tool
async def bili_publish_dynamic(text: str, confirm: bool = False) -> str:
    """发布 B 站纯文本动态. 须 confirm=True 才实际发送"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_publish_dynamic, text=text, confirm=confirm)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def bili_delete_dynamic(dynamic_id: str, confirm: bool = False) -> str:
    """删除自己的 B 站动态. 须 confirm=True"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].bili_delete_dynamic, dynamic_id=dynamic_id, confirm=confirm)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

# ─── 小红书 ───
@mcp.tool
async def xhs_my_notes(limit: int = 20) -> str:
    """查看自己在小红书发布的笔记"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_my_notes, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_notifications(limit: int = 30) -> str:
    """查看小红书通知 (@提及/点赞/关注)"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_notifications, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_favorites(limit: int = 20) -> str:
    """查看小红书收藏"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_favorites, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_feed(limit: int = 20) -> str:
    """浏览小红书推荐流"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_feed, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_hot(category: Optional[str] = None, limit: int = 30) -> str:
    """浏览小红书热门笔记 (可按 category)"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_hot, category=category, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_comments(note_id: str, limit: int = 20) -> str:
    """查看指定笔记的评论"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_comments, note_id=note_id, limit=limit)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_like(note_id: str) -> str:
    """给小红书笔记点赞"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_like, note_id=note_id)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_favorite(note_id: str) -> str:
    """收藏小红书笔记"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_favorite, note_id=note_id)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_comment(note_id: str, text: str, confirm: bool = False) -> str:
    """给小红书笔记发评论 (公开). 须 confirm=True"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_comment, note_id=note_id, text=text, confirm=confirm)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_publish_note(
    images: List[str],
    title: str,
    content: str,
    confirm: bool = False,
) -> str:
    """发布图文笔记到小红书. images 是本地图片路径列表. 须 confirm=True"""
    t = _get_tools()
    r = await asyncio.to_thread(
        t['social'].xhs_publish_note,
        images=images, title=title, content=content, confirm=confirm,
    )
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)

@mcp.tool
async def xhs_delete_note(note_id: str, confirm: bool = False) -> str:
    """删除自己发布的小红书笔记. 须 confirm=True"""
    t = _get_tools()
    r = await asyncio.to_thread(t['social'].xhs_delete_note, note_id=note_id, confirm=confirm)
    return json.dumps(r, ensure_ascii=False, indent=2, default=str)


# ==================== 多账号通知路由 (Batch 14) ====================

@mcp.tool
async def route_add(
    name: str,
    webhooks: List[Dict],
    keywords: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    match_mode: str = "any",
    description: str = "",
    enabled: bool = True,
) -> str:
    """
    添加一条通知路由 (落到 config/notification_routes.yaml)

    示例: 技术话题推到 feishu-tech 群
        route_add(
          name="tech",
          keywords=["AI","GPU","Nvidia","LLM","Kubernetes"],
          webhooks=[{
            "name": "feishu-tech",
            "channel": "feishu",
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
          }]
        )

    Args:
        name: 路由名 (唯一)
        webhooks: [{channel, webhook_url, name?}, ...]
                  channel 支持: feishu/dingtalk/wework/slack/bark/ntfy/generic
        keywords: 消息正文包含这些词就命中
        topics: 调用方显式标注的 topic 匹配
        match_mode: any=任一命中 / all=全部命中

    至少要有 keywords 或 topics 之一
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['router'].add,
        name=name, webhooks=webhooks, keywords=keywords,
        topics=topics, match_mode=match_mode,
        description=description, enabled=enabled,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def route_list(include_urls: bool = False) -> str:
    """列出所有通知路由 (默认 webhook URL 只显示前缀保护)"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['router'].list_routes, include_urls=include_urls)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def route_remove(name: str) -> str:
    """删除一条路由"""
    tools = _get_tools()
    result = await asyncio.to_thread(tools['router'].remove, name=name)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def route_test(text: str, topics: Optional[List[str]] = None) -> str:
    """
    干跑: 给一段文本, 看会命中哪些路由 (不真发)
    用来调试 keywords/match_mode
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['router'].test, text=text, topics=topics)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def route_dispatch(
    text: str,
    title: str = "Argus 通知",
    topics: Optional[List[str]] = None,
) -> str:
    """
    按路由规则分发消息. 对所有命中的路由 × 所有 webhook 并行发送

    示例:
        route_dispatch(
          text="Nvidia H100 库存告急, 多家云厂商排队",
          title="⚡ GPU 动态"
        )
        → 命中 keyword "Nvidia" 的所有路由都推送
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['router'].dispatch, text=text, title=title, topics=topics
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ==================== 每日早报推送 (Batch 15) ====================

@mcp.tool
async def push_daily_brief(
    channels: Optional[List[str]] = None,
    title_prefix: str = "🌅 Argus",
    date: Optional[str] = None,
    top_keywords: int = 10,
    top_per_platform: int = 3,
    max_platforms: int = 8,
) -> str:
    """
    渲染并推送真实内容的每日早报 (替代 morning_brief 里的固定文案)

    文本特性:
        - 热词去子串重复 ("机器人"→保留, "机器"→丢)
        - 强停用词 (过滤"中国/美国/公司/男子"等大类虚词)
        - 每个热词附一条代表性标题 (无需再搜索)
        - 日期中文化 ("4 月 20 日 · 星期一")
        - 每平台展示 top 标题 (带可点击链接)

    Args:
        channels: 推送渠道, 默认全部已配置 (如 ["feishu"])
        title_prefix: 消息标题前缀
        date: YYYY-MM-DD, 不传用最新
        top_keywords: 热词数量, 默认 10
        top_per_platform: 每平台头条数, 默认 3
        max_platforms: 显示多少个平台, 默认 8
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['daily_brief'].push,
        channels=channels, title_prefix=title_prefix, date=date,
        top_keywords=top_keywords, top_per_platform=top_per_platform,
        max_platforms=max_platforms,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def render_daily_brief(
    date: Optional[str] = None,
    top_keywords: int = 10,
    top_per_platform: int = 3,
    max_platforms: int = 8,
) -> str:
    """
    只渲染早报 markdown (不推送), 返回 content 字符串
    用途: 预览 / 调试 / 其他用途(比如贴到 Obsidian)
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['daily_brief'].render,
        date=date, top_keywords=top_keywords,
        top_per_platform=top_per_platform, max_platforms=max_platforms,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def check_cli_auth() -> str:
    """
    一键检查 5 个本地 CLI 工具的认证状态 (bili/xhs/twitter/tg/discord)

    这 5 个工具由 jackwener 维护, 专为 AI 代理设计, 支持 agent-friendly YAML envelope。
    通过 `uv tool install` 本地安装, 通过浏览器 cookie 或 QR 扫码认证。

    Returns:
        JSON: 每个 CLI 的 installed / auth / user 信息
    """
    tools = _get_tools()
    result = await asyncio.to_thread(tools['cli'].check_cli_auth)
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_bilibili(
    subcommand: str,
    args: Optional[List[str]] = None,
    timeout: int = 60,
) -> str:
    """
    调用 bili CLI (B 站). 自动加 --yaml, 返回结构化 envelope

    常用子命令 (完整列表见 bili --help):
      - search <keyword> [--type video|user] [-n 10]   搜索视频/用户
      - video <BVID>                                   视频详情 + 字幕 + AI 摘要
      - user-videos <UID> [-n 10]                      UP 主视频列表
      - user <UID>                                     UP 主资料
      - hot [-n 10]                                    全站热门视频
      - rank                                           全站排行榜
      - feed [-n 20]                                   关注流
      - favorites                                      收藏夹
      - my-dynamics                                    我发布的动态
      - history                                        观看历史

    Args:
        subcommand: bili 子命令, 如 "search"、"video"、"hot"
        args: 位置参数和选项, 如 ["Claude Code", "--type", "video", "-n", "3"]
        timeout: 超时 (秒)

    Returns:
        JSON envelope: {ok, data, error}

    Examples:
        - run_bilibili("search", ["Claude Code", "--type", "video", "-n", "5"])
        - run_bilibili("video", ["BV1GtdpBZEx8"])
        - run_bilibili("user-videos", ["546195", "-n", "10"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cli'].run_bilibili,
        subcommand=subcommand, args=args, timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_xhs(
    subcommand: str,
    args: Optional[List[str]] = None,
    timeout: int = 60,
) -> str:
    """
    调用 xhs CLI (小红书). 自动加 --yaml, 返回结构化 envelope

    常用子命令 (完整列表见 xhs --help):
      - search <keyword> [--sort popular|latest] [--type video|image]  搜索笔记
      - search-user <keyword>                                          搜索用户
      - topics <keyword>                                               搜索话题
      - hot [-c fashion|food|cosmetics|travel|fitness|...]             分类热榜
      - feed                                                           推荐流
      - read <note_id|url>                                             笔记详情
      - comments <note_id>                                             笔记评论
      - user <user_id>                                                 用户资料
      - user-posts <user_id>                                           用户笔记
      - notifications                                                  通知

    Args:
        subcommand: xhs 子命令
        args: 位置参数和选项
        timeout: 超时

    Returns:
        JSON envelope

    Examples:
        - run_xhs("search", ["AI 工具", "--sort", "popular"])
        - run_xhs("read", ["69cf17b20000000023005fe0"])
        - run_xhs("hot", ["-c", "gaming"])
        - run_xhs("user-posts", ["<xhs_user_id>"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cli'].run_xhs,
        subcommand=subcommand, args=args, timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_twitter(
    subcommand: str,
    args: Optional[List[str]] = None,
    timeout: int = 60,
) -> str:
    """
    调用 twitter CLI (Twitter/X). 需先登录 x.com 让 CLI 从浏览器 cookie 自动提取

    常用子命令:
      - feed [-n 20] [--following]              主页时间线 (For You / Following)
      - search "<query>" [-n 10] [--latest]     搜索推文
      - tweet <tweet_id>                        推文详情 + 回复
      - user <handle>                           用户资料
      - user --likes <handle>                   用户点赞
      - user --tweets <handle>                  用户推文
      - article <tweet_id>                      长文 (Twitter Article)
      - list <list_id>                          List 时间线
      - bookmarks                               我的书签
      - post "<text>"                           发推 (需写权限)
      - reply <tweet_id> "<text>"               回复
      - quote <tweet_id> "<text>"               引用

    Args:
        subcommand: twitter 子命令
        args: 参数
        timeout: 超时

    Returns:
        JSON envelope (未登录时返回 not_authenticated)

    Examples:
        - run_twitter("search", ["Claude 3.5", "--latest", "-n", "5"])
        - run_twitter("user", ["AnthropicAI"])
        - run_twitter("feed", ["-n", "20"])
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cli'].run_twitter,
        subcommand=subcommand, args=args, timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_telegram(
    subcommand: str,
    args: Optional[List[str]] = None,
    timeout: int = 90,
) -> str:
    """
    调用 tg CLI (Telegram). 首次需输入手机号 + 验证码; 连接需要代理 (国内)

    特色: 本地 SQLite 缓存, 搜索查本地不打 API, 速度快 + 不会限流。

    常用子命令:
      - whoami                            当前账号
      - chats                             对话列表
      - sync-all                          同步所有对话到本地
      - sync <chat>                       增量同步某个对话
      - today                             今日消息 (所有对话)
      - recent [-n 100]                   最近消息
      - search "<keyword>" [-c <chat>]    搜索消息
      - filter "keyword1,keyword2" [-c <chat>]   多关键词过滤
      - history <chat> [--limit 100]      历史消息
      - timeline <chat>                   活动时间图
      - top                               最活跃发送者
      - stats                             按对话统计
      - export <chat> [-o file.txt]       导出
      - send <chat> "<msg>"               发消息

    Args:
        subcommand: tg 子命令
        args: 参数
        timeout: 超时 (默认 90s, Telegram 有时慢)

    Returns:
        JSON envelope

    Examples:
        - run_telegram("chats")
        - run_telegram("search", ["Claude", "-c", "某群组"])
        - run_telegram("today")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cli'].run_telegram,
        subcommand=subcommand, args=args, timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def run_discord(
    subcommand: str,
    args: Optional[List[str]] = None,
    timeout: int = 60,
) -> str:
    """
    调用 discord CLI. 需 DISCORD_TOKEN 环境变量 (从浏览器 DevTools 提取)

    ⚠️ 风险: Discord 官方禁止 user token 自动化, 被检测可能封号。只在自己账号自己机器使用。

    常用子命令:
      - whoami                                当前账号
      - status                                认证状态
      - dc list                               服务器列表
      - dc channels <server_id>               服务器频道列表
      - dc sync-all                           同步所有频道到本地
      - dc sync <channel>                     同步某频道
      - today                                 今日消息
      - recent [-n 100]                       最近消息
      - search "<keyword>" [-c <channel>]     搜索
      - export <channel> [-o file.txt]        导出
      - stats                                 频道统计
      - top                                   最活跃用户
      - timeline                              活动时间线

    Args:
        subcommand
        args: 参数
        timeout: 超时

    Returns:
        JSON envelope
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['cli'].run_discord,
        subcommand=subcommand, args=args, timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool
async def get_package_info(package: str, ecosystem: str = "pypi") -> str:
    """
    查询软件包信息 (PyPI / NPM, 含版本/下载量)

    Args:
        package: 包名, 如 "requests"、"react"、"langchain"
        ecosystem: pypi (Python) / npm (JavaScript)

    Returns:
        JSON: 包元数据 (最新版本 / 描述 / 许可证 / 下载量 / 历史版本)

    Examples:
        - get_package_info(package="anthropic", ecosystem="pypi")
        - get_package_info(package="next", ecosystem="npm")
    """
    tools = _get_tools()
    result = await asyncio.to_thread(
        tools['external'].get_package_info,
        package=package, ecosystem=ecosystem,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ==================== 启动入口 ====================

def run_server(
    project_root: Optional[str] = None,
    transport: str = 'stdio',
    host: str = '0.0.0.0',
    port: int = 3333
):
    """
    启动 MCP 服务器

    Args:
        project_root: 项目根目录路径
        transport: 传输模式，'stdio' 或 'http'
        host: HTTP模式的监听地址，默认 0.0.0.0
        port: HTTP模式的监听端口，默认 3333
    """
    # 初始化工具实例
    _get_tools(project_root)

    # 打印启动信息
    print()
    print("=" * 60)
    print("  Argus MCP Server - FastMCP 2.0")
    print("=" * 60)
    print(f"  传输模式: {transport.upper()}")

    if transport == 'stdio':
        print("  协议: MCP over stdio (标准输入输出)")
        print("  说明: 通过标准输入输出与 MCP 客户端通信")
    elif transport == 'http':
        print(f"  协议: MCP over HTTP (生产环境)")
        print(f"  服务器监听: {host}:{port}")

    if project_root:
        print(f"  项目目录: {project_root}")
    else:
        print("  项目目录: 当前目录")

    print()
    print("  已注册的工具:")
    print("    === 日期解析工具（推荐优先调用）===")
    print("    0. resolve_date_range       - 解析自然语言日期为标准格式")
    print()
    print("    === 基础数据查询（P0核心）===")
    print("    1. get_latest_news        - 获取最新新闻")
    print("    2. get_news_by_date       - 按日期查询新闻（支持自然语言）")
    print("    3. get_trending_topics    - 获取趋势话题（支持自动提取）")
    print()
    print("    === RSS 数据查询 ===")
    print("    4. get_latest_rss         - 获取最新 RSS 订阅数据")
    print("    5. search_rss             - 搜索 RSS 数据")
    print("    6. get_rss_feeds_status   - 获取 RSS 源状态")
    print()
    print("    === 智能检索工具 ===")
    print("    7. search_news            - 统一新闻搜索（关键词/模糊/实体）")
    print("    8. find_related_news      - 相关新闻查找（支持历史数据）")
    print()
    print("    === 高级数据分析 ===")
    print("    9. analyze_topic_trend      - 统一话题趋势分析（热度/生命周期/爆火/预测）")
    print("    10. analyze_data_insights   - 统一数据洞察分析（平台对比/活跃度/关键词共现）")
    print("    11. analyze_sentiment       - 情感倾向分析")
    print("    12. aggregate_news          - 跨平台新闻聚合去重")
    print("    13. compare_periods         - 时期对比分析（周环比/月环比）")
    print("    14. generate_summary_report - 每日/每周摘要生成")
    print()
    print("    === 配置与系统管理 ===")
    print("    15. get_current_config      - 获取当前系统配置")
    print("    16. get_system_status       - 获取系统运行状态")
    print("    17. check_version           - 检查版本更新（对比本地与远程版本）")
    print("    18. trigger_crawl           - 手动触发爬取任务")
    print()
    print("    === 存储同步工具 ===")
    print("    19. sync_from_remote        - 从远程存储拉取数据到本地")
    print("    20. get_storage_status      - 获取存储配置和状态")
    print("    21. list_available_dates    - 列出本地/远程可用日期")
    print()
    print("    === 文章内容读取 ===")
    print("    22. read_article            - 读取单篇文章内容（Markdown格式）")
    print("    23. read_articles_batch     - 批量读取多篇文章（自动限速）")
    print()
    print("    === 通知推送工具 ===")
    print("    24. get_channel_format_guide  - 获取渠道格式化策略指南（提示词）")
    print("    25. get_notification_channels - 获取已配置的通知渠道状态")
    print("    26. send_notification         - 向通知渠道发送消息（自动适配格式）")
    print()
    print("    === 外部数据源 - 学术论文 ===")
    print("    27. search_arxiv              - arXiv 论文")
    print("    28. search_semantic_scholar   - Semantic Scholar (含 AI TLDR)")
    print("    29. search_openalex           - OpenAlex 2.4 亿论文元数据")
    print("    30. search_pubmed             - PubMed 医学/生物")
    print("    31. search_crossref           - CrossRef DOI 元数据")
    print("    32. search_openreview         - OpenReview (顶会投稿+评审)")
    print("    33. search_dblp               - DBLP 计算机文献库")
    print("    34. search_inspire_hep        - inspire-HEP 高能物理")
    print("    35. search_all_academic       - 跨学术源统一搜索")
    print()
    print("    === 外部数据源 - 社区/媒体/视频 ===")
    print("    36. get_hackernews_top        - HN 实时榜单")
    print("    37. search_hackernews         - HN 全文历史搜索 (Algolia)")
    print("    38. search_reddit             - Reddit 任意 subreddit")
    print("    39. search_mastodon           - Mastodon 联邦社交")
    print("    40. search_stackexchange      - Stack Exchange 问答")
    print("    41. get_youtube_channel       - YouTube 频道订阅")
    print("    42. search_wikipedia          - Wikipedia 文章搜索")
    print()
    print("    === 外部数据源 - 代码/AI 生态 ===")
    print("    43. get_github_trending       - GitHub 热门仓库")
    print("    44. get_github_releases       - GitHub 仓库发布动态")
    print("    45. search_github_code        - GitHub 代码搜索 (需 token)")
    print("    46. get_package_info          - PyPI / NPM 包信息")
    print("    47. search_huggingface        - Hugging Face 模型/数据集")
    print()
    print("    === 外部数据源 - 全球事件/市场/政府/安全 ===")
    print("    48. search_gdelt              - GDELT 全球新闻事件库")
    print("    49. get_wikipedia_trending    - Wikipedia 浏览趋势")
    print("    50. get_crypto_trending       - CoinGecko 加密货币热门")
    print("    51. get_crypto_markets        - CoinGecko 价格/市值/涨跌")
    print("    52. search_sec_edgar          - SEC EDGAR 美股公开文件")
    print("    53. search_cve                - NVD CVE 漏洞库")
    print()
    print("    === 外部数据源 - 自然/科学/经济/社会 ===")
    print("    54. get_earthquakes           - USGS 全球地震实时数据")
    print("    55. get_nasa_data             - NASA APOD/NeoWs (天文/小行星)")
    print("    56. get_weather               - Open-Meteo 全球天气预报")
    print("    57. query_wikidata            - Wikidata 知识图谱(SPARQL)")
    print("    58. get_worldbank_indicator   - World Bank 国家经济指标")
    print("    59. get_lobsters              - Lobsters 高质量技术社区")
    print("    60. get_pypi_stats            - PyPI 包下载量趋势")
    print()
    print("    === 外部数据源 - 新社交/历史档案 ===")
    print("    61. search_bluesky            - Bluesky 去中心化社交")
    print("    62. search_lemmy              - Lemmy 联邦社区 (开源 Reddit)")
    print("    63. get_wayback               - Internet Archive 历史快照")
    print()
    print("    === CLI 工具套件 (jackwener's AI-agent CLIs) ===")
    print("    64. check_cli_auth            - 一键查 5 个 CLI 认证状态")
    print("    65. run_bilibili              - B 站: search/video/hot/feed/...")
    print("    66. run_xhs                   - 小红书: search/read/hot/user-posts/...")
    print("    67. run_twitter               - Twitter/X: feed/search/user/article/...")
    print("    68. run_telegram              - Telegram: search/today/sync/export/...")
    print("    69. run_discord               - Discord: search/today/recent/export/...")
    print()
    print("    === 外部数据源 - 包生态/书籍/安全 ===")
    print("    64. search_ghsa               - GitHub Advisory 开源漏洞")
    print("    65. search_books              - Open Library 图书 (4000万+)")
    print("    66. search_crates             - Crates.io Rust 包")
    print("    67. search_jsr                - JSR JS/TS 包 (Deno 维护)")
    print("    68. search_docker_hub         - Docker Hub 容器镜像")
    print()
    print("    === 外部数据源 - 人道/汇率/加密详情 ===")
    print("    69. search_reliefweb          - UN OCHA 人道/灾难 (需免费注册 appname)")
    print("    70. get_exchange_rates        - Frankfurter/ECB 汇率")
    print("    71. get_crypto_details        - CoinPaprika 币种详情")
    print()
    print("    === 外部数据源 - Git/应用/VSCode ===")
    print("    72. search_gitlab             - GitLab.com 公开项目")
    print("    73. search_homebrew           - Homebrew formula/cask")
    print("    74. search_flathub            - Flathub Linux 应用")
    print("    75. search_vscode_extensions  - VSCode 扩展商店")
    print("    76. search_artifact_hub       - Kubernetes Helm/Operator/Argo")
    print()
    print("    === 外部数据源 - 气象历史/漏洞利用/音乐/论文社媒 ===")
    print("    77. get_weather_history       - Open-Meteo Archive 1940+ 历史气象")
    print("    78. search_exploit_db         - Exploit-DB 漏洞利用代码")
    print("    79. search_musicbrainz        - MusicBrainz 音乐百科")
    print("    80. get_crossref_events       - CrossRef Event DOI 社媒提及")
    print("=" * 60)
    print()

    # 根据传输模式运行服务器
    if transport == 'stdio':
        mcp.run(transport='stdio')
    elif transport == 'http':
        # HTTP 模式（生产推荐）
        mcp.run(
            transport='http',
            host=host,
            port=port,
            path='/mcp'  # HTTP 端点路径
        )
    else:
        raise ValueError(f"不支持的传输模式: {transport}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Argus MCP Server - 新闻热点聚合 MCP 工具服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
详细配置教程请查看: README-Cherry-Studio.md
        """
    )
    parser.add_argument(
        '--transport',
        choices=['stdio', 'http'],
        default='stdio',
        help='传输模式：stdio (默认) 或 http (生产环境)'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='HTTP模式的监听地址，默认 0.0.0.0'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=3333,
        help='HTTP模式的监听端口，默认 3333'
    )
    parser.add_argument(
        '--project-root',
        help='项目根目录路径'
    )

    args = parser.parse_args()

    run_server(
        project_root=args.project_root,
        transport=args.transport,
        host=args.host,
        port=args.port
    )
