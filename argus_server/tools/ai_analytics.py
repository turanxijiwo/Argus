"""
AI 增强分析 - Batch 3 交付

1. semantic_deduplicate: 用 LLM 对新闻做语义去重聚类 (升级原 aggregate_news 的字符串相似度)
2. detect_anomaly: 时序异常检测 (话题突发/衰退预警)
3. combined: 语义去重 + 异常检测组合工具

依赖:
  - argus.ai.AIClient (摘要/分类)
  - argus.storage 查询历史数据
  - numpy / statistics (时序分析)
"""

from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "ANALYSIS_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


class AIAnalyticsTools:
    """AI 增强分析 (语义去重 + 异常检测)"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
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
                "TEMPERATURE": 0.1,   # 语义聚类要稳定
                "MAX_TOKENS": 4000,
                "TIMEOUT": 90,
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

    # ────────────── 功能一: 语义去重 ──────────────

    def semantic_deduplicate(
        self,
        news_items: List[Dict],
        group_threshold: str = "same_event",
        include_summary: bool = True,
        target_language: str = "zh-CN",
    ) -> Dict:
        """用 LLM 对新闻列表做语义聚类去重

        与 aggregate_news 的区别:
          - aggregate_news: 基于标题字符串相似度 (0.7 阈值)
          - semantic_deduplicate: 基于 LLM 理解的语义 (同一事件/话题)

        Args:
            news_items: [{title, platform?, url?, ...}, ...]
            group_threshold:
              - "same_event"  — 同一具体事件才合并 (严格)
              - "same_topic"  — 同一主题就合并 (宽松)
              - "same_entity" — 涉及同一人物/公司/产品就合并 (最宽松)
            include_summary: 每个聚类生成一句话摘要
            target_language: 输出语种

        Returns:
            {
              clusters: [
                {
                  cluster_id,
                  representative_title,
                  summary,              # 可选
                  platforms: [...],
                  items: [原始 index 列表],
                  size
                }
              ],
              unique_count,
              compression_ratio
            }
        """
        if not news_items:
            return _err("news_items 为空", code="INVALID_PARAM")
        if self._get_llm() is None:
            return _err(
                "未配置 AI 模型 (AI_API_KEY)。语义去重依赖 LLM。"
                "可退回 aggregate_news 使用字符串相似度。",
                code="AUTH_REQUIRED",
            )

        # 截断到合理数量 (避免 prompt 过大)
        items = news_items[:80]

        # 构造 prompt
        lines = []
        for i, it in enumerate(items):
            title = (it.get("title") or "").strip()
            plat = it.get("platform") or it.get("source") or ""
            lines.append(f"[{i}] {title}" + (f" @{plat}" if plat else ""))
        compiled = "\n".join(lines)

        threshold_hint = {
            "same_event": "必须是同一具体事件才能归为一组 (如两篇报道同一次会议)",
            "same_topic": "同一主题即可归为一组 (如都讨论 AI 监管政策即可)",
            "same_entity": "涉及同一人物/公司/产品即可归为一组",
        }.get(group_threshold, "同一具体事件")

        summary_hint = "- 为每组生成一句不超过 30 字的中文摘要" if include_summary else ""

        system = (
            "你是专业新闻编辑。你的任务是把语义重复的新闻归到同一组。"
            f"严格用 JSON 数组输出, 不要 markdown code block, 不要解释。"
        )
        user = f"""下面有 {len(items)} 条新闻, 请按"{threshold_hint}"的规则分组。
输出 JSON 数组, 每个元素格式:
{{
  "cluster_id": 1,
  "representative_title": "该组最代表性的标题",
  "summary": "可选, 1 句话摘要",
  "member_indices": [0, 3, 7]
}}

要求:
- 所有 {len(items)} 个 index (0~{len(items)-1}) 必须出现且只出现一次
- 单篇不重复的新闻也是一组 (member_indices 长度 1)
{summary_hint}
- 用 {target_language} 输出 representative_title 和 summary

新闻列表:
{compiled}

