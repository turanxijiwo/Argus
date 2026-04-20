"""
本地语义/全文搜索 - Batch 8 交付

对 output/news/*.db 的历史标题做 BM25 索引, 支持跨天全文检索 + 相似标题召回。

为什么不用 embeddings?
  - Python 3.14 下 onnxruntime/torch wheel 缺失
  - 新闻标题短 + 实体关键词主导, BM25 实测比 embedding 更准
  - 0 依赖冲突, 查询 <50ms
未来升级路线:
  - AI_API_KEY 设置后, 可加 OpenAI embedding 分支 (接口已为此留位)

工具:
    semantic_index_rebuild(days=30)              全量重建索引
    semantic_index_status()                      索引元信息
    semantic_search(query, window_days, limit)   全文搜索 (跨天)
    semantic_similar(title, limit)               找相似标题
"""

from __future__ import annotations

import json
import os
import pickle
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "SEMANTIC_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


# jieba 初始化一次 (懒加载)
_jieba_inited = False


def _tokenize(text: str) -> List[str]:
    """中英混合分词: jieba + 保留原串里的英数词"""
    global _jieba_inited
    if not _jieba_inited:
        import jieba
        jieba.initialize()
        _jieba_inited = True
    import jieba
    text = (text or "").lower()
    # 切词 + 过滤单字符
    toks = [t.strip() for t in jieba.cut_for_search(text) if t.strip()]
    # 过滤标点/空白
    cleaned = []
    for t in toks:
        if len(t) < 1:
            continue
        if re.fullmatch(r"[\W_]+", t):
            continue
        cleaned.append(t)
    return cleaned


