"""
导出到 Obsidian / 本地 Markdown - Batch 10 交付

把每日/任意时间段的新闻 + 异常 + 趋势词导出为 markdown 文件, 落到指定目录,
适合当 Obsidian vault 的每日笔记。

特性:
    - YAML frontmatter (可被 Obsidian Dataview 查询)
    - 双链格式 [[话题]] / [[平台:B站]]
    - 按日期文件名 YYYY-MM-DD.md (Obsidian daily notes)
    - 支持 append 模式 (当天已存在就追加 section)

工具:
    export_daily_brief(date?, output_dir?, vault_style?)
    export_query_report(query, output_path?, window_days?)
    export_anomalies(output_path?, lookback_days?)
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "EXPORT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _default_vault() -> Path:
    """优先环境变量, 回退到 ~/Desktop/Argus-Vault"""
    env = os.environ.get("ARGUS_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "Desktop" / "Argus-Vault").resolve()


def _slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[\\/:*?\"<>|#\[\]]+", "-", (s or "").strip())
    return s[:max_len] or "untitled"


class ExporterTools:
    """Markdown / Obsidian 导出"""

    def __init__(self, project_root: Optional[str] = None,
                 storage_adapter=None,
                 ai_analytics_adapter=None,
                 semantic_adapter=None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self._storage = storage_adapter
        self._analytics = ai_analytics_adapter
        self._semantic = semantic_adapter

    # ────────────── 内部 helper ──────────────

    def _load_day(self, ds: str) -> Dict[str, Any]:
        from argus.storage import get_storage_manager
        sm = get_storage_manager()
        data = sm.get_today_all_data(ds)
        platforms: Dict[str, List[Dict]] = {}
        total = 0
        if data is None:
            return {"date": ds, "total": 0, "platforms": {}}
        items_dict = getattr(data, "items", None) or {}
        id_to_name = getattr(data, "id_to_name", {}) or {}
        if isinstance(items_dict, dict):
            for pid, items in items_dict.items():
                name = id_to_name.get(pid, pid)
                rows = []
                for it in items or []:
                    title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
                    url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
                    ranks = getattr(it, "ranks", None) or (it.get("ranks") if isinstance(it, dict) else [])
                    if title:
                        rows.append({"title": title, "url": url, "ranks": ranks})
                if rows:
                    platforms[name] = rows
                    total += len(rows)
        return {"date": ds, "total": total, "platforms": platforms}

    @staticmethod
    def _top_keywords(day: Dict, top_n: int = 30) -> List[Dict]:
        import jieba
        counter: Counter = Counter()
        plats_of: Dict[str, set] = defaultdict(set)
        for plat, items in (day.get("platforms") or {}).items():
            for it in items:
                title = it.get("title") or ""
                for tok in jieba.cut_for_search(title):
                    t = tok.strip()
                    if len(t) < 2:
                        continue
                    if re.fullmatch(r"[\W_]+", t):
                        continue
                    counter[t] += 1
                    plats_of[t].add(plat)
        return [
            {"keyword": k, "count": c, "platforms": sorted(plats_of[k])}
            for k, c in counter.most_common(top_n)
        ]

    @staticmethod
    def _write_md(path: Path, content: str, append: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append and path.exists() else "w"
        with path.open(mode, encoding="utf-8") as f:
            if append and path.exists() and mode == "a":
                f.write("\n\n---\n\n")
            f.write(content)

    # ────────────── 公开工具 ──────────────

    def export_daily_brief(
        self,
        date: Optional[str] = None,
        output_dir: Optional[str] = None,
        vault_style: bool = True,
        top_keywords: int = 20,
        top_per_platform: int = 10,
        append: bool = False,
    ) -> Dict:
        """导出某日简报为 markdown

        Args:
            date: YYYY-MM-DD; 不传则用最近可用日期
            output_dir: 输出目录; 不传用 $ARGUS_VAULT 或 ~/Desktop/Argus-Vault
            vault_style: 是否用 Obsidian 双链 [[...]]
            top_keywords: 顶部趋势词 N
            top_per_platform: 每平台展示多少条
            append: 同日文件已存在时是否追加 (默认覆盖)
        """
        # 确定日期
        if not date:
            news_dir = self.project_root / "output" / "news"
            dates = sorted([f.stem for f in news_dir.glob("*.db")], reverse=True) if news_dir.exists() else []
            if not dates:
                return _err("无可用日期数据", code="NO_DATA")
            date = dates[0]

        day = self._load_day(date)
        if day["total"] == 0:
            return _err(f"{date} 无新闻数据", code="NO_DATA")

        # 趋势词
        keywords = self._top_keywords(day, top_n=top_keywords)

        # 渲染 markdown
        out_dir = Path(output_dir).expanduser() if output_dir else _default_vault()
        out_dir = out_dir.resolve()
        out_path = out_dir / "daily" / f"{date}.md"

        # frontmatter
        plat_count = len(day["platforms"])
        fm = [
            "---",
            f"date: {date}",
            f"type: argus-daily",
            f"total_items: {day['total']}",
            f"platforms: {plat_count}",
            f"tags: [argus, daily-brief]",
            "---",
            "",
            f"# 📰 {date} 热点简报",
            "",
            f"> 共 **{day['total']}** 条 / **{plat_count}** 个平台",
            "",
        ]

        # 趋势词区块
        fm.append("## 🔥 Top 趋势词")
        fm.append("")
        for k in keywords:
            link = f"[[{k['keyword']}]]" if vault_style else f"`{k['keyword']}`"
            plats = ", ".join(k["platforms"][:5])
            fm.append(f"- {link} × **{k['count']}** — {plats}")
        fm.append("")

        # 按平台分组
        fm.append("## 📡 按平台")
        fm.append("")
        # 按条数降序排平台
        sorted_plats = sorted(day["platforms"].items(), key=lambda x: len(x[1]), reverse=True)
        for plat, items in sorted_plats:
            plat_link = f"[[平台·{plat}]]" if vault_style else f"**{plat}**"
            fm.append(f"### {plat_link} ({len(items)})")
            fm.append("")
            for it in items[:top_per_platform]:
                title = it["title"]
                url = it.get("url", "")
                if url:
                    fm.append(f"- [{title}]({url})")
                else:
                    fm.append(f"- {title}")
            fm.append("")

        content = "\n".join(fm)
        self._write_md(out_path, content, append=append)

        return _ok(
            {
                "output_path": str(out_path),
                "date": date,
                "total_items": day["total"],
                "keywords_count": len(keywords),
            },
            bytes_written=len(content.encode("utf-8")),
        )

    def export_query_report(
        self,
        query: str,
        output_path: Optional[str] = None,
        window_days: int = 30,
        limit: int = 50,
    ) -> Dict:
        """把对 query 的 BM25 搜索结果导成 markdown 报告"""
        if not query or not query.strip():
            return _err("query 不能为空", code="INVALID_PARAM")
        if self._semantic is None:
            return _err("语义搜索引擎未接入", code="INTERNAL_ERROR")

        res = self._semantic.search(query, window_days=window_days, limit=limit)
        if not res.get("success"):
            return res
        results = (res.get("data") or {}).get("results") or []

        out_dir = _default_vault()
        fname = f"query-{_slug(query)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        out_path = Path(output_path).expanduser() if output_path else (out_dir / "queries" / fname)

        # 按日期分组
        by_date: Dict[str, List[Dict]] = defaultdict(list)
        for r in results:
            by_date[r["date"]].append(r)

        lines = [
            "---",
            f"query: \"{query}\"",
            f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
            f"window_days: {window_days}",
            f"matches: {len(results)}",
            f"tags: [argus, query-report]",
            "---",
            "",
            f"# 🔍 \"{query}\" 查询报告",
            "",
            f"> BM25 命中 **{len(results)}** 条 / 最近 **{window_days}** 天",
            "",
        ]

        for ds in sorted(by_date.keys(), reverse=True):
            items = sorted(by_date[ds], key=lambda x: x["score"], reverse=True)
            lines.append(f"## {ds} ({len(items)})")
            lines.append("")
            for it in items:
                badge = f"**{it['score']}** · {it['platform']}"
                if it.get("url"):
                    lines.append(f"- {badge} — [{it['title']}]({it['url']})")
                else:
                    lines.append(f"- {badge} — {it['title']}")
            lines.append("")

        content = "\n".join(lines)
        self._write_md(out_path, content)

        return _ok(
            {
                "output_path": str(out_path),
                "query": query,
                "matches": len(results),
                "days_covered": len(by_date),
            },
            bytes_written=len(content.encode("utf-8")),
        )

    def export_anomalies(
        self,
        output_path: Optional[str] = None,
        lookback_days: int = 14,
        z_threshold: float = 2.0,
    ) -> Dict:
        """把异常检测结果导为 markdown"""
        if self._analytics is None:
            return _err("analytics 未接入", code="INTERNAL_ERROR")

        res = self._analytics.detect_anomaly(
            lookback_days=lookback_days, z_threshold=z_threshold, top_n=30
        )
        if not res.get("success"):
            return res
        anomalies = (res.get("data") or {}).get("anomalies") or []

        out_dir = _default_vault()
        fname = f"anomaly-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        out_path = Path(output_path).expanduser() if output_path else (out_dir / "anomalies" / fname)

        lines = [
            "---",
            f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
            f"lookback_days: {lookback_days}",
            f"z_threshold: {z_threshold}",
            f"anomaly_count: {len(anomalies)}",
            f"tags: [argus, anomaly]",
            "---",
            "",
            "# ⚡ 异常话题报告",
            "",
            f"> {len(anomalies)} 个异常 · 回溯 {lookback_days} 天 · z 阈 {z_threshold}",
            "",
            "| 关键词 | z-score | 最新计数 | 基线均值 | 趋势 |",
            "|---|---|---|---|---|",
        ]
        for a in anomalies:
            lines.append(
                f"| [[{a['keyword']}]] | {a['z_score']} | {a['latest_count']} | "
                f"{a['baseline_mean']} | {a['trend']} |"
            )
        lines.append("")

        content = "\n".join(lines)
        self._write_md(out_path, content)

        return _ok(
            {
                "output_path": str(out_path),
                "anomaly_count": len(anomalies),
            },
            bytes_written=len(content.encode("utf-8")),
        )
