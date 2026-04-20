"""
每日早报生成 & 推送 - Batch 15 (接 Batch 10 导出)

根据本地 news db 渲染一份可读的 markdown 早报, 可推到飞书/钉钉/企业微信。

相对 export_daily_brief 的区别:
    export_daily_brief → 落到 vault 的 md 文件 (给 Obsidian)
    push_daily_brief   → 直接推到 IM 通知渠道 (给飞书群)

文本优化:
    - 子串分词去重 (保留最长词, 丢子串如 "霍尔" vs "霍尔木兹海峡")
    - 强停用词表 (过滤"中国/美国/公司/男子/女子/事件"等大类)
    - 标题清洗 (去 # / 去 emoji / trim)
    - 日期中文化 (2026-04-20 → 4 月 20 日 星期一)
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "BRIEF_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


# 分词停用词 — 高频但无信息量的大类/虚词
_STOPWORDS = {
    # 虚词
    "什么", "怎么", "为什么", "这个", "那个", "这样", "这些", "一个", "哪个", "可以",
    "如何", "还是", "或者", "以及", "但是", "于是", "因为", "所以", "现在", "今天",
    "昨天", "明天", "已经", "可能", "应该", "之后", "之前", "表示", "进行", "目前",
    "直接", "的话", "他们", "我们", "你们", "很多", "一下", "起来", "出来", "过来",
    "下来", "上来", "这么", "那么", "最终", "立即", "突然", "迅速", "正在", "依然",
    "依旧", "仍然", "比如", "例如", "其中", "包括", "涉及", "大概", "大约", "据悉",
    # 通用大类 (单独出现没信息量)
    "中国", "美国", "日本", "英国", "俄罗斯", "韩国", "印度",  # 国名太笼统
    "公司", "企业", "集团", "部门", "单位", "机构",
    "男子", "女子", "男孩", "女孩", "老人", "年轻", "年轻人", "网友", "粉丝",
    "视频", "直播", "节目", "事件", "事情", "消息", "新闻", "现场", "画面",
    "回应", "发生", "发布", "出现", "提出", "宣布", "称将", "表态",
    "第一", "第二", "第三", "第四", "第五",
    "全国", "全球", "全网", "当地", "官方", "相关", "涉事",
}

_RE_PUNCT = re.compile(r"[\W_]+", re.UNICODE)
_RE_CLEAN_TITLE = re.compile(r"^[#\s]+|[#\s]+$|\u200b")


def _tokenize(text: str) -> List[str]:
    import jieba
    out = []
    for t in jieba.cut_for_search(text.lower()):
        t = t.strip()
        if len(t) < 2:
            continue
        if _RE_PUNCT.fullmatch(t):
            continue
        if t in _STOPWORDS:
            continue
        out.append(t)
    return out


def _clean_title(t: str) -> str:
    t = _RE_CLEAN_TITLE.sub("", t or "").strip()
    # 去开头结尾的 # 围起来的话题标签
    t = re.sub(r"^#([^#]+)#\s*", r"\1 · ", t)
    t = re.sub(r"\s*#([^#]+)#$", r" · \1", t)
    return t.strip()


def _dedup_substring_tokens(counter: Counter, plats_of: Dict[str, set]) -> List:
    """去子串重复: 若 A ⊂ B 且 count(A) - count(B) ≤ 2, 丢 A

    例: "机器" (26) + "机器人" (26) → 只留 "机器人"
        "霍尔" (11) + "霍尔木" (11) + "霍尔木兹海峡" (10) → 只留 "霍尔木兹海峡"
    """
    items = [(k, c) for k, c in counter.most_common(100) if len(plats_of[k]) >= 2]
    # 按词长降序, 优先保留长词
    items_by_len = sorted(items, key=lambda x: (-len(x[0]), -x[1]))
    kept: List = []
    dropped = set()
    for word, count in items_by_len:
        is_dropped = False
        for long_word, long_count in kept:
            if word in long_word and word != long_word:
                if abs(count - long_count) <= 2:
                    dropped.add(word)
                    is_dropped = True
                    break
        if not is_dropped:
            kept.append((word, count))
    # 恢复按 count 降序
    kept.sort(key=lambda x: -x[1])
    return kept


_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _fmt_date_cn(ds: str) -> str:
    """2026-04-20 → 4 月 20 日 · 星期一"""
    try:
        dt = datetime.strptime(ds, "%Y-%m-%d")
        wd = _WEEKDAY_CN[dt.weekday()]
        return f"{dt.month} 月 {dt.day} 日 · 星期{wd}"
    except Exception:
        return ds


class DailyBriefTools:
    """渲染 + 推送每日早报"""

    def __init__(self, project_root: Optional[str] = None, notification_adapter=None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self._notif = notification_adapter

    # ────────────── 内部: 加载当日数据 ──────────────

    def _load_day(self, date: Optional[str] = None) -> Dict:
        news_dir = self.project_root / "output" / "news"
        if not news_dir.exists():
            return {"error": "output/news 不存在"}
        if not date:
            dates = sorted([f.stem for f in news_dir.glob("*.db")], reverse=True)
            if not dates:
                return {"error": "无可用日期"}
            date = dates[0]

        try:
            from argus.storage import get_storage_manager
            sm = get_storage_manager()
            data = sm.get_today_all_data(date)
        except Exception as ex:
            return {"error": f"加载失败: {ex}"}
        if data is None:
            return {"error": f"{date} 无数据"}

        items_dict = getattr(data, "items", None) or {}
        id_to_name = getattr(data, "id_to_name", {}) or {}

        platforms: Dict[str, List[Dict]] = {}
        total = 0
        for pid, items in (items_dict.items() if isinstance(items_dict, dict) else []):
            name = id_to_name.get(pid, pid)
            rows = []
            for it in items or []:
                title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
                url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
                title = _clean_title(title)
                if title:
                    rows.append({"title": title, "url": url})
            if rows:
                platforms[name] = rows
                total += len(rows)
        return {"date": date, "total": total, "platforms": platforms}

    # ────────────── 渲染 markdown ──────────────

    def render(
        self,
        date: Optional[str] = None,
        top_keywords: int = 10,
        top_per_platform: int = 3,
        max_platforms: int = 8,
        min_platform_count: int = 2,   # 热词至少被 N 个平台报道
    ) -> Dict:
        day = self._load_day(date)
        if "error" in day:
            return _err(day["error"], code="NO_DATA")

        total = day["total"]
        platforms = day["platforms"]
        date = day["date"]

        # 分词
        counter: Counter = Counter()
        plats_of: Dict[str, set] = defaultdict(set)
        for pname, rows in platforms.items():
            for r in rows:
                for tok in _tokenize(r["title"]):
                    counter[tok] += 1
                    plats_of[tok].add(pname)

        # 去子串重复
        top_all = _dedup_substring_tokens(counter, plats_of)
        top_kw = top_all[:top_keywords]

        # 为每个热词选一条"代表性标题" (用户看词就知道发生啥)
        # 策略: 包含该词的所有标题里, 选"最短的+包含具体动作动词"的那条
        kw_sample: Dict[str, Dict] = {}
        for kw, _ in top_kw:
            candidates = []
            for pname, rows in platforms.items():
                for r in rows:
                    if kw in r["title"].lower():
                        candidates.append({"title": r["title"], "url": r.get("url", ""), "platform": pname})
            if not candidates:
                continue
            # 优先短标题 (通常更精炼), 但不要太短 (>=10 字)
            decent = [c for c in candidates if len(c["title"]) >= 10]
            if decent:
                decent.sort(key=lambda c: len(c["title"]))
                kw_sample[kw] = decent[0]
            else:
                candidates.sort(key=lambda c: -len(c["title"]))
                kw_sample[kw] = candidates[0]

        # 渲染
        now_str = datetime.now().strftime("%H:%M")
        date_cn = _fmt_date_cn(date)

        lines = [
            f"## 📅 {date_cn}",
            f"",
            f"> **{total}** 条 · **{len(platforms)}** 个平台 · 更新于 {now_str}",
            f"",
        ]

        if top_kw:
            lines.append(f"### 🔥 今日热词 Top {len(top_kw)}")
            lines.append("")
            for k, c in top_kw:
                plat_count = len(plats_of[k])
                lines.append(f"**{k}** · {c} 次 · {plat_count} 平台")
                sample = kw_sample.get(k)
                if sample:
                    title = sample["title"]
                    if len(title) > 55:
                        title = title[:55] + "…"
                    if sample.get("url"):
                        lines.append(f"   ↳ [{title}]({sample['url']})")
                    else:
                        lines.append(f"   ↳ {title}")
                lines.append("")

        # 平台头条 (按条数倒序, 最多 max_platforms 个)
        sorted_plats = sorted(platforms.items(), key=lambda x: len(x[1]), reverse=True)[:max_platforms]
        if sorted_plats:
            lines.append("### 📰 平台头条")
            lines.append("")
            for pname, rows in sorted_plats:
                lines.append(f"**{pname}** · {len(rows)} 条")
                for r in rows[:top_per_platform]:
                    title = r["title"]
                    if len(title) > 50:
                        title = title[:50] + "…"
                    if r.get("url"):
                        lines.append(f"- [{title}]({r['url']})")
                    else:
                        lines.append(f"- {title}")
                lines.append("")

        lines.append("---")
        lines.append(f"_Argus · {len(platforms)} 平台 · 去冗余后 {len(top_kw)} 组热词_")

        content = "\n".join(lines)
        return _ok(
            {
                "content": content,
                "date": date,
                "total_items": total,
                "platform_count": len(platforms),
                "keywords_count": len(top_kw),
            },
            bytes=len(content.encode("utf-8")),
        )

    # ────────────── 推送 ──────────────

    def push(
        self,
        channels: Optional[List[str]] = None,
        title_prefix: str = "🌅 Argus",
        date: Optional[str] = None,
        top_keywords: int = 10,
        top_per_platform: int = 3,
        max_platforms: int = 8,
    ) -> Dict:
        """渲染并推送到通知渠道"""
        rendered = self.render(
            date=date, top_keywords=top_keywords,
            top_per_platform=top_per_platform,
            max_platforms=max_platforms,
        )
        if not rendered.get("success"):
            return rendered

        content = rendered["data"]["content"]
        real_date = rendered["data"]["date"]
        date_cn = _fmt_date_cn(real_date)
        title = f"{title_prefix} · {date_cn}"

        if self._notif is None:
            return _err("notification 适配器未接入", code="INTERNAL_ERROR")
        try:
            r = self._notif.send_notification(
                message=content,
                title=title,
                channels=channels,
            )
            return _ok(
                {
                    "title": title,
                    "content_preview": content[:300],
                    "total_items": rendered["data"]["total_items"],
                    "platform_count": rendered["data"]["platform_count"],
                    "notification_result": r,
                },
                channels=channels or "all",
            )
        except Exception as ex:
            return _err(f"推送失败: {ex}", code="NOTIFY_ERROR")