输出 JSON:"""

        try:
            resp = self._llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception as ex:
            return _err(f"LLM 调用失败: {ex}", code="UPSTREAM_ERROR")

        # 解析 JSON
        clusters_raw = self._parse_json_array(resp)
        if clusters_raw is None:
            return _err(
                "LLM 输出不是有效 JSON, 请重试或换更强的模型",
                code="PARSE_ERROR",
                preview=resp[:300],
            )

        # 校验 + 补全
        used = set()
        clusters = []
        for c in clusters_raw:
            idx_list = c.get("member_indices", []) or []
            # 过滤有效 index
            valid = [i for i in idx_list if isinstance(i, int) and 0 <= i < len(items) and i not in used]
            if not valid:
                continue
            used.update(valid)
            platforms = list({
                items[i].get("platform") or items[i].get("source") or "unknown"
                for i in valid
            })
            clusters.append({
                "cluster_id": c.get("cluster_id", len(clusters) + 1),
                "representative_title": c.get("representative_title", ""),
                "summary": c.get("summary") if include_summary else None,
                "platforms": platforms,
                "item_indices": valid,
                "size": len(valid),
            })
        # 补漏 (LLM 可能漏分 index)
        missing = [i for i in range(len(items)) if i not in used]
        for i in missing:
            clusters.append({
                "cluster_id": len(clusters) + 1,
                "representative_title": items[i].get("title", ""),
                "summary": None,
                "platforms": [items[i].get("platform") or items[i].get("source") or "unknown"],
                "item_indices": [i],
                "size": 1,
            })

        compression = 1 - (len(clusters) / len(items)) if items else 0
        return _ok(
            {
                "clusters": clusters,
                "group_threshold": group_threshold,
                "language": target_language,
            },
            total_input=len(news_items),
            processed=len(items),
            unique_count=len(clusters),
            compression_ratio=round(compression, 3),
        )

    def _parse_json_array(self, text: str) -> Optional[List]:
        """尽力解析 LLM 输出的 JSON 数组"""
        if not text:
            return None
        # 去除可能的 code fence
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # 去掉 ```json 和 ```
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        # 定位 [ ... ]
        l = cleaned.find("[")
        r = cleaned.rfind("]")
        if l < 0 or r < l:
            return None
        try:
            return json.loads(cleaned[l:r+1])
        except json.JSONDecodeError:
            try:
                # 尝试用 json-repair
                from json_repair import loads as jr_loads
                return jr_loads(cleaned[l:r+1])
            except Exception:
                return None

    # ────────────── 功能二: 时序异常检测 ──────────────

    def detect_anomaly(
        self,
        topic: Optional[str] = None,
        lookback_days: int = 14,
        z_threshold: float = 2.0,
        min_frequency: int = 3,
        top_n: int = 20,
    ) -> Dict:
        """时序异常检测 - 发现突发增长或急剧衰退的话题

        方法:
            1. 从 Argus 本地存储拉过去 N 天的每日关键词统计
            2. 对每个关键词算 (最近一天频次 - 历史均值) / 历史标准差
            3. |z| >= threshold 的标为异常 (z>0=爆发, z<0=衰退)

        Args:
            topic: 限定关键词 (不填则扫全部)
            lookback_days: 回溯天数, 默认 14
            z_threshold: z 值阈值, 默认 2.0 (约 95% 置信区间外)
            min_frequency: 最小基础频次 (过滤噪声)
            top_n: 返回 TOP N

        Returns:
            {
              anomalies: [
                {keyword, z_score, latest_count, baseline_mean, baseline_std, trend}
              ],
              window: "14 days"
            }
        """
        try:
            from argus.storage import get_storage_manager
        except Exception as ex:
            return _err(f"无法导入 Argus storage: {ex}", code="INTERNAL_ERROR")

        try:
            sm = get_storage_manager()
        except Exception as ex:
            return _err(f"无法创建 storage manager: {ex}", code="INTERNAL_ERROR")

        # 0. 先拿本地所有可用日期, 取最近 lookback_days 天 (而非强依赖"今天")
        try:
            backend = sm.get_backend()
            available = backend.list_available_dates() if hasattr(backend, "list_available_dates") else []
        except Exception:
            available = []
        # 兜底: 扫 output/news/*.db
        if not available:
            try:
                from pathlib import Path
                p = Path(self.project_root or ".") / "output" / "news"
                if not p.exists():
                    p = Path("output") / "news"
                available = sorted([f.stem for f in p.glob("*.db")], reverse=True)
            except Exception:
                available = []
        if not available:
            return _err(
                "本地无历史新闻数据。请先运行 trigger_crawl 或 sync_from_remote 累积数据。",
                code="NO_LOCAL_DATA",
            )
        target_dates = sorted(available, reverse=True)[:lookback_days]

        # 1. 拉历史数据
        daily_stats: Dict[str, Counter] = {}
        for ds in target_dates:
            try:
                news_data = sm.get_today_all_data(ds)
            except Exception:
                continue
            if not news_data:
                continue
            # NewsData 是 dataclass, 字段 .items 是 {platform_id: [NewsItem]}
            platform_dict = getattr(news_data, "items", None) or (
                news_data if isinstance(news_data, dict) else {}
            )
            counter: Counter = Counter()
            for platform_id, items in (platform_dict.items() if isinstance(platform_dict, dict) else []):
                for item in items or []:
                    # item 可能是 dict 或 NewsItem dataclass
                    title = ""
                    if hasattr(item, "title"):
                        title = (item.title or "").strip()
                    elif isinstance(item, dict):
                        title = (item.get("title") or "").strip()
                    if not title:
                        continue
                    # 简易分词
                    tokens = [t.strip() for t in
                              title.replace("、", " ").replace(",", " ")
                              .replace(":", " ").replace("/", " ").split()]
                    for tok in tokens:
                        if len(tok) < 2:
                            continue
                        if topic and topic.lower() not in tok.lower():
                            continue
                        counter[tok] += 1
            if counter:
                daily_stats[ds] = counter

        if len(daily_stats) < 3:
            return _err(
                f"历史数据不足 (仅找到 {len(daily_stats)} 天), 需要至少 3 天。"
                f"可以先用 trigger_crawl 或 sync_from_remote 累积数据。",
                code="INSUFFICIENT_DATA",
                available_days=len(daily_stats),
            )

        # 2. 计算 z-score (最近一天 vs 之前的历史均值和标准差)
        sorted_dates = sorted(daily_stats.keys(), reverse=True)
        latest_date = sorted_dates[0]
        history_dates = sorted_dates[1:]

        # 收集所有出现过的 keyword
        all_keywords = set()
        for c in daily_stats.values():
            all_keywords.update(c.keys())

        anomalies = []
        for kw in all_keywords:
            latest_count = daily_stats[latest_date].get(kw, 0)
            if latest_count < min_frequency:
                continue
            history_counts = [daily_stats[d].get(kw, 0) for d in history_dates]
            if len(history_counts) < 2:
                continue
            try:
                mean = statistics.mean(history_counts)
                stdev = statistics.stdev(history_counts) if len(history_counts) > 1 else 0
            except Exception:
                continue
            if stdev == 0:
                # 历史全为 0 但今日突然有 → 视为新现象
                if latest_count >= min_frequency and mean == 0:
                    z = float("inf")
                    trend = "new_emergence"
                else:
                    continue
            else:
                z = (latest_count - mean) / stdev
                trend = "spike" if z > 0 else "decline"

            if abs(z) >= z_threshold:
                anomalies.append({
                    "keyword": kw,
                    "z_score": round(z, 2) if z != float("inf") else "inf",
                    "latest_count": latest_count,
                    "baseline_mean": round(mean, 2),
                    "baseline_std": round(stdev, 2),
                    "trend": trend,
                    "history_counts": history_counts[-7:],
                })

        # 按 |z| 排序
        anomalies.sort(
            key=lambda x: abs(x["z_score"]) if isinstance(x["z_score"], (int, float)) else 999,
            reverse=True,
        )
        anomalies = anomalies[:top_n]

        return _ok(
            {
                "anomalies": anomalies,
                "latest_date": latest_date,
                "history_window_days": len(history_dates),
                "z_threshold": z_threshold,
            },
            total_anomalies=len(anomalies),
            total_keywords_scanned=len(all_keywords),
        )

    # ────────────── 功能三: 组合 - 先去重再查异常 ──────────────

    def analyze_with_ai(
        self,
        news_items: Optional[List[Dict]] = None,
        topic: Optional[str] = None,
        mode: str = "full",
    ) -> Dict:
        """组合工具: 一次 API 调用同时做语义去重 + 异常检测

        mode:
            full      — 两样都做 (默认)
            dedup     — 只语义去重 (需 news_items)
            anomaly   — 只异常检测 (可选 topic 过滤)
        """
        out = {"mode": mode}
        if mode in ("full", "dedup"):
            if not news_items:
                out["dedup"] = _err("news_items 为空", code="INVALID_PARAM")
            else:
                out["dedup"] = self.semantic_deduplicate(news_items)
        if mode in ("full", "anomaly"):
            out["anomaly"] = self.detect_anomaly(topic=topic)
        return _ok(out, mode=mode)
