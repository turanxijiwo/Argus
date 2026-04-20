"""
Alert 规则引擎 - Batch 9 交付

DSL 示例 (alerts.yaml):
    rules:
      - name: nvidia_spike
        when:
          type: keyword_count
          keyword: Nvidia
          window_days: 1
          threshold: 5
        notify:
          channel: feishu
          title: "⚡ Nvidia 声量激增"
          template: "今天 {platforms} 共出现 {count} 次 Nvidia 相关讨论"

      - name: anomaly_watch
        when:
          type: anomaly
          z_threshold: 2.5
          min_frequency: 3
        notify:
          channel: feishu
          title: "🚨 异常话题预警"

支持的 when.type:
    keyword_count    — 指定关键词在窗口内出现次数 >= threshold
    anomaly          — 复用 detect_anomaly, 有异常即触发
    semantic_hit     — BM25 搜索 query, 分数 > min_score 的命中数 >= threshold

与 scheduler 的关系:
    本模块只负责"评估规则 + 触发动作"。真正的定时跑由 schedule_task 配
    workflow = [{tool: run_alerts}] 每小时/每天调一次即可。

工具:
    alert_add(name, when, notify)       添加规则
    alert_list()                        列出所有规则
    alert_remove(name)                  删除
    alert_test(name)                    评估但不推送 (干跑)
    alert_run_all()                     评估所有规则, 命中则推送
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "ALERT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,48}$")


def _yaml():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 200
    return y


class AlertTools:
    """基于 yaml 规则的告警引擎"""

    def __init__(self, project_root: Optional[str] = None,
                 notification_adapter=None,
                 ai_analytics_adapter=None,
                 semantic_adapter=None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.rules_path = self.project_root / "config" / "alerts.yaml"
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self._notif = notification_adapter
        self._analytics = ai_analytics_adapter
        self._semantic = semantic_adapter

    # ────────────── 规则读写 ──────────────

    def _load_rules(self) -> List[Dict]:
        if not self.rules_path.exists():
            return []
        try:
            y = _yaml()
            with self.rules_path.open("r", encoding="utf-8") as f:
                data = y.load(f) or {}
            rules = data.get("rules") or []
            return [dict(r) for r in rules if isinstance(r, dict)]
        except Exception:
            return []

    def _save_rules(self, rules: List[Dict]) -> None:
        y = _yaml()
        doc = {"rules": rules}
        with self.rules_path.open("w", encoding="utf-8") as f:
            y.dump(doc, f)

    # ────────────── CRUD ──────────────

    def add(self, name: str, when: Dict, notify: Dict,
            description: str = "", enabled: bool = True) -> Dict:
        if not _NAME_RE.match(name or ""):
            return _err("name 必须以字母开头, 2-49 位字母数字下划线横线", code="INVALID_NAME")
        err = self._validate(when, notify)
        if err:
            return _err(err, code="INVALID_RULE")

        rules = self._load_rules()
        if any(r.get("name") == name for r in rules):
            return _err(f"规则 {name} 已存在, 先删除或换名", code="DUPLICATE")

        rules.append({
            "name": name,
            "description": description,
            "enabled": enabled,
            "when": when,
            "notify": notify,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_rules(rules)
        return _ok({"name": name, "total_rules": len(rules)})

    def list_rules(self) -> Dict:
        rules = self._load_rules()
        out = [
            {
                "name": r.get("name"),
                "description": r.get("description", ""),
                "enabled": r.get("enabled", True),
                "when_type": r.get("when", {}).get("type"),
                "channel": r.get("notify", {}).get("channel"),
                "created_at": r.get("created_at"),
            }
            for r in rules
        ]
        return _ok({"rules": out, "full": rules}, count=len(out))

    def remove(self, name: str) -> Dict:
        rules = self._load_rules()
        new = [r for r in rules if r.get("name") != name]
        if len(new) == len(rules):
            return _err(f"未找到规则 {name}", code="NOT_FOUND")
        self._save_rules(new)
        return _ok({"removed": name, "remaining": len(new)})

    # ────────────── 校验 ──────────────

    _WHEN_TYPES = {"keyword_count", "anomaly", "semantic_hit"}

    def _validate(self, when: Dict, notify: Dict) -> Optional[str]:
        if not isinstance(when, dict):
            return "when 必须是对象"
        t = when.get("type")
        if t not in self._WHEN_TYPES:
            return f"when.type 必须是 {sorted(self._WHEN_TYPES)}"
        if t == "keyword_count":
            if not when.get("keyword"):
                return "keyword_count 规则需 keyword"
            if not isinstance(when.get("threshold", 0), int):
                return "threshold 必须是整数"
        if t == "semantic_hit":
            if not when.get("query"):
                return "semantic_hit 规则需 query"
        if not isinstance(notify, dict):
            return "notify 必须是对象"
        if not notify.get("channel"):
            return "notify.channel 必需 (feishu/dingtalk/wework/...)"
        return None

    # ────────────── 评估 ──────────────

    def _eval_keyword_count(self, when: Dict) -> Dict:
        """扫 BM25 索引, 统计关键词命中"""
        keyword = when["keyword"]
        threshold = int(when.get("threshold", 5))
        window_days = int(when.get("window_days", 1))
        if self._semantic is None:
            return {"triggered": False, "reason": "semantic 引擎未接入"}
        res = self._semantic.search(keyword, window_days=window_days, limit=1000, min_score=0.1)
        if not res.get("success"):
            return {"triggered": False, "reason": "semantic 搜索失败", "detail": res.get("error")}
        hits = (res.get("data") or {}).get("results") or []
        platforms = Counter(h["platform"] for h in hits)
        return {
            "triggered": len(hits) >= threshold,
            "count": len(hits),
            "threshold": threshold,
            "platforms": dict(platforms),
            "top_titles": [h["title"] for h in hits[:5]],
        }

    def _eval_anomaly(self, when: Dict) -> Dict:
        if self._analytics is None:
            return {"triggered": False, "reason": "analytics 引擎未接入"}
        z = float(when.get("z_threshold", 2.0))
        mf = int(when.get("min_frequency", 3))
        top_n = int(when.get("top_n", 10))
        topic = when.get("topic")
        res = self._analytics.detect_anomaly(topic=topic, z_threshold=z, min_frequency=mf, top_n=top_n)
        if not res.get("success"):
            return {"triggered": False, "reason": "anomaly 失败", "detail": res.get("error")}
        anomalies = (res.get("data") or {}).get("anomalies") or []
        return {
            "triggered": len(anomalies) > 0,
            "count": len(anomalies),
            "anomalies": anomalies[:5],
        }

    def _eval_semantic_hit(self, when: Dict) -> Dict:
        if self._semantic is None:
            return {"triggered": False, "reason": "semantic 引擎未接入"}
        query = when["query"]
        threshold = int(when.get("threshold", 3))
        min_score = float(when.get("min_score", 1.0))
        window_days = int(when.get("window_days", 1))
        res = self._semantic.search(query, window_days=window_days, min_score=min_score, limit=50)
        if not res.get("success"):
            return {"triggered": False, "reason": "semantic 失败"}
        hits = (res.get("data") or {}).get("results") or []
        return {
            "triggered": len(hits) >= threshold,
            "count": len(hits),
            "top_titles": [h["title"] for h in hits[:5]],
        }

    def _eval(self, rule: Dict) -> Dict:
        when = rule["when"]
        t = when["type"]
        if t == "keyword_count":
            return self._eval_keyword_count(when)
        if t == "anomaly":
            return self._eval_anomaly(when)
        if t == "semantic_hit":
            return self._eval_semantic_hit(when)
        return {"triggered": False, "reason": f"未知 when.type {t}"}

    # ────────────── 公开: test / run ──────────────

    def test(self, name: str) -> Dict:
        rules = self._load_rules()
        target = next((r for r in rules if r.get("name") == name), None)
        if not target:
            return _err(f"规则 {name} 不存在", code="NOT_FOUND")
        eval_result = self._eval(target)
        return _ok(
            {"rule": name, "eval": eval_result, "would_notify": eval_result.get("triggered")},
            dry_run=True,
        )

    def run_all(self) -> Dict:
        rules = self._load_rules()
        triggered: List[Dict] = []
        skipped: List[str] = []
        errors: List[Dict] = []

        for r in rules:
            name = r.get("name")
            if not r.get("enabled", True):
                skipped.append(name)
                continue
            try:
                eval_result = self._eval(r)
            except Exception as ex:
                errors.append({"rule": name, "error": f"{type(ex).__name__}: {ex}"})
                continue
            if not eval_result.get("triggered"):
                continue

            notify = r.get("notify") or {}
            payload = self._render_notify(notify, r, eval_result)
            sent = self._send(notify.get("channel"), payload)
            triggered.append({
                "rule": name,
                "eval": eval_result,
                "notify_result": sent,
            })

        return _ok(
            {
                "triggered": triggered,
                "skipped": skipped,
                "errors": errors,
            },
            total_rules=len(rules),
            triggered_count=len(triggered),
        )

    # ────────────── 渲染 + 推送 ──────────────

    def _render_notify(self, notify: Dict, rule: Dict, eval_result: Dict) -> Dict:
        title = notify.get("title") or f"Alert: {rule.get('name')}"
        tmpl = notify.get("template") or ""

        # 把各种命中数据都格式化好供 template 引用
        anomaly_lines = []
        for a in (eval_result.get("anomalies") or [])[:5]:
            trend = {"spike": "📈 爆发", "decline": "📉 衰退",
                     "new_emergence": "🆕 新现象"}.get(a.get("trend"), a.get("trend", ""))
            anomaly_lines.append(
                f"- **{a.get('keyword')}** {trend}  "
                f"(z={a.get('z_score')}, 今日 {a.get('latest_count')} 次 / 基线 {a.get('baseline_mean')})"
            )

        top_title_lines = [f"- {t}" for t in (eval_result.get("top_titles") or [])[:5]]

        # items 是聚合:优先 anomalies,再 top_titles, 都没就空
        items_block = "\n".join(anomaly_lines) or "\n".join(top_title_lines) or "_(详情见规则配置)_"

        ctx = {
            "rule": rule.get("name", ""),
            "count": eval_result.get("count", ""),
            "platforms": ", ".join(f"{k}({v})" for k, v in (eval_result.get("platforms") or {}).items()),
            "top_titles": "\n".join(top_title_lines),
            "anomalies": "\n".join(anomaly_lines),
            "items": items_block,              # 通用, 模板推荐用这个
            "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if tmpl:
            try:
                body = tmpl.format(**ctx)
            except Exception:
                body = tmpl
        else:
            # 默认模板
            lines = [f"**{title}**", f"规则: {rule.get('name')}", ""]
            if "count" in eval_result:
                lines.append(f"命中: {eval_result['count']}")
            if eval_result.get("top_titles"):
                lines.append("Top:")
                lines += [f"- {t}" for t in eval_result["top_titles"][:5]]
            if eval_result.get("anomalies"):
                lines.append("异常:")
                for a in eval_result["anomalies"][:5]:
                    lines.append(f"- {a.get('keyword')} z={a.get('z_score')} ({a.get('trend')})")
            lines.append(f"\n_时间: {ctx['now']}_")
            body = "\n".join(lines)
        return {"title": title, "content": body}

    def _send(self, channel: str, payload: Dict) -> Dict:
        """推送到 Argus notification 渠道"""
        if not self._notif:
            return {"ok": False, "reason": "notification 适配器未接入"}
        try:
            r = self._notif.send_notification(
                message=payload.get("content", ""),
                title=payload.get("title", ""),
                channels=[channel] if channel else None,
            )
            return {"ok": bool(r.get("success", r.get("ok"))), "detail": r}
        except Exception as ex:
            return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
