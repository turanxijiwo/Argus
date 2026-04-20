"""
内容安全扫描 - Batch 12 交付

对抓到的新闻标题批量跑规则扫描: 敏感词 / 手机号 / 邮箱 / 身份证 / 广告模式 / 诈骗模式

设计:
    - 零外部依赖 (纯 regex + 词表)
    - 规则分 3 档: high / medium / low
    - 扫单条 or 扫当天全量
    - 可扩展: config/safety_rules.yaml 自定义词表

工具:
    safety_scan_titles(titles: List[str])
    safety_scan_day(date?)
    safety_list_rules()
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "SAFETY_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


# ────────────────────── 内置规则 ──────────────────────

# PII / 隐私 (high)
_RULES_REGEX: List[Dict] = [
    {
        "id": "mobile_cn",
        "name": "中国手机号",
        "severity": "high",
        "category": "pii",
        "pattern": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    },
    {
        "id": "id_card_cn",
        "name": "中国身份证号",
        "severity": "high",
        "category": "pii",
        "pattern": re.compile(r"(?<!\d)[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    },
    {
        "id": "email",
        "name": "邮箱地址",
        "severity": "medium",
        "category": "pii",
        "pattern": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    },
    {
        "id": "url_suspicious",
        "name": "短链/可疑域名",
        "severity": "medium",
        "category": "spam",
        "pattern": re.compile(r"\b(?:bit\.ly|tinyurl\.com|t\.cn|dwz\.cn|ow\.ly|buff\.ly|rebrand\.ly)/\S+", re.IGNORECASE),
    },
    {
        "id": "qq_wechat",
        "name": "QQ/微信号露出",
        "severity": "low",
        "category": "contact_leak",
        "pattern": re.compile(r"(?:加\s*QQ|加\s*微信|V\s*信|VX|威信)[:：\s]*[\w\-\.]{3,30}", re.IGNORECASE),
    },
    {
        "id": "bank_card",
        "name": "疑似银行卡",
        "severity": "high",
        "category": "pii",
        "pattern": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    },
]

# 关键词词表 (可配置)
_KEYWORDS: Dict[str, Dict] = {
    "ads_promo": {
        "severity": "low",
        "category": "spam",
        "name": "营销广告词",
        "words": ["内部渠道", "一手货源", "免费领取", "限时特价", "独家优惠", "点击立即",
                  "推广合作", "代发广告"],
    },
    "scam": {
        "severity": "high",
        "category": "fraud",
        "name": "诈骗嫌疑",
        "words": ["刷单兼职", "垫付退款", "贷款免息", "无抵押贷款", "快速贷款", "包过包会",
                  "兼职日入", "轻松月入", "躺赚"],
    },
    "adult": {
        "severity": "medium",
        "category": "nsfw",
        "name": "成人内容嫌疑",
        "words": ["约炮", "一夜情", "成人用品", "艳遇"],
    },
    "violence": {
        "severity": "medium",
        "category": "violence",
        "name": "暴力相关",
        "words": ["爆炸装置", "枪支买卖", "炸弹制作"],
    },
}


class SafetyTools:
    """内容安全扫描"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self._user_rules_path = self.project_root / "config" / "safety_rules.yaml"

    # ────────────── 规则加载 (内置 + 用户扩展) ──────────────

    def _load_user_keywords(self) -> Dict[str, Dict]:
        if not self._user_rules_path.exists():
            return {}
        try:
            import yaml
            data = yaml.safe_load(self._user_rules_path.read_text(encoding="utf-8")) or {}
            kws = data.get("keywords", {})
            if not isinstance(kws, dict):
                return {}
            return kws
        except Exception:
            return {}

    def _scan_one(self, text: str) -> List[Dict]:
        """对一条文本做扫描, 返回 hits"""
        hits: List[Dict] = []
        if not text:
            return hits

        # Regex 规则
        for r in _RULES_REGEX:
            m = r["pattern"].search(text)
            if m:
                hits.append({
                    "rule_id": r["id"],
                    "rule_name": r["name"],
                    "severity": r["severity"],
                    "category": r["category"],
                    "match": m.group(0)[:40],
                })

        # 关键词规则
        all_keywords = dict(_KEYWORDS)
        all_keywords.update(self._load_user_keywords())
        low = text.lower()
        for rid, rule in all_keywords.items():
            for w in rule.get("words", []):
                if w.lower() in low:
                    hits.append({
                        "rule_id": rid,
                        "rule_name": rule.get("name", rid),
                        "severity": rule.get("severity", "low"),
                        "category": rule.get("category", "misc"),
                        "match": w,
                    })
                    break  # 同组规则只命中一次

        return hits

    # ────────────── 公开工具 ──────────────

    def scan_titles(self, titles: List[str]) -> Dict:
        """批量扫描标题"""
        if not isinstance(titles, list) or not titles:
            return _err("titles 必须是非空列表", code="INVALID_PARAM")

        flagged = []
        severity_counter: Counter = Counter()
        category_counter: Counter = Counter()
        rule_counter: Counter = Counter()

        for i, t in enumerate(titles):
            hits = self._scan_one(t)
            if not hits:
                continue
            # 最大 severity
            sev_order = {"high": 3, "medium": 2, "low": 1}
            top_sev = max(hits, key=lambda h: sev_order.get(h["severity"], 0))["severity"]
            flagged.append({
                "index": i,
                "title": t,
                "top_severity": top_sev,
                "hits": hits,
            })
            severity_counter[top_sev] += 1
            for h in hits:
                category_counter[h["category"]] += 1
                rule_counter[h["rule_id"]] += 1

        return _ok(
            {
                "total_scanned": len(titles),
                "flagged_count": len(flagged),
                "by_severity": dict(severity_counter),
                "by_category": dict(category_counter),
                "by_rule": dict(rule_counter),
                "flagged": flagged,
            },
            flagged=len(flagged),
            clean=len(titles) - len(flagged),
        )

    def scan_day(self, date: Optional[str] = None) -> Dict:
        """扫当天所有平台的标题"""
        news_dir = self.project_root / "output" / "news"
        if not news_dir.exists():
            return _err("output/news 不存在", code="NO_DATA")
        if not date:
            dates = sorted([f.stem for f in news_dir.glob("*.db")], reverse=True)
            if not dates:
                return _err("无可用日期", code="NO_DATA")
            date = dates[0]

        try:
            from argus.storage import get_storage_manager
            sm = get_storage_manager()
            data = sm.get_today_all_data(date)
        except Exception as ex:
            return _err(f"加载数据失败: {ex}", code="INTERNAL_ERROR")
        if data is None:
            return _err(f"{date} 无数据", code="NO_DATA")

        items_dict = getattr(data, "items", None) or {}
        id_to_name = getattr(data, "id_to_name", {}) or {}

        titles: List[str] = []
        meta: List[Dict] = []
        if isinstance(items_dict, dict):
            for pid, items in items_dict.items():
                pname = id_to_name.get(pid, pid)
                for it in items or []:
                    title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
                    url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
                    if not title:
                        continue
                    titles.append(title)
                    meta.append({"platform": pname, "url": url})

        res = self.scan_titles(titles)
        if not res.get("success"):
            return res

        flagged_with_meta = []
        for f in res["data"]["flagged"]:
            m = meta[f["index"]]
            flagged_with_meta.append({**f, **m})
        res["data"]["flagged"] = flagged_with_meta
        res["data"]["date"] = date
        return res

    def list_rules(self) -> Dict:
        """列出当前生效的所有规则"""
        regex_rules = [
            {"id": r["id"], "name": r["name"],
             "severity": r["severity"], "category": r["category"],
             "type": "regex"}
            for r in _RULES_REGEX
        ]
        kw_rules = []
        all_kw = dict(_KEYWORDS)
        all_kw.update(self._load_user_keywords())
        for rid, r in all_kw.items():
            kw_rules.append({
                "id": rid,
                "name": r.get("name", rid),
                "severity": r.get("severity", "low"),
                "category": r.get("category", "misc"),
                "word_count": len(r.get("words", [])),
                "type": "keyword",
                "source": "builtin" if rid in _KEYWORDS else "user",
            })
        return _ok(
            {"regex_rules": regex_rules, "keyword_rules": kw_rules},
            total=len(regex_rules) + len(kw_rules),
            user_rules_path=str(self._user_rules_path),
        )
