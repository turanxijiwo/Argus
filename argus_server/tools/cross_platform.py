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


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "CROSS_PLATFORM_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


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
        return {
            "title": item.get("title") or "",
            "url": item.get("url") or item.get("hn_url") or "",
            "source": "hn",
            "author": item.get("by") or "",
            "engagement": int(item.get("score", 0) or 0) + int(item.get("comments", 0) or 0),
            "extra": {"score": item.get("score"), "comments": item.get("comments")},
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
                hot = (res.get("data") or {}).get("hot_list") if isinstance(res, dict) else None
                if not hot and isinstance(res, dict):
                    hot = res.get("hot_list") or res.get("results") or []
                items = [self._norm_local_news(it) for it in (hot or [])[:limit]]
                return {"source": source, "items": items}

            if source == "hn":
                if not self._ext:
                    return {"source": source, "items": [], "error": "external_apis 未注入"}
                res = self._ext.search_hackernews(query=query, limit=limit) if hasattr(self._ext, "search_hackernews") else None
                if res is None:
                    # 退化: 抓 top 然后本地过滤
                    res = self._ext.get_hackernews_top(limit=limit * 3)
                stories = ((res.get("data") or {}).get("stories")
                           or (res.get("data") or {}).get("hits")
                           or [])
                q = query.lower()
                filtered = [s for s in stories if q in (s.get("title") or "").lower()]
                if not filtered:
                    filtered = stories[:limit]
                items = [self._norm_hn(s) for s in filtered[:limit]]
                return {"source": source, "items": items}

            if source == "reddit":
                if not self._ext:
                    return {"source": source, "items": [], "error": "external_apis 未注入"}
                # 用 /r/all/search.json 或退化到 /r/all
                try:
                    import requests
                    r = requests.get(
                        "https://www.reddit.com/search.json",
                        params={"q": query, "limit": max(1, min(limit, 50)), "sort": "hot"},
                        headers={"User-Agent": "ArgusBot/1.0"},
                        timeout=15,
                    )
                    children = r.json().get("data", {}).get("children", [])
                    posts = [c.get("data", {}) for c in children]
                    # 补齐 reddit dict 结构
                    normalized = []
                    for p in posts:
                        normalized.append({
                            "title": p.get("title"),
                            "permalink": f"https://reddit.com{p.get('permalink', '')}",
                            "url": p.get("url"),
                            "subreddit": p.get("subreddit"),
                            "score": p.get("score"),
                            "num_comments": p.get("num_comments"),
                            "author": p.get("author"),
                        })
                    items = [self._norm_reddit(p) for p in normalized[:limit]]
                    return {"source": source, "items": items}
                except Exception as ex:
                    return {"source": source, "items": [], "error": f"reddit 搜索失败: {ex}"}

            if source == "xhs":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_xhs("search", [query, "--limit", str(limit)], timeout=60)
                data = res.get("data") or {}
                raw_list = (data.get("notes") or data.get("items") or data.get("results")
                            or data.get("list") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_xhs(it) for it in raw_list[:limit]]
                return {"source": source, "items": items, "error": res.get("error", {}).get("message") if not res.get("success") else None}

            if source == "bili":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_bilibili("search", [query, "--limit", str(limit)], timeout=60)
                data = res.get("data") or {}
                raw_list = (data.get("results") or data.get("videos") or data.get("items")
                            or data.get("list") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_bili(it) for it in raw_list[:limit]]
                return {"source": source, "items": items, "error": res.get("error", {}).get("message") if not res.get("success") else None}

            if source == "twitter":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_twitter("search", [query, "--limit", str(limit)], timeout=60)
                data = res.get("data") or {}
                raw_list = (data.get("tweets") or data.get("results") or data.get("items") or [])
                if not isinstance(raw_list, list):
                    raw_list = []
                items = [self._norm_twitter(it) for it in raw_list[:limit]]
                return {"source": source, "items": items, "error": res.get("error", {}).get("message") if not res.get("success") else None}

            if source == "tg":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_telegram("search", [query, "--limit", str(limit)], timeout=60)
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
                return {"source": source, "items": items, "error": res.get("error", {}).get("message") if not res.get("success") else None}

            if source == "discord":
                if not self._cli:
                    return {"source": source, "items": [], "error": "cli 未注入"}
                res = self._cli.run_discord("search", [query, "--limit", str(limit)], timeout=60)
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
                return {"source": source, "items": items, "error": res.get("error", {}).get("message") if not res.get("success") else None}

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
            sources_out[s] = {
                "label": _PLATFORM_LABEL.get(s, s),
                "count": len(items),
                "items": items,
                "error": r.get("error"),
            }
            merged.extend(items)

        merged.sort(key=lambda x: x.get("engagement", 0), reverse=True)

        return _ok(
            {
                "query": query,
                "sources": sources_out,
                "merged": merged[:200],
            },
            sources=len(sources),
            total_items=len(merged),
        )

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
                "platforms_compared": list(by_platform.keys()),
                "by_platform": by_platform,
                "ranking": ranking,
            },
            platforms=len(platforms),
            method=method,
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
