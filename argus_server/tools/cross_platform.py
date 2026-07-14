"""
跨平台叙事追踪 / 统一搜索 - Batch 4a + 4b 交付

Batch 4a: narrative_tracking
    同一话题在 Twitter / 小红书 / B站 / HN / Reddit / 本地热榜 上的情感走向对比。
    - 并发拉取每个 platform 的相关条目
    - LLM 情感打分（有 API key）或关键词规则 fallback
    - 输出 {platform: {mean_sentiment, volume, top_titles, top_outlets}}

Batch 4b: universal_search
    一次调用路由到多平台。归一化输出到 {title, url, source, author, engagement} 结构。

依赖：
    - CLIToolsAdapter (run_xhs / run_bilibili / run_twitter / run_telegram / run_discord)
    - ExternalAPITools (get_hackernews_top / search_reddit)
    - SearchTools (search_news_unified)
    - AIClient (可选，无 key 则走规则打分)
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import feedparser
import requests


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "CROSS_PLATFORM_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _response_error(response: Any, fallback_message: str) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(response, dict):
        return "INVALID_RESPONSE", fallback_message
    if response.get("success") is not False:
        return None, None
    error = response.get("error") or {}
    if isinstance(error, dict):
        return str(error.get("code") or "SOURCE_ERROR"), str(
            error.get("message") or fallback_message
        )
    return "SOURCE_ERROR", str(error or fallback_message)


def _rate_limit_metadata(headers: Any) -> Dict[str, str]:
    if not hasattr(headers, "get"):
        return {}
    values = {
        "limit": headers.get("x-ratelimit-limit"),
        "remaining": headers.get("x-ratelimit-remaining"),
        "reset": headers.get("x-ratelimit-reset"),
        "retry_after": headers.get("retry-after"),
    }
    return {key: str(value) for key, value in values.items() if value is not None}


def _reddit_subreddit_from_url(url: str) -> str:
    match = re.search(r"/r/([^/]+)/", url or "", flags=re.IGNORECASE)
    return match.group(1) if match else ""


# ────────────────────── 规则情感词典 (fallback) ──────────────────────

_POS_WORDS = [
    "好", "棒", "赞", "利好", "突破", "创新", "成功", "领先", "增长", "上涨",
    "获胜", "超越", "盈利", "高效", "优秀", "惊艳", "happy", "great", "amazing",
    "love", "win", "breakthrough", "success", "growth", "gain", "boost",
    "excellent", "brilliant", "awesome",
]
_NEG_WORDS = [
    "差", "烂", "坑", "下跌", "崩", "暴跌", "失败", "风险", "裁员", "破产",
    "违规", "处罚", "起诉", "垃圾", "翻车", "crash", "fail", "lose", "fraud",
    "scandal", "crisis", "loss", "bug", "vulnerability", "decline", "worst",
    "terrible", "bad",
]


def _rule_sentiment(text: str) -> float:
    """极简词典打分: 返回 [-1, 1]"""
    if not text:
        return 0.0
    t = text.lower()
    pos = sum(1 for w in _POS_WORDS if w in t)
    neg = sum(1 for w in _NEG_WORDS if w in t)
    if pos == neg == 0:
        return 0.0
    return (pos - neg) / max(1, (pos + neg))


_PLATFORM_LABEL = {
    "news": "本地热榜",
    "hn": "Hacker News",
    "reddit": "Reddit",
    "xhs": "小红书",
    "bili": "Bilibili",
    "twitter": "Twitter",
    "tg": "Telegram",
    "discord": "Discord",
}


class CrossPlatformTools:
    """跨平台叙事追踪 + 统一搜索"""

    def __init__(
        self,
        project_root: Optional[str] = None,
        cli_adapter=None,
        external_api=None,
        search_tools=None,
    ):
        self.project_root = project_root
        self._cli = cli_adapter
        self._ext = external_api
        self._search = search_tools
        self._llm = None

    # ────────────── LLM 懒加载 ──────────────

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from argus.ai.client import AIClient
            cfg = {
                "MODEL": os.environ.get("AI_MODEL", "deepseek/deepseek-chat"),
                "API_KEY": os.environ.get("AI_API_KEY", ""),
                "API_BASE": os.environ.get("AI_API_BASE", ""),
                "TEMPERATURE": 0.1,
                "MAX_TOKENS": 2000,
                "TIMEOUT": 60,
            }
            if not cfg["API_KEY"]:
                try:
                    from argus.core.loader import load_config
                    loaded = load_config()
                    ai_cfg = loaded.get("ai", {}) if isinstance(loaded, dict) else {}
                    cfg["API_KEY"] = ai_cfg.get("API_KEY", "") or ""
                    cfg["MODEL"] = ai_cfg.get("MODEL") or cfg["MODEL"]
                    cfg["API_BASE"] = ai_cfg.get("API_BASE", "") or cfg["API_BASE"]
                except Exception:
                    pass
            if not cfg["API_KEY"]:
                return None
            self._llm = AIClient(cfg)
            return self._llm
        except Exception:
            return None

    # ────────────── 归一化条目 ──────────────

    @staticmethod
    def _norm_local_news(item: Dict) -> Dict:
        return {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "source": "news:" + (item.get("platform") or item.get("source") or ""),
            "author": "",
            "engagement": int(item.get("count", 0) or 0),
            "extra": {"ranks": item.get("ranks", [])},
        }

    @staticmethod
    def _norm_hn(item: Dict) -> Dict:
        score = int(item.get("score") or item.get("points") or 0)
        comments = int(item.get("comments") or item.get("num_comments") or 0)
        return {
            "title": item.get("title") or "",
            "url": item.get("url") or item.get("hn_url") or "",
            "source": "hn",
            "author": item.get("by") or item.get("author") or "",
            "engagement": score + comments,
            "extra": {"score": score, "comments": comments},
        }

    @staticmethod
    def _norm_reddit(item: Dict) -> Dict:
        return {
            "title": item.get("title") or "",
            "url": item.get("permalink") or item.get("url") or "",
            "source": "reddit:r/" + (item.get("subreddit") or ""),
            "author": item.get("author") or "",
            "engagement": int(item.get("score", 0) or 0) + int(item.get("num_comments", 0) or 0),
            "extra": {"score": item.get("score"), "comments": item.get("num_comments")},
        }

    @staticmethod
    def _norm_xhs(item: Dict) -> Dict:
        # xhs CLI 返回结构: {id, title, desc, user:{nickname}, interact_info:{liked_count, comment_count, share_count}, url}
        interact = item.get("interact_info") or {}
        user = item.get("user") or {}
        likes = int(interact.get("liked_count") or 0)
        comments = int(interact.get("comment_count") or 0)
        shares = int(interact.get("share_count") or 0)
        return {
            "title": item.get("title") or item.get("display_title") or item.get("desc", "")[:80],
            "url": item.get("url") or item.get("share_url") or "",
            "source": "xhs",
            "author": user.get("nickname") or user.get("nick_name") or user.get("name") or "",
            "engagement": likes + comments + shares,
            "extra": {"liked": likes, "comments": comments, "shares": shares},
        }

    @staticmethod
    def _norm_bili(item: Dict) -> Dict:
        # bili CLI search 返回: {title, author, bvid, play, danmaku, arcurl}
        plays = int(item.get("play") or item.get("view") or 0)
        danmaku = int(item.get("danmaku") or 0)
        return {
            "title": item.get("title") or "",
            "url": item.get("arcurl") or item.get("url") or (
                f"https://www.bilibili.com/video/{item.get('bvid')}" if item.get("bvid") else ""
            ),
            "source": "bili",
            "author": item.get("author") or item.get("owner", {}).get("name", "") if isinstance(item.get("owner"), dict) else item.get("author", ""),
            "engagement": plays + danmaku,
            "extra": {"play": plays, "danmaku": danmaku},
        }

    @staticmethod
    def _norm_twitter(item: Dict) -> Dict:
        # twitter CLI tweet 结构: {text, user:{username}, url, metrics:{like_count, retweet_count, reply_count}}
        metrics = item.get("metrics") or item.get("public_metrics") or {}
        user = item.get("user") or {}
        return {
            "title": (item.get("text") or "").split("\n")[0][:200],
            "url": item.get("url") or "",
            "source": "twitter",
            "author": user.get("username") or item.get("author") or "",
            "engagement": int(metrics.get("like_count", 0) or 0)
                           + int(metrics.get("retweet_count", 0) or 0)
                           + int(metrics.get("reply_count", 0) or 0),
            "extra": metrics,
        }

    # ────────────── 并发拉取一个 source ──────────────

    def _fetch_source(self, source: str, query: str, limit: int) -> Dict[str, Any]:
        """返回 {source, items: [norm_item], error?}"""
        try:
            if source == "news":
                if not self._search:
                    return {"source": source, "items": [], "error": "search_tools 未注入"}
                res = self._search.search_news_unified(query=query, limit=limit)
                error_code, error_message = _response_error(res, "本地新闻搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                hot = (res.get("data") or {}).get("hot_list") if isinstance(res, dict) else None
                if not hot and isinstance(res, dict):
                    hot = res.get("hot_list") or res.get("results") or []
                items = [self._norm_local_news(it) for it in (hot or [])[:limit]]
                return {"source": source, "items": items}

            if source == "hn":
                if not self._ext:
                    return {"source": source, "items": [], "error": "external_apis 未注入"}
                if hasattr(self._ext, "search_hackernews"):
                    res = self._ext.search_hackernews(query=query, hits=limit)
                    stories = (res.get("data") or {}).get("hits") if isinstance(res, dict) else []
                    transport = "algolia_search"
                else:
                    res = self._ext.get_hackernews_top(limit=limit * 3)
                    top_stories = (res.get("data") or {}).get("stories") if isinstance(res, dict) else []
                    query_text = query.lower()
                    stories = [
                        story
                        for story in (top_stories or [])
                        if query_text in (story.get("title") or "").lower()
                    ]
                    transport = "firebase_top_filter"
                error_code, error_message = _response_error(res, "Hacker News 搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                        "meta": {"transport": transport},
                    }
                items = [self._norm_hn(story) for story in (stories or [])[:limit]]
                return {"source": source, "items": items, "meta": {"transport": transport}}

            if source == "reddit":
                try:
                    response = requests.get(
                        "https://www.reddit.com/search.rss",
                        params={"q": query, "limit": max(1, min(limit, 50)), "sort": "hot"},
                        headers={"User-Agent": "Argus/6.6 research client"},
                        timeout=15,
                    )
                    rate_limit = _rate_limit_metadata(response.headers)
                    metadata = {"transport": "reddit_atom", "rate_limit": rate_limit}
                    if response.status_code == 429:
                        return {
                            "source": source,
                            "items": [],
                            "error": "Reddit Atom 搜索触发限流",
                            "error_code": "RATE_LIMITED",
                            "meta": metadata,
                        }
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                    entries = list(getattr(feed, "entries", []) or [])
                    if getattr(feed, "bozo", False) and not entries:
                        return {
                            "source": source,
                            "items": [],
                            "error": "Reddit Atom 响应无法解析",
                            "error_code": "PARSE_ERROR",
                            "meta": metadata,
                        }
                    posts = []
                    for entry in entries[:limit]:
                        link = entry.get("link") or ""
                        posts.append({
                            "title": entry.get("title"),
                            "permalink": link,
                            "url": link,
                            "subreddit": _reddit_subreddit_from_url(link),
                            "score": 0,
                            "num_comments": 0,
                            "author": entry.get("author"),
                        })
                    items = [self._norm_reddit(post) for post in posts]
                    return {"source": source, "items": items, "meta": metadata}
                except requests.exceptions.RequestException as ex:
                    return {
                        "source": source,
                        "items": [],
                        "error": f"Reddit Atom 请求失败: {ex}",
                        "error_code": "NETWORK_ERROR",
                        "meta": {"transport": "reddit_atom"},
                    }
                except Exception as ex:
                    return {
                        "source": source,
                        "items": [],
                        "error": f"Reddit Atom 搜索失败: {ex}",
                        "error_code": "SOURCE_ERROR",
                        "meta": {"transport": "reddit_atom"},
                    }

            if source == "xhs":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_xhs("search", [query], timeout=60)
                error_code, error_message = _response_error(res, "小红书搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                data = res.get("data") or {}
                raw_list = (data.get("notes") or data.get("items") or data.get("results")
                            or data.get("list") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_xhs(it) for it in raw_list[:limit]]
                return {"source": source, "items": items}

            if source == "bili":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_bilibili("search", [query, "-n", str(limit)], timeout=60)
                error_code, error_message = _response_error(res, "Bilibili 搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                data = res.get("data") or {}
                raw_list = (data.get("results") or data.get("videos") or data.get("items")
                            or data.get("list") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_bili(it) for it in raw_list[:limit]]
                return {"source": source, "items": items}

            if source == "twitter":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_twitter("search", [query, "-n", str(limit)], timeout=60)
                error_code, error_message = _response_error(res, "Twitter 搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                data = res.get("data") or {}
                raw_list = (data.get("tweets") or data.get("results") or data.get("items") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_twitter(it) for it in raw_list[:limit]]
                return {"source": source, "items": items}

            if source == "tg":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_telegram("search", [query], timeout=60)
                error_code, error_message = _response_error(res, "Telegram 搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                data = res.get("data") or {}
                raw_list = (data.get("messages") or data.get("results") or data.get("items") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = []
                for it in raw_list[:limit]:
                    items.append({
                        "title": (it.get("text") or it.get("content") or "")[:200],
                        "url": it.get("link") or "",
                        "source": "tg:" + (it.get("chat") or it.get("channel") or ""),
                        "author": it.get("sender") or "",
                        "engagement": int(it.get("views", 0) or 0),
                        "extra": {},
                    })
                return {"source": source, "items": items}

            if source == "discord":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_discord("search", [query], timeout=60)
                error_code, error_message = _response_error(res, "Discord 搜索失败")
                if error_message:
                    return {
                        "source": source,
                        "items": [],
                        "error": error_message,
                        "error_code": error_code,
                    }
                data = res.get("data") or {}
                raw_list = (data.get("messages") or data.get("results") or data.get("items") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = []
                for it in raw_list[:limit]:
                    items.append({
                        "title": (it.get("content") or it.get("text") or "")[:200],
                        "url": it.get("link") or "",
                        "source": "discord:" + (it.get("channel") or ""),
                        "author": it.get("author") or "",
                        "engagement": 0,
                        "extra": {},
                    })
                return {"source": source, "items": items}

            return {"source": source, "items": [], "error": f"未知 source: {source}"}
        except Exception as ex:
            return {"source": source, "items": [], "error": f"{type(ex).__name__}: {ex}"}

    # ────────────── Batch 4b: universal_search ──────────────

    def universal_search(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 10,
    ) -> Dict:
        """并发路由到多 source, 统一归一化返回

        Args:
            query: 查询关键词
            sources: 平台列表, 默认 ["news","hn","reddit","xhs","bili"]
            limit: 每源返回条数
        Returns:
            {
              sources: {src: {count, items, error?}},
              merged: [norm_item...]   # 按 engagement 排序后的平铺列表
            }
        """
        if not query or not query.strip():
            return _err("query 不能为空", code="INVALID_PARAM")

        default_sources = ["news", "hn", "reddit", "xhs", "bili"]
        sources = sources or default_sources
        # 过滤非法 source
        valid = {"news", "hn", "reddit", "xhs", "bili", "twitter", "tg", "discord"}
        sources = [s for s in sources if s in valid]
        if not sources:
            return _err("sources 列表无有效 source", code="INVALID_PARAM")

        per_limit = max(1, min(int(limit), 50))

        results: Dict[str, Any] = {}
        with cf.ThreadPoolExecutor(max_workers=min(8, len(sources))) as ex:
            futures = {ex.submit(self._fetch_source, s, query, per_limit): s for s in sources}
            for fut in cf.as_completed(futures):
                s = futures[fut]
                try:
                    results[s] = fut.result()
                except Exception as e:
                    results[s] = {"source": s, "items": [], "error": str(e)}

        # 归一结果 + 平铺排序
        merged: List[Dict] = []
        sources_out: Dict[str, Any] = {}
        for s in sources:
            r = results.get(s) or {"items": []}
            items = r.get("items") or []
            error = r.get("error")
            if error and items:
                source_status = "partial"
            elif error:
                source_status = "failed"
            elif items:
                source_status = "ready"
            else:
                source_status = "empty"
            sources_out[s] = {
                "label": _PLATFORM_LABEL.get(s, s),
                "status": source_status,
                "count": len(items),
                "items": items,
                "error": error,
                "error_code": r.get("error_code"),
                "meta": r.get("meta") or {},
            }
            merged.extend(items)

        merged.sort(key=lambda x: x.get("engagement", 0), reverse=True)
        failed_sources = sum(1 for info in sources_out.values() if info["status"] == "failed")
        degraded_sources = sum(1 for info in sources_out.values() if info["status"] == "partial")
        empty_sources = sum(1 for info in sources_out.values() if info["status"] == "empty")
        if not merged:
            status = "failed" if failed_sources == len(sources) else "empty"
        elif failed_sources or degraded_sources:
            status = "partial"
        else:
            status = "complete"
        response_data = {
            "query": query,
            "status": status,
            "sources": sources_out,
            "merged": merged[:200],
        }
        summary = {
            "status": status,
            "sources": len(sources),
            "total_items": len(merged),
            "failed_sources": failed_sources,
            "degraded_sources": degraded_sources,
            "empty_sources": empty_sources,
        }
        if not merged:
            error_code = "ALL_SOURCES_FAILED" if status == "failed" else "NO_RESULTS"
            error_message = (
                "所有请求的数据源均失败"
                if status == "failed"
                else "数据源请求完成但没有匹配结果"
            )
            return {
                "success": False,
                "error": {"code": error_code, "message": error_message},
                "summary": summary,
                "data": response_data,
            }
        return _ok(response_data, **summary)

    # ────────────── Batch 4a: narrative_tracking ──────────────

    def narrative_tracking(
        self,
        topic: str,
        platforms: Optional[List[str]] = None,
        limit_per_platform: int = 15,
        use_llm: bool = True,
    ) -> Dict:
        """对同一话题, 对比各平台的情感/报道量/代表标题

        Args:
            topic: 话题关键词
            platforms: 默认 ["news","hn","reddit","xhs","bili"]
            limit_per_platform: 每个平台拉多少条
            use_llm: 是否用 LLM 打分 (无 key 则自动降级为规则打分)

        Returns:
            {
              topic, platforms_compared,
              by_platform: {p: {volume, mean_sentiment, pos_ratio, neg_ratio, top_titles, top_outlets, sample}},
              ranking: {most_positive, most_negative, highest_volume},
              method: "llm" | "rule"
            }
        """
        if not topic or not topic.strip():
            return _err("topic 不能为空", code="INVALID_PARAM")

        platforms = platforms or ["news", "hn", "reddit", "xhs", "bili"]

        # 先复用 universal_search 拉条目
        us = self.universal_search(topic, sources=platforms, limit=limit_per_platform)
        if not us.get("success"):
            return us

        by_source = us["data"]["sources"]

        # 情感打分
        llm = self._get_llm() if use_llm else None
        method = "llm" if llm else "rule"

        by_platform: Dict[str, Dict[str, Any]] = {}
        for p, info in by_source.items():
            items = info["items"]
            if not items:
                by_platform[p] = {
                    "label": info.get("label", p),
                    "volume": 0,
                    "mean_sentiment": None,
                    "pos_ratio": None,
                    "neg_ratio": None,
                    "top_titles": [],
                    "top_outlets": [],
                    "sample": [],
                    "error": info.get("error"),
                }
                continue

            # 打分
            if llm:
                scores = self._llm_score_batch(llm, topic, [it["title"] for it in items])
            else:
                scores = [_rule_sentiment(it["title"]) for it in items]

            pos = sum(1 for s in scores if s > 0.15)
            neg = sum(1 for s in scores if s < -0.15)
            n = len(scores) or 1

            top_sorted = sorted(items, key=lambda x: x.get("engagement", 0), reverse=True)
            outlets = Counter(it.get("source", "") for it in items if it.get("source"))

            by_platform[p] = {
                "label": info.get("label", p),
                "volume": len(items),
                "mean_sentiment": round(sum(scores) / n, 3),
                "pos_ratio": round(pos / n, 3),
                "neg_ratio": round(neg / n, 3),
                "top_titles": [t["title"] for t in top_sorted[:5]],
                "top_outlets": [{"source": s, "count": c} for s, c in outlets.most_common(5)],
                "sample": top_sorted[:3],
                "error": info.get("error"),
            }

        # 排名
        scored = [(p, v) for p, v in by_platform.items() if v.get("mean_sentiment") is not None]
        ranking = {}
        if scored:
            ranking["most_positive"] = max(scored, key=lambda kv: kv[1]["mean_sentiment"])[0]
            ranking["most_negative"] = min(scored, key=lambda kv: kv[1]["mean_sentiment"])[0]
            ranking["highest_volume"] = max(by_platform.items(), key=lambda kv: kv[1]["volume"])[0]

        return _ok(
            {
                "topic": topic,
                "method": method,
                "status": us["summary"]["status"],
                "platforms_compared": list(by_platform.keys()),
                "by_platform": by_platform,
                "ranking": ranking,
            },
            status=us["summary"]["status"],
            platforms=len(by_platform),
            method=method,
            failed_sources=us["summary"]["failed_sources"],
            degraded_sources=us["summary"]["degraded_sources"],
            empty_sources=us["summary"]["empty_sources"],
        )

    # ────────────── LLM 批量打分 ──────────────

    def _llm_score_batch(self, llm, topic: str, titles: List[str]) -> List[float]:
        """一次 LLM 调用给多条标题打情感分 [-1, 1]"""
        if not titles:
            return []
        numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(titles))
        system = (
            "你是舆情分析专家。对每条标题相对于给定话题的情感打分。"
            "输出 JSON 数组, 不要 markdown 代码块, 不要解释。"
        )
        user = f"""话题: {topic}

规则:
- 每条打分 [-1, 1]: +1=强正面, 0=中性, -1=强负面
- 严格输出 JSON 数组, 长度 = {len(titles)}, 元素为 number
- 示例: [0.6, -0.3, 0.0, 0.8]

标题:
{numbered}

输出 JSON:"""
        try:
            resp = llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception:
            return [_rule_sentiment(t) for t in titles]

        parsed = self._parse_num_array(resp, len(titles))
        if parsed is None:
            return [_rule_sentiment(t) for t in titles]
        return parsed

    @staticmethod
    def _parse_num_array(text: str, expected_len: int) -> Optional[List[float]]:
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        l = cleaned.find("[")
        r = cleaned.rfind("]")
        if l < 0 or r < l:
            return None
        try:
            arr = json.loads(cleaned[l:r + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(arr, list):
            return None
        out: List[float] = []
        for v in arr:
            try:
                out.append(max(-1.0, min(1.0, float(v))))
            except (TypeError, ValueError):
                out.append(0.0)
        # 对齐长度
        if len(out) < expected_len:
            out.extend([0.0] * (expected_len - len(out)))
        return out[:expected_len]
