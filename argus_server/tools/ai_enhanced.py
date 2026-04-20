"""
AI 增强工具 - Batch 2 交付

功能一: 摘要 + 翻译 (复用 argus.ai.AIClient + litellm)
  - ai_summarize: 长文 → 结构化摘要
  - ai_translate: 任意文本 → 目标语种
  - ai_brief_news: 批量新闻 → 一句话简报

功能二: AI 搜索 API 骨架 (Tavily/Exa/Perplexity/Brave)
  - ai_web_search(query, provider="tavily|exa|perplexity|brave")
  - 留 env 占位, 拿到 API key 只改环境变量即可激活

所有工具返回 Argus 标准 envelope:
  {success, summary, data, error}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests


# ────────────────────── helper ──────────────────────

def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "AI_ERROR", **extra) -> Dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, **extra},
    }


def _need_key(env_var: str, service: str, signup_url: str) -> Dict:
    return _err(
        f"{service} 需要 API key。设置环境变量 {env_var}=<your_key>，或在 .env 文件加一行。"
        f" 注册免费账号: {signup_url}",
        code="AUTH_REQUIRED",
        env_var=env_var,
        signup_url=signup_url,
    )


# ────────────────────── AI 增强工具类 ──────────────────────

class AIEnhancedTools:
    """AI 增强功能 (摘要/翻译/搜索) 统一入口"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
        self._llm = None  # 懒加载 AIClient

    # ────────────── 懒加载 LLM ──────────────

    def _get_llm(self):
        """复用 Argus 的 AIClient (litellm 封装)"""
        if self._llm is not None:
            return self._llm
        try:
            from argus.ai.client import AIClient
            from argus.core.loader import load_config
            # 优先环境变量, 回退到 config.yaml 里的 ai 段
            cfg = {
                "MODEL": os.environ.get("AI_MODEL", "deepseek/deepseek-chat"),
                "API_KEY": os.environ.get("AI_API_KEY", ""),
                "API_BASE": os.environ.get("AI_API_BASE", ""),
                "TEMPERATURE": float(os.environ.get("AI_TEMPERATURE", "0.3")),
                "MAX_TOKENS": int(os.environ.get("AI_MAX_TOKENS", "2000")),
                "TIMEOUT": int(os.environ.get("AI_TIMEOUT", "60")),
            }
            if not cfg["API_KEY"]:
                # 尝试从 Argus 配置读
                try:
                    loaded = load_config()
                    ai_cfg = loaded.get("ai", {}) if isinstance(loaded, dict) else {}
                    cfg["API_KEY"] = ai_cfg.get("API_KEY", "") or cfg["API_KEY"]
                    cfg["MODEL"] = ai_cfg.get("MODEL") or cfg["MODEL"]
                    cfg["API_BASE"] = ai_cfg.get("API_BASE", "") or cfg["API_BASE"]
                except Exception:
                    pass
            if not cfg["API_KEY"]:
                return None
            self._llm = AIClient(cfg)
            return self._llm
        except Exception as ex:
            # 保持静默, 调用方自己判断 None
            return None

    def _llm_chat(self, system: str, user: str) -> Optional[str]:
        client = self._get_llm()
        if client is None:
            return None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            return client.chat(messages)
        except Exception as ex:
            raise RuntimeError(f"LLM 调用失败: {ex}") from ex

    # ────────────── 摘要 ──────────────

    def ai_summarize(
        self,
        text: str,
        style: str = "bullet",
        max_points: int = 5,
        target_language: str = "zh-CN",
    ) -> Dict:
        """文本摘要.
        style: bullet (要点) / paragraph (段落) / tldr (一句话)
        """
        if not text or not text.strip():
            return _err("text 不能为空", code="INVALID_PARAM")
        if self._get_llm() is None:
            return _err(
                "未配置 AI 模型。设置 AI_API_KEY / AI_MODEL 环境变量, "
                "或在 config/config.yaml 的 ai 段填写。",
                code="AUTH_REQUIRED",
            )

        style_hint = {
            "bullet": f"用 {max_points} 条要点列出 (markdown 无序列表格式)",
            "paragraph": "用 1-2 段话总结",
            "tldr": "用 1 句话总结 (不超过 50 字)",
        }.get(style, "用要点列出")

        system = (
            f"你是专业的文章摘要助手。请用 {target_language} 语言总结, "
            f"保留关键事实、数字、名称。不要评论, 不要加主观判断。"
        )
        user = f"请{style_hint}下面的文本:\n\n{text[:20000]}"
        try:
            summary = self._llm_chat(system, user)
        except RuntimeError as ex:
            return _err(str(ex), code="UPSTREAM_ERROR")

        return _ok(
            {"summary": summary, "style": style, "language": target_language},
            length_input=len(text),
            length_output=len(summary or ""),
        )

    # ────────────── 翻译 ──────────────

    def ai_translate(
        self,
        text: str,
        target_language: str = "zh-CN",
        source_language: Optional[str] = None,
        preserve_format: bool = True,
    ) -> Dict:
        """文本翻译.
        target_language: zh-CN / en / ja / ko / fr / de 等
        source_language: 不填则自动识别
        """
        if not text or not text.strip():
            return _err("text 不能为空", code="INVALID_PARAM")
        if self._get_llm() is None:
            return _err(
                "未配置 AI 模型。设置 AI_API_KEY / AI_MODEL 环境变量。",
                code="AUTH_REQUIRED",
            )

        fmt_hint = (
            "保留原文的 markdown / HTML 格式标记 (链接、粗体、代码块等)。"
            if preserve_format else ""
        )
        src = f"从 {source_language} " if source_language else "自动识别源语言, "

        system = (
            f"你是专业翻译。{src}翻译为 {target_language}。"
            f"保持语义准确、行文自然。{fmt_hint}"
            f"只输出译文, 不要解释、不要注释。"
        )
        user = text[:15000]
        try:
            translated = self._llm_chat(system, user)
        except RuntimeError as ex:
            return _err(str(ex), code="UPSTREAM_ERROR")

        return _ok(
            {
                "translated": translated,
                "target_language": target_language,
                "source_language": source_language or "auto",
            },
            length_input=len(text),
            length_output=len(translated or ""),
        )

    # ────────────── 批量新闻简报 ──────────────

    def ai_brief_news(
        self,
        news_items: List[Dict],
        style: str = "oneline",
        target_language: str = "zh-CN",
    ) -> Dict:
        """批量新闻简报。每条新闻一行/一段摘要。

        news_items: [{title, body?, url?, source?}, ...]
        style: oneline (一行)  / headline (头条式) / digest (段落摘要)
        """
        if not news_items:
            return _err("news_items 为空", code="INVALID_PARAM")
        if self._get_llm() is None:
            return _err("未配置 AI 模型", code="AUTH_REQUIRED")

        # 拼入 LLM 的输入 (只取前 30 条避免超长)
        items = news_items[:30]
        lines = []
        for i, it in enumerate(items, 1):
            title = (it.get("title") or "").strip()
            body = (it.get("body") or "").strip()[:300]
            src = it.get("source") or it.get("platform") or ""
            lines.append(f"[{i}] {title}"
                         + (f" — {src}" if src else "")
                         + (f"\n    {body}" if body else ""))
        compiled = "\n".join(lines)

        style_hint = {
            "oneline": "每条新闻一行, 形如: N. 标题 | 核心要点 (≤20字)",
            "headline": "每条新闻一个带标签的头条, 格式: [类别] 标题 — 一句要点",
            "digest": "每条新闻一段 1-2 句话的摘要",
        }.get(style, "每条一行摘要")

        system = (
            f"你是新闻简报编辑。请用 {target_language} 输出。不要编号重复, "
            f"不要加开场白/结束语, 直接输出列表。"
        )
        user = f"请按{style_hint}整理下面 {len(items)} 条新闻:\n\n{compiled}"

        try:
            briefing = self._llm_chat(system, user)
        except RuntimeError as ex:
            return _err(str(ex), code="UPSTREAM_ERROR")

        return _ok(
            {"briefing": briefing, "style": style, "language": target_language,
             "items_processed": len(items)},
            total=len(news_items),
            processed=len(items),
        )

    # ────────────── AI 网络搜索 ──────────────

    def ai_web_search(
        self,
        query: str,
        provider: str = "tavily",
        max_results: int = 10,
        include_answer: bool = True,
        search_depth: str = "basic",
    ) -> Dict:
        """AI 优化型网络搜索 - 针对 LLM 设计的实时搜索

        provider 选项 (按推荐度排序):
            tavily       — Tavily Search  (1000 次/月免费, 专为 LLM)
            exa          — Exa.ai 语义搜索 (免费额度有限)
            perplexity   — Perplexity API (付费, 含 LLM 总结)
            brave        — Brave Search   (2000 次/月免费, 独立索引)

        环境变量:
            TAVILY_API_KEY, EXA_API_KEY, PERPLEXITY_API_KEY, BRAVE_API_KEY
        """
        provider = provider.lower()
        handler = {
            "tavily": self._search_tavily,
            "exa": self._search_exa,
            "perplexity": self._search_perplexity,
            "brave": self._search_brave,
        }.get(provider)

        if not handler:
            return _err(
                f"不支持的 provider: {provider}. 可选: tavily/exa/perplexity/brave",
                code="INVALID_PARAM",
            )

        return handler(
            query=query,
            max_results=max(1, min(int(max_results), 50)),
            include_answer=include_answer,
            search_depth=search_depth,
        )

    # ---------- Tavily ----------
    def _search_tavily(self, query, max_results, include_answer, search_depth):
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            return _need_key(
                "TAVILY_API_KEY", "Tavily Search",
                "https://app.tavily.com/home",
            )
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,  # basic / advanced
                    "include_answer": include_answer,
                    "include_raw_content": False,
                },
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "answer": d.get("answer"),
                    "results": [
                        {
                            "title": x.get("title"),
                            "url": x.get("url"),
                            "content": x.get("content"),
                            "score": x.get("score"),
                            "published_date": x.get("published_date"),
                        }
                        for x in d.get("results", [])
                    ],
                    "query": query,
                },
                provider="tavily", count=len(d.get("results", [])),
            )
        except requests.exceptions.HTTPError as ex:
            if ex.response.status_code == 401:
                return _err("Tavily API key 无效", code="AUTH_REQUIRED")
            return _err(f"Tavily HTTP 错误: {ex}", code="UPSTREAM_ERROR")
        except Exception as ex:
            return _err(f"Tavily 调用失败: {ex}", code="NETWORK_ERROR")

    # ---------- Exa ----------
    def _search_exa(self, query, max_results, include_answer, search_depth):
        key = os.environ.get("EXA_API_KEY", "")
        if not key:
            return _need_key(
                "EXA_API_KEY", "Exa.ai",
                "https://dashboard.exa.ai/",
            )
        try:
            r = requests.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": max_results,
                    "useAutoprompt": True,
                    "type": "neural" if search_depth == "advanced" else "auto",
                    "contents": {"text": True} if include_answer else None,
                },
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "autoprompt": d.get("autopromptString"),
                    "results": [
                        {
                            "title": x.get("title"),
                            "url": x.get("url"),
                            "published_date": x.get("publishedDate"),
                            "author": x.get("author"),
                            "score": x.get("score"),
                            "text": (x.get("text") or "")[:500] if include_answer else None,
                        }
                        for x in d.get("results", [])
                    ],
                    "query": query,
                },
                provider="exa", count=len(d.get("results", [])),
            )
        except requests.exceptions.HTTPError as ex:
            if ex.response.status_code in (401, 403):
                return _err("Exa API key 无效或配额超出", code="AUTH_REQUIRED")
            return _err(f"Exa HTTP 错误: {ex}", code="UPSTREAM_ERROR")
        except Exception as ex:
            return _err(f"Exa 调用失败: {ex}", code="NETWORK_ERROR")

    # ---------- Perplexity ----------
    def _search_perplexity(self, query, max_results, include_answer, search_depth):
        key = os.environ.get("PERPLEXITY_API_KEY", "")
        if not key:
            return _need_key(
                "PERPLEXITY_API_KEY", "Perplexity",
                "https://www.perplexity.ai/settings/api",
            )
        try:
            # Perplexity 是 LLM-based 搜索, 用 chat/completions 端点
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "model": "sonar-pro" if search_depth == "advanced" else "sonar",
                    "messages": [
                        {"role": "system",
                         "content": "Be precise and concise. Include citations."},
                        {"role": "user", "content": query},
                    ],
                    "return_citations": True,
                    "return_images": False,
                },
                timeout=60,
            )
            r.raise_for_status()
            d = r.json()
            answer = (d.get("choices", [{}])[0].get("message") or {}).get("content", "")
            citations = d.get("citations", [])
            return _ok(
                {
                    "answer": answer,
                    "citations": citations[:max_results],
                    "query": query,
                    "model": d.get("model"),
                    "usage": d.get("usage"),
                },
                provider="perplexity", citation_count=len(citations),
            )
        except requests.exceptions.HTTPError as ex:
            if ex.response.status_code == 401:
                return _err("Perplexity API key 无效", code="AUTH_REQUIRED")
            return _err(f"Perplexity HTTP 错误: {ex}", code="UPSTREAM_ERROR")
        except Exception as ex:
            return _err(f"Perplexity 调用失败: {ex}", code="NETWORK_ERROR")

    # ---------- Brave ----------
    def _search_brave(self, query, max_results, include_answer, search_depth):
        key = os.environ.get("BRAVE_API_KEY", "")
        if not key:
            return _need_key(
                "BRAVE_API_KEY", "Brave Search",
                "https://api.search.brave.com/app/dashboard",
            )
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
                params={
                    "q": query,
                    "count": max_results,
                    "search_lang": "en",
                    "safesearch": "moderate",
                },
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            web = (d.get("web") or {}).get("results", [])
            return _ok(
                {
                    "results": [
                        {
                            "title": x.get("title"),
                            "url": x.get("url"),
                            "description": x.get("description"),
                            "age": x.get("age"),
                        }
                        for x in web
                    ],
                    "query": query,
                    "infobox": d.get("infobox"),
                },
                provider="brave", count=len(web),
            )
        except requests.exceptions.HTTPError as ex:
            if ex.response.status_code == 401:
                return _err("Brave API key 无效", code="AUTH_REQUIRED")
            return _err(f"Brave HTTP 错误: {ex}", code="UPSTREAM_ERROR")
        except Exception as ex:
            return _err(f"Brave 调用失败: {ex}", code="NETWORK_ERROR")

    # ────────────── 诊断: 看哪些 provider 已配置 ──────────────

    def check_ai_providers(self) -> Dict:
        """一键查: AI 模型 + 4 个 AI 搜索 provider 的配置状态"""
        status = {
            "llm_chat": {
                "configured": self._get_llm() is not None,
                "env_var": "AI_API_KEY (+ AI_MODEL, AI_API_BASE)",
                "purpose": "摘要 / 翻译 / 简报",
            },
        }
        for name, env_var, url in [
            ("tavily", "TAVILY_API_KEY", "https://app.tavily.com/home"),
            ("exa", "EXA_API_KEY", "https://dashboard.exa.ai/"),
            ("perplexity", "PERPLEXITY_API_KEY", "https://www.perplexity.ai/settings/api"),
            ("brave", "BRAVE_API_KEY", "https://api.search.brave.com/app/dashboard"),
        ]:
            status[name] = {
                "configured": bool(os.environ.get(env_var)),
                "env_var": env_var,
                "signup_url": url,
            }
        configured = sum(1 for v in status.values() if v.get("configured"))
        return _ok(
            status,
            total=len(status),
            configured=configured,
        )