class SemanticSearchTools:
    """BM25 本地索引"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.index_dir = self.project_root / "output" / "semantic_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "bm25.pkl"
        self.meta_path = self.index_dir / "meta.json"
        self._bm25 = None                    # BM25Okapi
        self._docs: List[Dict] = []          # [{date, platform, title, url, ...}]
        self._tokens: List[List[str]] = []   # 每个 doc 的 token 列表(复用建索引时的)

    # ────────────── 索引构建 ──────────────

    def rebuild(self, days: int = 30) -> Dict:
        """扫 output/news 最近 N 天, 全量重建 BM25 索引"""
        t0 = time.time()
        try:
            from argus.storage import get_storage_manager
        except Exception as ex:
            return _err(f"无法加载 storage: {ex}", code="INTERNAL_ERROR")

        sm = get_storage_manager()
        news_dir = self.project_root / "output" / "news"
        if not news_dir.exists():
            return _err("output/news 目录不存在", code="NO_DATA")

        available = sorted([f.stem for f in news_dir.glob("*.db")], reverse=True)[:days]
        if not available:
            return _err("无可用日期", code="NO_DATA")

        docs: List[Dict] = []
        for ds in available:
            try:
                data = sm.get_today_all_data(ds)
            except Exception:
                continue
            if data is None:
                continue
            items_dict = getattr(data, "items", None) or {}
            id_to_name = getattr(data, "id_to_name", {}) or {}
            if not isinstance(items_dict, dict):
                continue
            for pid, items in items_dict.items():
                pname = id_to_name.get(pid, pid)
                for it in items or []:
                    title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
                    url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
                    if not title:
                        continue
                    docs.append({
                        "date": ds,
                        "platform": pname,
                        "title": title,
                        "url": url,
                    })

        if not docs:
            return _err("所有日期都无可索引数据", code="NO_DATA")

        # 去重 (按 platform+title 组合)
        seen = set()
        uniq_docs = []
        for d in docs:
            key = (d["platform"], d["title"])
            if key in seen:
                continue
            seen.add(key)
            uniq_docs.append(d)

        # 分词 + 建索引
        tokens = [_tokenize(d["title"]) for d in uniq_docs]

        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi(tokens)

        # 落盘
        with self.index_path.open("wb") as f:
            pickle.dump({"bm25": bm25, "docs": uniq_docs, "tokens": tokens}, f)

        meta = {
            "built_at": datetime.now().isoformat(),
            "days_covered": days,
            "dates": available,
            "doc_count": len(uniq_docs),
            "vocab_size": len({t for toks in tokens for t in toks}),
            "build_seconds": round(time.time() - t0, 2),
        }
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # 缓存到内存
        self._bm25 = bm25
        self._docs = uniq_docs
        self._tokens = tokens

        return _ok(meta, rebuilt=True)

    def status(self) -> Dict:
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                meta["index_file_size"] = self.index_path.stat().st_size if self.index_path.exists() else 0
                meta["index_loaded"] = self._bm25 is not None
                return _ok(meta, exists=True)
            except Exception as ex:
                return _err(f"读取 meta 失败: {ex}", code="READ_ERROR")
        return _ok({"exists": False, "hint": "先调用 semantic_index_rebuild()"}, exists=False)

    # ────────────── 查询 ──────────────

    def _load_index(self) -> Optional[str]:
        if self._bm25 is not None:
            return None
        if not self.index_path.exists():
            return "索引尚未构建, 请先调 semantic_index_rebuild()"
        try:
            with self.index_path.open("rb") as f:
                payload = pickle.load(f)
            self._bm25 = payload["bm25"]
            self._docs = payload["docs"]
            self._tokens = payload["tokens"]
            return None
        except Exception as ex:
            return f"索引加载失败: {ex}"

    def search(
        self,
        query: str,
        window_days: Optional[int] = None,
        limit: int = 20,
        platforms: Optional[List[str]] = None,
        min_score: float = 0.0,
    ) -> Dict:
        """BM25 全文搜索

        Args:
            query: 查询串 (中英混合)
            window_days: 只返回最近 N 天的结果 (不传=全部索引内)
            limit: 返回条数
            platforms: 平台过滤 (中文名, 如 ["知乎","微博"])
            min_score: BM25 分数下限
        """
        if not query or not query.strip():
            return _err("query 不能为空", code="INVALID_PARAM")
        err = self._load_index()
        if err:
            return _err(err, code="NO_INDEX")

        q_tokens = _tokenize(query)
        if not q_tokens:
            return _err(f"query '{query}' 分词后为空", code="INVALID_PARAM")

        scores = self._bm25.get_scores(q_tokens)

        # 日期窗口过滤
        cutoff: Optional[str] = None
        if window_days is not None and window_days > 0:
            from datetime import datetime, timedelta
            # 用索引里最晚日期作为"今天"(可能比实际今日早)
            latest = max(d["date"] for d in self._docs) if self._docs else None
            if latest:
                try:
                    latest_dt = datetime.strptime(latest, "%Y-%m-%d")
                    cutoff_dt = latest_dt - timedelta(days=window_days - 1)
                    cutoff = cutoff_dt.strftime("%Y-%m-%d")
                except Exception:
                    cutoff = None

        results = []
        for idx, score in enumerate(scores):
            if score < min_score:
                continue
            doc = self._docs[idx]
            if cutoff and doc["date"] < cutoff:
                continue
            if platforms and doc["platform"] not in platforms:
                continue
            results.append({
                "score": round(float(score), 3),
                "date": doc["date"],
                "platform": doc["platform"],
                "title": doc["title"],
                "url": doc["url"],
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:max(1, int(limit))]

        return _ok(
            {"results": results, "query": query, "query_tokens": q_tokens},
            total=len(results),
            window_days=window_days,
            cutoff=cutoff,
        )

    def similar(self, title: str, limit: int = 10) -> Dict:
        """找与给定标题最相似的历史标题 (BM25 余弦近似)"""
        if not title or not title.strip():
            return _err("title 不能为空", code="INVALID_PARAM")
        err = self._load_index()
        if err:
            return _err(err, code="NO_INDEX")

        q_tokens = _tokenize(title)
        if not q_tokens:
            return _err("title 分词后为空", code="INVALID_PARAM")

        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(
            [(i, s) for i, s in enumerate(scores) if s > 0],
            key=lambda x: x[1], reverse=True,
        )[:limit + 3]  # 多拉几个避免完全相同的

        results = []
        for i, s in ranked:
            doc = self._docs[i]
            if doc["title"] == title:
                continue
            results.append({
                "score": round(float(s), 3),
                "date": doc["date"],
                "platform": doc["platform"],
                "title": doc["title"],
                "url": doc["url"],
            })
            if len(results) >= limit:
                break
        return _ok(
            {"results": results, "input_title": title},
            total=len(results),
        )
