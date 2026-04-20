"""
外部 API 适配器工具

为 Argus 接入额外的全球数据源 (无需 API key 即可使用):

  - arXiv API           论文预印本搜索
  - Semantic Scholar    论文 + 引用图谱
  - OpenAlex            2.4 亿论文元数据
  - PubMed E-utilities  医学/生物全库
  - Hacker News API     完整社区帖子 (含 score/comments)
  - Reddit JSON         任意 subreddit 帖子
  - GitHub API          Trending / Releases / 仓库搜索

所有适配器统一返回:
    {"success": bool, "summary": {...}, "data": {...}, "error"?: {...}}
"""

import time
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import requests

try:
    import feedparser
except ImportError:
    feedparser = None


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Argus/6.6 Safari/537.36"
)


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "EXTERNAL_API_ERROR", **extra) -> Dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, **extra},
    }


class ExternalAPITools:
    """外部数据源 API 适配器集合"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": _DEFAULT_UA,
                "Accept": "application/json, application/atom+xml, text/xml, */*",
            }
        )

    # ───────────────────────── 内部 helper ─────────────────────────
    def _get(self, url: str, params: Optional[Dict] = None,
             timeout: int = 20, headers: Optional[Dict] = None) -> requests.Response:
        h = dict(self.session.headers)
        if headers:
            h.update(headers)
        return self.session.get(url, params=params, headers=h, timeout=timeout)

    # ───────────────────────── 1. arXiv API ─────────────────────────
    def search_arxiv(
        self,
        query: str,
        category: Optional[str] = None,
        max_results: int = 20,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> Dict:
        """搜索 arXiv 论文 (官方 Atom API)"""
        if not feedparser:
            return _err("feedparser 未安装", code="DEP_MISSING")

        try:
            search = query.strip()
            if category:
                search = f"({search}) AND cat:{category}" if search else f"cat:{category}"
            params = {
                "search_query": search,
                "start": 0,
                "max_results": max(1, min(int(max_results), 100)),
                "sortBy": sort_by,
                "sortOrder": sort_order,
            }
            r = self._get("http://export.arxiv.org/api/query", params=params, timeout=25)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            items = []
            for e in feed.entries:
                items.append(
                    {
                        "id": getattr(e, "id", ""),
                        "title": getattr(e, "title", "").strip(),
                        "authors": [a.name for a in getattr(e, "authors", [])],
                        "summary": getattr(e, "summary", "").strip(),
                        "published": getattr(e, "published", ""),
                        "updated": getattr(e, "updated", ""),
                        "primary_category": getattr(
                            getattr(e, "arxiv_primary_category", {}), "get", lambda *_: ""
                        )("term") if hasattr(e, "arxiv_primary_category") else "",
                        "categories": [t.term for t in getattr(e, "tags", [])],
                        "pdf_url": next(
                            (l.href for l in getattr(e, "links", []) if l.get("type") == "application/pdf"),
                            "",
                        ),
                        "abs_url": getattr(e, "link", ""),
                    }
                )
            return _ok(
                {"papers": items},
                source="arxiv",
                query=query,
                category=category,
                count=len(items),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"arXiv 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"arXiv 解析失败: {ex}")

    # ───────────────────────── 2. Semantic Scholar ─────────────────────────
    def search_semantic_scholar(
        self,
        query: str,
        limit: int = 20,
        year: Optional[str] = None,
        fields_of_study: Optional[List[str]] = None,
        min_citation_count: Optional[int] = None,
    ) -> Dict:
        """Semantic Scholar 论文搜索 (含引用数 + AI TLDR)"""
        try:
            fields = (
                "paperId,title,abstract,year,authors,venue,publicationDate,"
                "citationCount,influentialCitationCount,tldr,openAccessPdf,url"
            )
            params = {
                "query": query,
                "limit": max(1, min(int(limit), 100)),
                "fields": fields,
            }
            if year:
                params["year"] = year
            if fields_of_study:
                params["fieldsOfStudy"] = ",".join(fields_of_study)
            if min_citation_count is not None:
                params["minCitationCount"] = int(min_citation_count)

            r = self._get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=25,
            )
            # Semantic Scholar 匿名调用易被限流, 内置一次退避重试
            if r.status_code == 429:
                time.sleep(3)
                r = self._get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params,
                    timeout=25,
                )
            if r.status_code == 429:
                return _err(
                    "Semantic Scholar 限流, 稍后重试 (匿名调用 1 RPS),"
                    " 建议设置 SEMANTIC_SCHOLAR_API_KEY 环境变量",
                    code="RATE_LIMITED",
                )
            r.raise_for_status()
            data = r.json()
            papers = []
            for p in data.get("data", []):
                tldr = p.get("tldr") or {}
                papers.append(
                    {
                        "id": p.get("paperId"),
                        "title": p.get("title"),
                        "abstract": p.get("abstract"),
                        "tldr": tldr.get("text") if tldr else None,
                        "year": p.get("year"),
                        "venue": p.get("venue"),
                        "publication_date": p.get("publicationDate"),
                        "citations": p.get("citationCount"),
                        "influential_citations": p.get("influentialCitationCount"),
                        "authors": [a.get("name") for a in (p.get("authors") or [])],
                        "url": p.get("url"),
                        "pdf_url": (p.get("openAccessPdf") or {}).get("url"),
                    }
                )
            return _ok(
                {"papers": papers, "total": data.get("total", len(papers))},
                source="semantic_scholar",
                query=query,
                count=len(papers),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Semantic Scholar 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Semantic Scholar 解析失败: {ex}")

    # ───────────────────────── 3. OpenAlex ─────────────────────────
    def search_openalex(
        self,
        query: str,
        per_page: int = 25,
        from_publication_date: Optional[str] = None,
        sort: str = "relevance_score:desc",
    ) -> Dict:
        """OpenAlex 论文搜索 (2.4 亿论文, 免费无 key)"""
        try:
            params = {
                "search": query,
                "per-page": max(1, min(int(per_page), 100)),
                "sort": sort,
            }
            filters = []
            if from_publication_date:
                filters.append(f"from_publication_date:{from_publication_date}")
            if filters:
                params["filter"] = ",".join(filters)

            r = self._get(
                "https://api.openalex.org/works",
                params=params,
                headers={"User-Agent": "Argus/6.6 (mailto:noreply@argus.local)"},
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
            works = []
            for w in data.get("results", []):
                works.append(
                    {
                        "id": w.get("id"),
                        "doi": w.get("doi"),
                        "title": w.get("title"),
                        "publication_date": w.get("publication_date"),
                        "type": w.get("type"),
                        "cited_by_count": w.get("cited_by_count"),
                        "concepts": [
                            {"name": c.get("display_name"), "level": c.get("level")}
                            for c in (w.get("concepts") or [])[:5]
                        ],
                        "authors": [
                            a.get("author", {}).get("display_name")
                            for a in (w.get("authorships") or [])
                        ],
                        "open_access": w.get("open_access"),
                        "url": (w.get("primary_location") or {}).get("landing_page_url")
                        or w.get("doi"),
                    }
                )
            return _ok(
                {"works": works, "meta": data.get("meta", {})},
                source="openalex",
                query=query,
                count=len(works),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"OpenAlex 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"OpenAlex 解析失败: {ex}")

    # ───────────────────────── 4. PubMed ─────────────────────────
    def search_pubmed(self, query: str, max_results: int = 20) -> Dict:
        """PubMed 医学/生物论文搜索 (E-utilities, 免费)"""
        try:
            # Step 1: esearch -> 拿 PMID 列表
            esearch = self._get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmax": max(1, min(int(max_results), 100)),
                    "retmode": "json",
                    "sort": "date",
                },
                timeout=20,
            )
            esearch.raise_for_status()
            pmids = esearch.json().get("esearchresult", {}).get("idlist", [])
            if not pmids:
                return _ok({"papers": []}, source="pubmed", query=query, count=0)

            # Step 2: esummary -> 拿元数据
            esum = self._get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
                timeout=20,
            )
            esum.raise_for_status()
            result = esum.json().get("result", {})
            papers = []
            for pmid in pmids:
                p = result.get(pmid, {})
                if not p:
                    continue
                papers.append(
                    {
                        "pmid": pmid,
                        "title": p.get("title", ""),
                        "authors": [a.get("name") for a in p.get("authors", [])][:8],
                        "journal": p.get("fulljournalname", ""),
                        "pubdate": p.get("pubdate", ""),
                        "doi": next(
                            (a.get("value") for a in p.get("articleids", []) if a.get("idtype") == "doi"),
                            "",
                        ),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    }
                )
            return _ok(
                {"papers": papers},
                source="pubmed",
                query=query,
                count=len(papers),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"PubMed 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"PubMed 解析失败: {ex}")

    # ───────────────────────── 5. Hacker News API ─────────────────────────
    def get_hackernews_top(self, story_type: str = "top", limit: int = 30) -> Dict:
        """Hacker News 完整 API (top/new/best/ask/show/job)"""
        try:
            allowed = {"top", "new", "best", "ask", "show", "job"}
            if story_type not in allowed:
                return _err(f"story_type 必须是 {allowed}", code="INVALID_PARAM")

            ids = self._get(
                f"https://hacker-news.firebaseio.com/v0/{story_type}stories.json",
                timeout=15,
            ).json()
            ids = ids[: max(1, min(int(limit), 100))]
            stories = []
            for sid in ids:
                try:
                    r = self._get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                        timeout=10,
                    )
                    item = r.json() or {}
                    if not item.get("title"):
                        continue
                    stories.append(
                        {
                            "id": item.get("id"),
                            "title": item.get("title"),
                            "url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                            "score": item.get("score", 0),
                            "comments": item.get("descendants", 0),
                            "by": item.get("by"),
                            "time": datetime.fromtimestamp(
                                item.get("time", 0), tz=timezone.utc
                            ).isoformat() if item.get("time") else "",
                            "type": item.get("type"),
                            "hn_url": f"https://news.ycombinator.com/item?id={sid}",
                        }
                    )
                except Exception:
                    continue
            return _ok(
                {"stories": stories},
                source="hackernews",
                story_type=story_type,
                count=len(stories),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"HN 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"HN 解析失败: {ex}")

    # ───────────────────────── 6. Reddit JSON ─────────────────────────
    def search_reddit(
        self,
        subreddit: str,
        sort: str = "hot",
        time_filter: str = "day",
        limit: int = 25,
    ) -> Dict:
        """Reddit subreddit 帖子 (官方公开 JSON, 无需 OAuth)"""
        try:
            if sort not in ("hot", "new", "top", "rising", "controversial"):
                return _err(f"sort 必须是 hot/new/top/rising/controversial", code="INVALID_PARAM")
            params = {"limit": max(1, min(int(limit), 100))}
            if sort in ("top", "controversial"):
                params["t"] = time_filter

            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
            r = self._get(url, params=params, timeout=15,
                          headers={"User-Agent": "ArgusBot/1.0"})
            r.raise_for_status()
            data = r.json().get("data", {}).get("children", [])
            posts = []
            for child in data:
                p = child.get("data", {})
                posts.append(
                    {
                        "id": p.get("id"),
                        "title": p.get("title"),
                        "author": p.get("author"),
                        "score": p.get("score", 0),
                        "upvote_ratio": p.get("upvote_ratio"),
                        "num_comments": p.get("num_comments", 0),
                        "created_utc": datetime.fromtimestamp(
                            p.get("created_utc", 0), tz=timezone.utc
                        ).isoformat() if p.get("created_utc") else "",
                        "url": p.get("url"),
                        "permalink": f"https://reddit.com{p.get('permalink', '')}",
                        "is_self": p.get("is_self"),
                        "selftext": (p.get("selftext") or "")[:1000],
                        "flair": p.get("link_flair_text"),
                        "subreddit": p.get("subreddit"),
                    }
                )
            return _ok(
                {"posts": posts},
                source="reddit",
                subreddit=subreddit,
                sort=sort,
                count=len(posts),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Reddit 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Reddit 解析失败: {ex}")

    # ───────────────────────── 7. GitHub API ─────────────────────────
    def get_github_trending(
        self,
        language: Optional[str] = None,
        since: str = "daily",
        limit: int = 25,
    ) -> Dict:
        """GitHub 'Trending' (用 search API 模拟: 按时间窗 stars 排序)"""
        try:
            today = datetime.now(timezone.utc)
            delta = {"daily": 1, "weekly": 7, "monthly": 30}.get(since, 1)
            since_date = (today - timedelta(days=delta)).strftime("%Y-%m-%d")
            q = f"created:>{since_date}"
            if language:
                q += f" language:{language}"
            r = self._get(
                "https://api.github.com/search/repositories",
                params={
                    "q": q,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": max(1, min(int(limit), 100)),
                },
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
            )
            if r.status_code == 403:
                return _err(
                    "GitHub 匿名调用限流 (60/h),建议设置 GITHUB_TOKEN 环境变量",
                    code="RATE_LIMITED",
                )
            r.raise_for_status()
            items = r.json().get("items", [])
            repos = []
            for it in items:
                repos.append(
                    {
                        "name": it.get("full_name"),
                        "url": it.get("html_url"),
                        "description": it.get("description"),
                        "stars": it.get("stargazers_count"),
                        "language": it.get("language"),
                        "created_at": it.get("created_at"),
                        "updated_at": it.get("updated_at"),
                        "topics": it.get("topics", []),
                        "owner": it.get("owner", {}).get("login"),
                    }
                )
            return _ok(
                {"repositories": repos},
                source="github_trending",
                language=language,
                since=since,
                count=len(repos),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GitHub 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GitHub 解析失败: {ex}")

    def get_github_releases(self, repo: str, limit: int = 10) -> Dict:
        """获取仓库最新发布 (适合追踪关键开源项目动态)"""
        try:
            r = self._get(
                f"https://api.github.com/repos/{repo}/releases",
                params={"per_page": max(1, min(int(limit), 30))},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15,
            )
            if r.status_code == 404:
                return _err(f"仓库 {repo} 不存在", code="NOT_FOUND")
            if r.status_code == 403:
                return _err("GitHub 限流", code="RATE_LIMITED")
            r.raise_for_status()
            data = r.json()
            releases = []
            for rel in data:
                releases.append(
                    {
                        "name": rel.get("name") or rel.get("tag_name"),
                        "tag": rel.get("tag_name"),
                        "url": rel.get("html_url"),
                        "published_at": rel.get("published_at"),
                        "is_prerelease": rel.get("prerelease"),
                        "is_draft": rel.get("draft"),
                        "body": (rel.get("body") or "")[:2000],
                        "author": (rel.get("author") or {}).get("login"),
                    }
                )
            return _ok(
                {"releases": releases},
                source="github_releases",
                repo=repo,
                count=len(releases),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GitHub 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GitHub 解析失败: {ex}")

    # ───────────────────────── 跨源统一搜索 ─────────────────────────
    def search_all_academic(self, query: str, per_source: int = 10) -> Dict:
        """跨学术源统一搜索 (arXiv + Semantic Scholar + OpenAlex + PubMed)"""
        results = {}
        try:
            results["arxiv"] = self.search_arxiv(query, max_results=per_source)
        except Exception as ex:
            results["arxiv"] = _err(str(ex))
        try:
            results["semantic_scholar"] = self.search_semantic_scholar(query, limit=per_source)
        except Exception as ex:
            results["semantic_scholar"] = _err(str(ex))
        try:
            results["openalex"] = self.search_openalex(query, per_page=per_source)
        except Exception as ex:
            results["openalex"] = _err(str(ex))
        try:
            results["pubmed"] = self.search_pubmed(query, max_results=per_source)
        except Exception as ex:
            results["pubmed"] = _err(str(ex))

        total = sum(
            len(((v.get("data") or {}).get("papers") or (v.get("data") or {}).get("works") or []))
            for v in results.values() if v.get("success")
        )
        return _ok(
            {"sources": results},
            query=query,
            total_papers=total,
            sources_attempted=list(results.keys()),
        )

    # ───────────────────────── 8. CrossRef ─────────────────────────
    def search_crossref(
        self,
        query: str,
        rows: int = 20,
        from_pub_date: Optional[str] = None,
        sort: str = "relevance",
    ) -> Dict:
        """CrossRef DOI 元数据 (1.5 亿条目, 完全免费无 key)"""
        try:
            params = {
                "query": query,
                "rows": max(1, min(int(rows), 100)),
                "sort": sort,
            }
            if from_pub_date:
                params["filter"] = f"from-pub-date:{from_pub_date}"
            r = self._get(
                "https://api.crossref.org/works",
                params=params,
                headers={"User-Agent": "Argus/6.6 (mailto:noreply@argus.local)"},
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("message", {}).get("items", [])
            works = []
            for w in items:
                title = (w.get("title") or [""])[0]
                works.append(
                    {
                        "doi": w.get("DOI"),
                        "title": title,
                        "type": w.get("type"),
                        "publisher": w.get("publisher"),
                        "container_title": (w.get("container-title") or [""])[0],
                        "published": (w.get("published-print") or w.get("published-online") or {}).get("date-parts"),
                        "url": w.get("URL"),
                        "is_referenced_by_count": w.get("is-referenced-by-count"),
                        "authors": [
                            f"{a.get('given', '')} {a.get('family', '')}".strip()
                            for a in (w.get("author") or [])
                        ][:8],
                        "abstract": w.get("abstract"),
                    }
                )
            return _ok(
                {"works": works},
                source="crossref",
                query=query,
                count=len(works),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"CrossRef 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"CrossRef 解析失败: {ex}")

    # ───────────────────────── 9. OpenReview ─────────────────────────
    def search_openreview(
        self,
        query: str,
        venue: Optional[str] = None,
        limit: int = 20,
    ) -> Dict:
        """OpenReview 论文 (NeurIPS/ICLR/ICML 等顶会的投稿与评审)"""
        try:
            params = {
                "term": query,
                "content": "all",
                "source": "all",
                "limit": max(1, min(int(limit), 100)),
            }
            if venue:
                params["group"] = venue
            r = self._get(
                "https://api2.openreview.net/notes/search",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json().get("notes", [])
            papers = []
            for n in data:
                content = n.get("content", {}) or {}
                # OpenReview 字段格式 {field: {value: actual}}
                def _v(k):
                    f = content.get(k)
                    if isinstance(f, dict):
                        return f.get("value", "")
                    return f or ""
                papers.append(
                    {
                        "id": n.get("id"),
                        "title": _v("title"),
                        "abstract": _v("abstract"),
                        "authors": _v("authors") if isinstance(_v("authors"), list) else [_v("authors")],
                        "venue": _v("venue"),
                        "pdf": f"https://openreview.net/pdf?id={n.get('id')}" if n.get("id") else "",
                        "forum_url": f"https://openreview.net/forum?id={n.get('id')}" if n.get("id") else "",
                        "tldr": _v("TL;DR") or _v("tldr"),
                        "keywords": _v("keywords") if isinstance(_v("keywords"), list) else [],
                    }
                )
            return _ok(
                {"papers": papers},
                source="openreview",
                query=query,
                venue=venue,
                count=len(papers),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"OpenReview 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"OpenReview 解析失败: {ex}")

    # ───────────────────────── 10. Wikipedia 趋势 ─────────────────────────
    def get_wikipedia_trending(
        self,
        project: str = "en.wikipedia",
        date: Optional[str] = None,
        limit: int = 25,
    ) -> Dict:
        """Wikipedia 当日热门文章 (按浏览量排序, 趋势检测利器)"""
        try:
            ua = {"User-Agent": "ArgusBot/1.0 (https://argus.local)"}
            # 默认从昨天开始往前回退最多 5 天 (Wikipedia 数据通常滞后 1-3 天)
            articles = None
            actual_date = None
            if date:
                candidates = [datetime.strptime(date, "%Y-%m-%d")]
            else:
                base = datetime.now(timezone.utc)
                candidates = [base - timedelta(days=i) for i in range(1, 6)]

            for d in candidates:
                url = (
                    f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
                    f"{project}/all-access/{d.year}/{d.month:02d}/{d.day:02d}"
                )
                r = self._get(url, timeout=15, headers=ua)
                if r.status_code == 200:
                    articles = r.json().get("items", [{}])[0].get("articles", [])
                    actual_date = d
                    break
            if articles is None:
                return _err(
                    "Wikipedia 最近 5 天均无数据 (API 通常滞后 1-3 天)",
                    code="NO_DATA",
                )
            top = []
            for a in articles[: max(1, min(int(limit), 100))]:
                article = a.get("article", "")
                if article in ("Main_Page", "Special:Search", "-"):
                    continue
                top.append(
                    {
                        "title": article.replace("_", " "),
                        "views": a.get("views"),
                        "rank": a.get("rank"),
                        "url": f"https://{project}.org/wiki/{article}",
                    }
                )
            return _ok(
                {"articles": top, "date": actual_date.strftime("%Y-%m-%d")},
                source="wikipedia_trending",
                project=project,
                count=len(top),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Wikipedia 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Wikipedia 解析失败: {ex}")

    # ───────────────────────── 11. Mastodon ─────────────────────────
    def search_mastodon(
        self,
        hashtag: Optional[str] = None,
        instance: str = "mastodon.social",
        limit: int = 20,
    ) -> Dict:
        """Mastodon 公开时间线 / 话题标签 (开放联邦, 无需 API key)

        Note:
            - 大多数实例(包括 mastodon.social)的全局公共时间线需要登录,
              因此推荐使用 hashtag 模式(无需登录)。
            - 也可以指定其他开放实例,如 mastodon.online、infosec.exchange 等。
        """
        try:
            limit = max(1, min(int(limit), 40))
            if hashtag:
                clean = hashtag.lstrip("#")
                url = f"https://{instance}/api/v1/timelines/tag/{clean}"
            else:
                # 不带 hashtag 时,只查本地时间线 (most public)
                url = f"https://{instance}/api/v1/timelines/public"
                # mastodon.social 已限制公共时间线,自动切到一个开放实例
                if instance == "mastodon.social":
                    url = "https://mastodon.online/api/v1/timelines/public?local=true"
            r = self._get(url, params={"limit": limit}, timeout=15)
            if r.status_code == 401 or r.status_code == 422:
                return _err(
                    f"该实例 ({instance}) 的公共时间线需要登录, 请改用 hashtag 模式",
                    code="AUTH_REQUIRED",
                )
            r.raise_for_status()
            data = r.json()
            posts = []
            for p in data:
                # 简单去 HTML 标签
                import re as _re
                content = _re.sub(r"<[^>]+>", "", p.get("content", "") or "")
                posts.append(
                    {
                        "id": p.get("id"),
                        "content": content[:500],
                        "url": p.get("url"),
                        "created_at": p.get("created_at"),
                        "favourites": p.get("favourites_count", 0),
                        "reblogs": p.get("reblogs_count", 0),
                        "replies": p.get("replies_count", 0),
                        "language": p.get("language"),
                        "account": (p.get("account") or {}).get("acct"),
                        "tags": [t.get("name") for t in (p.get("tags") or [])],
                    }
                )
            return _ok(
                {"posts": posts},
                source="mastodon",
                instance=instance,
                hashtag=hashtag,
                count=len(posts),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Mastodon 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Mastodon 解析失败: {ex}")

    # ───────────────────────── 12. Stack Exchange ─────────────────────────
    def search_stackexchange(
        self,
        query: str,
        site: str = "stackoverflow",
        sort: str = "votes",
        order: str = "desc",
        page_size: int = 20,
        tagged: Optional[List[str]] = None,
    ) -> Dict:
        """Stack Exchange 问答 (StackOverflow / SuperUser / AskUbuntu 等, 无 key 300/天)"""
        try:
            params = {
                "order": order,
                "sort": sort,
                "intitle": query,
                "site": site,
                "pagesize": max(1, min(int(page_size), 100)),
                "filter": "!nNPvSNdWme",  # 包含 body / answer_count / score
            }
            if tagged:
                params["tagged"] = ";".join(tagged)
            r = self._get(
                "https://api.stackexchange.com/2.3/search",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json().get("items", [])
            questions = []
            for q in data:
                questions.append(
                    {
                        "id": q.get("question_id"),
                        "title": q.get("title"),
                        "score": q.get("score", 0),
                        "answers": q.get("answer_count", 0),
                        "is_answered": q.get("is_answered"),
                        "view_count": q.get("view_count"),
                        "tags": q.get("tags", []),
                        "creation_date": datetime.fromtimestamp(
                            q.get("creation_date", 0), tz=timezone.utc
                        ).isoformat() if q.get("creation_date") else "",
                        "url": q.get("link"),
                        "owner": (q.get("owner") or {}).get("display_name"),
                    }
                )
            return _ok(
                {"questions": questions},
                source="stackexchange",
                site=site,
                query=query,
                count=len(questions),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Stack Exchange 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Stack Exchange 解析失败: {ex}")

    # ───────────────────────── 13. CoinGecko ─────────────────────────
    def get_crypto_trending(self, limit: int = 15) -> Dict:
        """CoinGecko 热门加密货币 (按搜索量, 完全免费无 key)"""
        try:
            r = self._get(
                "https://api.coingecko.com/api/v3/search/trending",
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            coins = []
            for c in data.get("coins", [])[: max(1, min(int(limit), 30))]:
                item = c.get("item", {})
                coins.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "symbol": item.get("symbol"),
                        "market_cap_rank": item.get("market_cap_rank"),
                        "price_btc": item.get("price_btc"),
                        "score": item.get("score"),
                        "thumb": item.get("thumb"),
                    }
                )
            nfts = data.get("nfts", [])[:5]
            categories = data.get("categories", [])[:5]
            return _ok(
                {"coins": coins, "nfts": nfts, "categories": categories},
                source="coingecko_trending",
                count=len(coins),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"CoinGecko 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"CoinGecko 解析失败: {ex}")

    # ───────────────────────── 14. SEC EDGAR ─────────────────────────
    def search_sec_edgar(
        self,
        query: Optional[str] = None,
        cik: Optional[str] = None,
        forms: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict:
        """SEC EDGAR 美股上市公司公开文件 (10-K/10-Q/8-K/13F 等, 完全免费)"""
        try:
            params = {"hits": max(1, min(int(limit), 100))}
            if query:
                params["q"] = query
            if cik:
                params["ciks"] = cik
            if forms:
                params["forms"] = ",".join(forms)
            # SEC 要求声明 User-Agent
            r = self._get(
                "https://efts.sec.gov/LATEST/search-index",
                params=params,
                headers={
                    "User-Agent": "Argus Research noreply@argus.local",
                },
                timeout=20,
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            filings = []
            for h in hits:
                src = h.get("_source", {})
                adsh = src.get("adsh", "")
                cik_clean = (src.get("ciks") or [""])[0]
                filings.append(
                    {
                        "form": src.get("form"),
                        "filed": src.get("file_date"),
                        "company": (src.get("display_names") or [""])[0],
                        "cik": cik_clean,
                        "description": src.get("file_description"),
                        "adsh": adsh,
                        "url": (
                            f"https://www.sec.gov/Archives/edgar/data/"
                            f"{int(cik_clean) if cik_clean else 0}/"
                            f"{adsh.replace('-', '')}/{adsh}-index.htm"
                            if adsh and cik_clean
                            else ""
                        ),
                    }
                )
            return _ok(
                {"filings": filings},
                source="sec_edgar",
                query=query,
                forms=forms,
                count=len(filings),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"SEC EDGAR 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"SEC EDGAR 解析失败: {ex}")

    # ───────────────────────── 15. YouTube 频道 (RSS) ─────────────────────────
    def get_youtube_channel(self, channel_id: str, limit: int = 15) -> Dict:
        """订阅 YouTube 频道最新视频 (官方 RSS, 无需 API key)

        channel_id 必须是以 'UC' 开头的 24 字符 ID, 不是用户名。
        从 YouTube 频道页面查看源代码搜索 'channelId' 可获取。
        """
        if not feedparser:
            return _err("feedparser 未安装", code="DEP_MISSING")
        try:
            r = self._get(
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                timeout=15,
            )
            if r.status_code == 404:
                return _err(f"频道 {channel_id} 不存在或未公开", code="NOT_FOUND")
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            videos = []
            for e in feed.entries[: max(1, min(int(limit), 30))]:
                videos.append(
                    {
                        "title": getattr(e, "title", ""),
                        "url": getattr(e, "link", ""),
                        "video_id": getattr(e, "yt_videoid", ""),
                        "published": getattr(e, "published", ""),
                        "author": getattr(e, "author", ""),
                        "description": (getattr(e, "summary", "") or "")[:500],
                    }
                )
            return _ok(
                {
                    "videos": videos,
                    "channel_title": feed.feed.get("title", "") if hasattr(feed, "feed") else "",
                },
                source="youtube_channel",
                channel_id=channel_id,
                count=len(videos),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"YouTube 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"YouTube 解析失败: {ex}")

    # ───────────────────────── 16. PyPI / NPM 包 ─────────────────────────
    def get_package_info(
        self,
        package: str,
        ecosystem: str = "pypi",
    ) -> Dict:
        """查询包仓库信息 (PyPI / NPM, 含版本/下载量趋势)"""
        try:
            ecosystem = ecosystem.lower()
            if ecosystem == "pypi":
                r = self._get(f"https://pypi.org/pypi/{package}/json", timeout=15)
                if r.status_code == 404:
                    return _err(f"PyPI 未找到 {package}", code="NOT_FOUND")
                r.raise_for_status()
                d = r.json()
                info = d.get("info", {})
                releases = list(d.get("releases", {}).keys())
                return _ok(
                    {
                        "name": info.get("name"),
                        "version": info.get("version"),
                        "summary": info.get("summary"),
                        "homepage": info.get("home_page"),
                        "project_urls": info.get("project_urls"),
                        "author": info.get("author"),
                        "license": info.get("license"),
                        "requires_python": info.get("requires_python"),
                        "release_count": len(releases),
                        "latest_releases": sorted(releases)[-10:],
                        "url": f"https://pypi.org/project/{package}/",
                    },
                    source="pypi",
                    package=package,
                )
            elif ecosystem == "npm":
                r = self._get(f"https://registry.npmjs.org/{package}", timeout=15)
                if r.status_code == 404:
                    return _err(f"NPM 未找到 {package}", code="NOT_FOUND")
                r.raise_for_status()
                d = r.json()
                latest = d.get("dist-tags", {}).get("latest", "")
                # 拿下载量
                stat = self._get(
                    f"https://api.npmjs.org/downloads/point/last-week/{package}",
                    timeout=10,
                )
                weekly = stat.json().get("downloads", 0) if stat.status_code == 200 else 0
                return _ok(
                    {
                        "name": d.get("name"),
                        "version": latest,
                        "description": d.get("description"),
                        "homepage": d.get("homepage"),
                        "license": d.get("license"),
                        "author": d.get("author"),
                        "keywords": d.get("keywords", []),
                        "downloads_last_week": weekly,
                        "release_count": len(d.get("versions", {})),
                        "url": f"https://www.npmjs.com/package/{package}",
                    },
                    source="npm",
                    package=package,
                )
            else:
                return _err(
                    f"暂不支持 ecosystem={ecosystem}, 可用: pypi / npm",
                    code="INVALID_PARAM",
                )
        except requests.exceptions.RequestException as ex:
            return _err(f"包仓库请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"包仓库解析失败: {ex}")

    # ───────────────────────── 17. Hugging Face Hub ─────────────────────────
    def search_huggingface(
        self,
        kind: str = "models",
        query: Optional[str] = None,
        sort: str = "downloads",
        direction: str = "-1",
        limit: int = 25,
        filter_tag: Optional[str] = None,
    ) -> Dict:
        """Hugging Face Hub - 模型/数据集/Spaces 趋势 (官方 API, 无需 key)"""
        try:
            kind = kind.lower()
            if kind not in ("models", "datasets", "spaces"):
                return _err("kind 必须是 models / datasets / spaces", code="INVALID_PARAM")
            params = {
                "sort": sort,                # downloads / likes / lastModified / createdAt
                "direction": direction,      # -1=desc, 1=asc
                "limit": max(1, min(int(limit), 100)),
            }
            if query:
                params["search"] = query
            if filter_tag:
                params["filter"] = filter_tag
            r = self._get(
                f"https://huggingface.co/api/{kind}",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            items = []
            for item in data:
                items.append(
                    {
                        "id": item.get("id") or item.get("modelId"),
                        "author": item.get("author"),
                        "downloads": item.get("downloads"),
                        "likes": item.get("likes"),
                        "tags": item.get("tags", [])[:10],
                        "pipeline_tag": item.get("pipeline_tag"),
                        "library_name": item.get("library_name"),
                        "created_at": item.get("createdAt"),
                        "last_modified": item.get("lastModified"),
                        "private": item.get("private"),
                        "url": f"https://huggingface.co/{item.get('id') or item.get('modelId') or ''}",
                    }
                )
            return _ok(
                {kind: items},
                source="huggingface",
                kind=kind,
                query=query,
                count=len(items),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"HuggingFace 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"HuggingFace 解析失败: {ex}")

    # ───────────────────────── 18. DBLP ─────────────────────────
    def search_dblp(
        self,
        query: str,
        kind: str = "publ",
        limit: int = 30,
    ) -> Dict:
        """DBLP 计算机科学文献库 (含会议论文 / 作者档案 / 完整元数据, 免费)"""
        try:
            kind = kind.lower()
            if kind not in ("publ", "author", "venue"):
                return _err("kind 必须是 publ / author / venue", code="INVALID_PARAM")
            r = self._get(
                f"https://dblp.org/search/{kind}/api",
                params={
                    "q": query,
                    "h": max(1, min(int(limit), 1000)),
                    "format": "json",
                },
                timeout=20,
            )
            r.raise_for_status()
            hits = (
                r.json()
                .get("result", {})
                .get("hits", {})
                .get("hit", [])
            )
            results = []
            for h in hits:
                info = h.get("info", {})
                if kind == "publ":
                    authors = info.get("authors", {}).get("author", [])
                    if isinstance(authors, dict):
                        authors = [authors]
                    results.append(
                        {
                            "title": info.get("title"),
                            "authors": [
                                a.get("text") if isinstance(a, dict) else a
                                for a in authors
                            ],
                            "venue": info.get("venue"),
                            "year": info.get("year"),
                            "type": info.get("type"),
                            "doi": info.get("doi"),
                            "url": info.get("url") or info.get("ee"),
                            "key": info.get("key"),
                        }
                    )
                elif kind == "author":
                    results.append(
                        {
                            "name": info.get("author"),
                            "url": info.get("url"),
                            "aliases": info.get("aliases", []),
                            "affiliation": info.get("notes", {}).get("note", {}),
                        }
                    )
                elif kind == "venue":
                    results.append(
                        {
                            "name": info.get("venue"),
                            "acronym": info.get("acronym"),
                            "type": info.get("type"),
                            "url": info.get("url"),
                        }
                    )
            return _ok(
                {kind: results},
                source="dblp",
                query=query,
                kind=kind,
                count=len(results),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"DBLP 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"DBLP 解析失败: {ex}")

    # ───────────────────────── 19. inspire-HEP ─────────────────────────
    def search_inspire_hep(
        self,
        query: str,
        sort: str = "mostrecent",
        size: int = 25,
    ) -> Dict:
        """inspire-HEP 高能物理论文库 (CERN 等机构维护, 免费)"""
        try:
            r = self._get(
                "https://inspirehep.net/api/literature",
                params={
                    "q": query,
                    "sort": sort,         # mostrecent / mostcited
                    "size": max(1, min(int(size), 100)),
                    "fields": "titles,authors,abstracts,publication_info,citation_count,arxiv_eprints,dois,texkeys",
                },
                timeout=20,
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            papers = []
            for h in hits:
                meta = h.get("metadata", {})
                titles = meta.get("titles", [{}])
                title = titles[0].get("title", "") if titles else ""
                authors = meta.get("authors", [])[:8]
                abstracts = meta.get("abstracts", [{}])
                abstract = abstracts[0].get("value", "") if abstracts else ""
                arxiv_id = ""
                eprints = meta.get("arxiv_eprints", [])
                if eprints:
                    arxiv_id = eprints[0].get("value", "")
                pub_info = meta.get("publication_info", [{}])[0] if meta.get("publication_info") else {}
                papers.append(
                    {
                        "id": h.get("id"),
                        "title": title,
                        "authors": [a.get("full_name", "") for a in authors],
                        "abstract": abstract[:500],
                        "journal": pub_info.get("journal_title"),
                        "year": pub_info.get("year"),
                        "citations": meta.get("citation_count"),
                        "arxiv_id": arxiv_id,
                        "doi": (meta.get("dois", [{}])[0] or {}).get("value", "") if meta.get("dois") else "",
                        "url": f"https://inspirehep.net/literature/{h.get('id')}",
                    }
                )
            return _ok(
                {"papers": papers},
                source="inspire_hep",
                query=query,
                count=len(papers),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"inspire-HEP 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"inspire-HEP 解析失败: {ex}")

    # ───────────────────────── 20. GDELT (全球事件数据库) ─────────────────────────
    def search_gdelt(
        self,
        query: str,
        timespan: str = "1d",
        max_records: int = 25,
        mode: str = "ArtList",
        sort: str = "DateDesc",
    ) -> Dict:
        """GDELT 全球新闻事件库 - 跨语言全球新闻 (1.5 亿+ 事件, 免费无 key)"""
        try:
            mode = mode if mode in ("ArtList", "TimelineVol", "TimelineTone", "ToneChart", "WordCloudEnglish") else "ArtList"
            params = {
                "query": query,
                "timespan": timespan,    # 1h / 24h / 1d / 7d / 1m / 3m / 1y
                "maxrecords": max(1, min(int(max_records), 250)),
                "mode": mode,
                "sort": sort,            # DateDesc / DateAsc / ToneDesc / ToneAsc / HybridRel
                "format": "json",
            }
            r = self._get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            try:
                data = r.json()
            except Exception:
                # GDELT 偶尔返回 HTML 错误页
                return _err(f"GDELT 返回非 JSON: {r.text[:200]}", code="PARSE_ERROR")
            articles = data.get("articles", [])
            results = []
            for a in articles:
                results.append(
                    {
                        "title": a.get("title"),
                        "url": a.get("url"),
                        "domain": a.get("domain"),
                        "language": a.get("language"),
                        "country": a.get("sourcecountry"),
                        "tone": a.get("tone"),       # 情感倾向 -10 ~ +10
                        "seendate": a.get("seendate"),
                        "social_image": a.get("socialimage"),
                    }
                )
            return _ok(
                {"articles": results},
                source="gdelt",
                query=query,
                timespan=timespan,
                count=len(results),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GDELT 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GDELT 解析失败: {ex}")

    # ───────────────────────── 21. CoinGecko 市场行情 ─────────────────────────
    def get_crypto_markets(
        self,
        vs_currency: str = "usd",
        per_page: int = 25,
        order: str = "market_cap_desc",
    ) -> Dict:
        """CoinGecko Top 币种市场数据 (价格/市值/24h 涨跌)"""
        try:
            r = self._get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": vs_currency,
                    "order": order,                # market_cap_desc / volume_desc / id_asc
                    "per_page": max(1, min(int(per_page), 250)),
                    "page": 1,
                    "sparkline": "false",
                    "price_change_percentage": "24h,7d,30d",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            coins = []
            for c in data:
                coins.append(
                    {
                        "id": c.get("id"),
                        "symbol": c.get("symbol"),
                        "name": c.get("name"),
                        "current_price": c.get("current_price"),
                        "market_cap": c.get("market_cap"),
                        "market_cap_rank": c.get("market_cap_rank"),
                        "total_volume": c.get("total_volume"),
                        "high_24h": c.get("high_24h"),
                        "low_24h": c.get("low_24h"),
                        "change_24h_pct": c.get("price_change_percentage_24h_in_currency"),
                        "change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
                        "change_30d_pct": c.get("price_change_percentage_30d_in_currency"),
                        "ath": c.get("ath"),
                        "ath_date": c.get("ath_date"),
                    }
                )
            return _ok(
                {"coins": coins, "vs_currency": vs_currency},
                source="coingecko_markets",
                count=len(coins),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"CoinGecko 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"CoinGecko 解析失败: {ex}")

    # ───────────────────────── 22. Hacker News Algolia 搜索 ─────────────────────────
    def search_hackernews(
        self,
        query: str,
        tags: Optional[str] = None,
        sort: str = "search",
        hits: int = 30,
    ) -> Dict:
        """通过 Algolia 搜索 HN 历史所有帖子/评论 (官方搜索引擎, 免费)"""
        try:
            params = {
                "query": query,
                "hitsPerPage": max(1, min(int(hits), 100)),
            }
            if tags:
                params["tags"] = tags    # story / comment / poll / show_hn / ask_hn / front_page
            base = "https://hn.algolia.com/api/v1"
            endpoint = f"{base}/search" if sort == "search" else f"{base}/search_by_date"
            r = self._get(endpoint, params=params, timeout=15)
            r.raise_for_status()
            data = r.json().get("hits", [])
            items = []
            for h in data:
                items.append(
                    {
                        "id": h.get("objectID"),
                        "title": h.get("title") or h.get("story_title"),
                        "url": h.get("url") or h.get("story_url"),
                        "author": h.get("author"),
                        "points": h.get("points"),
                        "num_comments": h.get("num_comments"),
                        "created_at": h.get("created_at"),
                        "type": h.get("_tags", [None])[0] if h.get("_tags") else None,
                        "comment_text": (h.get("comment_text") or "")[:500],
                        "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    }
                )
            return _ok(
                {"hits": items},
                source="hackernews_algolia",
                query=query,
                count=len(items),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"HN Algolia 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"HN Algolia 解析失败: {ex}")

    # ───────────────────────── 23. Wikipedia 搜索 ─────────────────────────
    def search_wikipedia(
        self,
        query: str,
        language: str = "en",
        limit: int = 10,
    ) -> Dict:
        """Wikipedia 文章搜索 + 摘要 (REST API, 免费)"""
        try:
            # Step 1: 搜索匹配条目
            r = self._get(
                f"https://{language}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": max(1, min(int(limit), 50)),
                },
                timeout=15,
            )
            r.raise_for_status()
            search = r.json().get("query", {}).get("search", [])
            articles = []
            for s in search:
                title = s.get("title", "")
                # 提取纯文本 snippet
                import re as _re
                snippet = _re.sub(r"<[^>]+>", "", s.get("snippet", "") or "")
                articles.append(
                    {
                        "title": title,
                        "snippet": snippet,
                        "wordcount": s.get("wordcount"),
                        "size": s.get("size"),
                        "timestamp": s.get("timestamp"),
                        "url": f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    }
                )
            return _ok(
                {"articles": articles},
                source="wikipedia",
                query=query,
                language=language,
                count=len(articles),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Wikipedia 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Wikipedia 解析失败: {ex}")

    # ───────────────────────── 24. GitHub 代码搜索 ─────────────────────────
    def search_github_code(
        self,
        query: str,
        limit: int = 20,
    ) -> Dict:
        """GitHub 代码搜索 (跨所有公开仓库)"""
        try:
            r = self._get(
                "https://api.github.com/search/code",
                params={
                    "q": query,
                    "per_page": max(1, min(int(limit), 100)),
                },
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
            )
            if r.status_code == 401 or r.status_code == 403:
                return _err(
                    "GitHub 代码搜索需要 GITHUB_TOKEN 环境变量 (匿名禁用)",
                    code="AUTH_REQUIRED",
                )
            r.raise_for_status()
            items = r.json().get("items", [])
            results = []
            for it in items:
                repo = it.get("repository", {}) or {}
                results.append(
                    {
                        "name": it.get("name"),
                        "path": it.get("path"),
                        "url": it.get("html_url"),
                        "repo": repo.get("full_name"),
                        "repo_url": repo.get("html_url"),
                        "language": (it.get("language") or repo.get("language")),
                        "score": it.get("score"),
                    }
                )
            return _ok(
                {"results": results},
                source="github_code",
                query=query,
                count=len(results),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GitHub 代码搜索失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GitHub 代码搜索解析失败: {ex}")

    # ───────────────────────── 25. NVD CVE 漏洞库 ─────────────────────────
    def search_cve(
        self,
        keyword: Optional[str] = None,
        cve_id: Optional[str] = None,
        days: int = 7,
        results_per_page: int = 25,
    ) -> Dict:
        """美国 NIST NVD 漏洞库 (CVE 实时数据, 安全情报必备, 免费)"""
        try:
            params = {
                "resultsPerPage": max(1, min(int(results_per_page), 100)),
            }
            if cve_id:
                params["cveId"] = cve_id
            elif keyword:
                params["keywordSearch"] = keyword
                # 默认时间窗
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=max(1, min(int(days), 120)))
                params["pubStartDate"] = start.strftime("%Y-%m-%dT00:00:00.000")
                params["pubEndDate"] = end.strftime("%Y-%m-%dT23:59:59.999")
            else:
                return _err("必须提供 keyword 或 cve_id", code="INVALID_PARAM")

            r = self._get(
                "https://services.nvd.nist.gov/rest/json/cves/2.0",
                params=params,
                timeout=25,
            )
            r.raise_for_status()
            vulns = r.json().get("vulnerabilities", [])
            cves = []
            for v in vulns:
                cve = v.get("cve", {})
                desc_list = cve.get("descriptions", [])
                desc = next(
                    (d.get("value") for d in desc_list if d.get("lang") == "en"),
                    desc_list[0].get("value") if desc_list else "",
                )
                metrics = cve.get("metrics", {}) or {}
                cvss = (
                    metrics.get("cvssMetricV31")
                    or metrics.get("cvssMetricV30")
                    or metrics.get("cvssMetricV2")
                    or [{}]
                )[0].get("cvssData", {})
                cves.append(
                    {
                        "id": cve.get("id"),
                        "published": cve.get("published"),
                        "modified": cve.get("lastModified"),
                        "description": (desc or "")[:600],
                        "severity": cvss.get("baseSeverity"),
                        "score": cvss.get("baseScore"),
                        "vector": cvss.get("vectorString"),
                        "url": f"https://nvd.nist.gov/vuln/detail/{cve.get('id')}",
                        "references": [
                            r2.get("url") for r2 in (cve.get("references") or [])[:5]
                        ],
                    }
                )
            return _ok(
                {"cves": cves},
                source="nvd_cve",
                keyword=keyword,
                cve_id=cve_id,
                count=len(cves),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"NVD CVE 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"NVD CVE 解析失败: {ex}")

    # ───────────────────────── 26. USGS 地震 ─────────────────────────
    def get_earthquakes(
        self,
        period: str = "day",
        min_magnitude: str = "significant",
        limit: int = 50,
    ) -> Dict:
        """USGS 全球地震实时数据 (官方权威, 完全免费)"""
        try:
            allowed_period = {"hour", "day", "week", "month"}
            allowed_mag = {"significant", "4.5", "2.5", "1.0", "all"}
            if period not in allowed_period:
                return _err(f"period 必须是 {allowed_period}", code="INVALID_PARAM")
            if min_magnitude not in allowed_mag:
                return _err(f"min_magnitude 必须是 {allowed_mag}", code="INVALID_PARAM")
            url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{min_magnitude}_{period}.geojson"
            r = self._get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            features = data.get("features", [])[: max(1, min(int(limit), 200))]
            quakes = []
            for f in features:
                p = f.get("properties", {}) or {}
                geo = (f.get("geometry") or {}).get("coordinates", [None, None, None])
                quakes.append(
                    {
                        "id": f.get("id"),
                        "mag": p.get("mag"),
                        "place": p.get("place"),
                        "time": datetime.fromtimestamp(
                            (p.get("time") or 0) / 1000, tz=timezone.utc
                        ).isoformat() if p.get("time") else "",
                        "tsunami": bool(p.get("tsunami")),
                        "alert": p.get("alert"),
                        "felt_reports": p.get("felt"),
                        "depth_km": geo[2] if len(geo) > 2 else None,
                        "longitude": geo[0],
                        "latitude": geo[1],
                        "url": p.get("url"),
                    }
                )
            return _ok(
                {"earthquakes": quakes,
                 "metadata": {"count": data.get("metadata", {}).get("count")}},
                source="usgs_earthquake",
                period=period,
                min_magnitude=min_magnitude,
                count=len(quakes),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"USGS 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"USGS 解析失败: {ex}")

    # ───────────────────────── 27. NASA APOD + 近地小行星 ─────────────────────────
    def get_nasa_data(
        self,
        kind: str = "apod",
        date: Optional[str] = None,
        days: int = 1,
    ) -> Dict:
        """NASA 公开数据 (APOD 每日天文图 / NeoWs 近地小行星)

        Args:
            kind: apod (Astronomy Picture of the Day) / neo (Near Earth Objects)
            date: 指定日期 YYYY-MM-DD (apod 模式) 或 起始日期 (neo 模式)
            days: neo 模式查询天数, 默认 1, 最大 7
        """
        try:
            kind = kind.lower()
            if kind == "apod":
                params = {"api_key": "DEMO_KEY"}
                if date:
                    params["date"] = date
                r = self._get("https://api.nasa.gov/planetary/apod", params=params, timeout=30)
                r.raise_for_status()
                d = r.json()
                return _ok(
                    {
                        "title": d.get("title"),
                        "date": d.get("date"),
                        "explanation": d.get("explanation"),
                        "media_type": d.get("media_type"),
                        "url": d.get("url"),
                        "hdurl": d.get("hdurl"),
                        "copyright": d.get("copyright"),
                    },
                    source="nasa_apod",
                )
            elif kind == "neo":
                today = datetime.now(timezone.utc).date()
                start = datetime.strptime(date, "%Y-%m-%d").date() if date else today
                end = start + timedelta(days=max(0, min(int(days) - 1, 6)))
                r = self._get(
                    "https://api.nasa.gov/neo/rest/v1/feed",
                    params={
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "api_key": "DEMO_KEY",
                    },
                    timeout=20,
                )
                r.raise_for_status()
                d = r.json()
                neos = []
                for date_str, items in (d.get("near_earth_objects") or {}).items():
                    for n in items:
                        diameter = (n.get("estimated_diameter") or {}).get("meters", {})
                        ca = (n.get("close_approach_data") or [{}])[0]
                        neos.append(
                            {
                                "id": n.get("id"),
                                "name": n.get("name"),
                                "date": date_str,
                                "is_hazardous": n.get("is_potentially_hazardous_asteroid"),
                                "diameter_m_min": diameter.get("estimated_diameter_min"),
                                "diameter_m_max": diameter.get("estimated_diameter_max"),
                                "miss_distance_km": (ca.get("miss_distance") or {}).get("kilometers"),
                                "velocity_kmh": (ca.get("relative_velocity") or {}).get("kilometers_per_hour"),
                                "url": n.get("nasa_jpl_url"),
                            }
                        )
                return _ok(
                    {"neos": neos, "element_count": d.get("element_count")},
                    source="nasa_neo",
                    count=len(neos),
                )
            else:
                return _err("kind 必须是 apod / neo", code="INVALID_PARAM")
        except requests.exceptions.RequestException as ex:
            return _err(f"NASA 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"NASA 解析失败: {ex}")

    # ───────────────────────── 28. Open-Meteo 天气 ─────────────────────────
    def get_weather(
        self,
        latitude: float,
        longitude: float,
        days: int = 3,
        timezone_str: str = "auto",
    ) -> Dict:
        """全球天气预报 + 当前观测 (Open-Meteo, 完全免费无 key)"""
        try:
            r = self._get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
                    "forecast_days": max(1, min(int(days), 16)),
                    "timezone": timezone_str,
                },
                timeout=15,
            )
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "location": {
                        "latitude": d.get("latitude"),
                        "longitude": d.get("longitude"),
                        "elevation": d.get("elevation"),
                        "timezone": d.get("timezone"),
                    },
                    "current": d.get("current"),
                    "daily": d.get("daily"),
                },
                source="open_meteo",
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Open-Meteo 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Open-Meteo 解析失败: {ex}")

    # ───────────────────────── 29. Wikidata 知识图谱 ─────────────────────────
    def query_wikidata(
        self,
        sparql: Optional[str] = None,
        search: Optional[str] = None,
        language: str = "en",
        limit: int = 20,
    ) -> Dict:
        """Wikidata SPARQL 查询 (10 亿+ 三元组结构化知识库)

        两种模式:
            1. sparql: 直接传 SPARQL 查询语句
            2. search: 简单关键词搜索实体 (走 wbsearchentities)
        """
        try:
            if sparql:
                r = self._get(
                    "https://query.wikidata.org/sparql",
                    params={"query": sparql, "format": "json"},
                    headers={"Accept": "application/sparql-results+json"},
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
                bindings = data.get("results", {}).get("bindings", [])
                rows = []
                for b in bindings[: max(1, min(int(limit), 500))]:
                    row = {k: v.get("value") for k, v in b.items()}
                    rows.append(row)
                return _ok(
                    {"rows": rows, "vars": data.get("head", {}).get("vars", [])},
                    source="wikidata_sparql",
                    count=len(rows),
                )
            elif search:
                r = self._get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbsearchentities",
                        "search": search,
                        "language": language,
                        "format": "json",
                        "limit": max(1, min(int(limit), 50)),
                    },
                    timeout=15,
                )
                r.raise_for_status()
                items = r.json().get("search", [])
                entities = [
                    {
                        "id": e.get("id"),
                        "label": e.get("label"),
                        "description": e.get("description"),
                        "url": e.get("concepturi"),
                    }
                    for e in items
                ]
                return _ok(
                    {"entities": entities},
                    source="wikidata_search",
                    query=search,
                    count=len(entities),
                )
            else:
                return _err("必须提供 sparql 或 search 参数", code="INVALID_PARAM")
        except requests.exceptions.RequestException as ex:
            return _err(f"Wikidata 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Wikidata 解析失败: {ex}")

    # ───────────────────────── 30. Bluesky 公共时间线 ─────────────────────────
    def search_bluesky(
        self,
        query: str,
        limit: int = 25,
        sort: str = "latest",
    ) -> Dict:
        """Bluesky AT Protocol 公共帖子搜索 (无需登录, 公开端点)"""
        try:
            r = self._get(
                "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={
                    "q": query,
                    "limit": max(1, min(int(limit), 100)),
                    "sort": sort,           # latest / top
                },
                timeout=15,
            )
            r.raise_for_status()
            posts_raw = r.json().get("posts", [])
            posts = []
            for p in posts_raw:
                rec = p.get("record", {}) or {}
                author = p.get("author", {}) or {}
                posts.append(
                    {
                        "uri": p.get("uri"),
                        "cid": p.get("cid"),
                        "text": rec.get("text", ""),
                        "created_at": rec.get("createdAt"),
                        "author": author.get("handle"),
                        "display_name": author.get("displayName"),
                        "likes": p.get("likeCount"),
                        "reposts": p.get("repostCount"),
                        "replies": p.get("replyCount"),
                        "url": (
                            f"https://bsky.app/profile/{author.get('handle', '')}/post/"
                            f"{p.get('uri', '').split('/')[-1]}"
                            if author.get("handle") and p.get("uri")
                            else ""
                        ),
                    }
                )
            return _ok(
                {"posts": posts},
                source="bluesky",
                query=query,
                count=len(posts),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Bluesky 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Bluesky 解析失败: {ex}")

    # ───────────────────────── 31. Internet Archive Wayback ─────────────────────────
    def get_wayback(self, url: str, timestamp: Optional[str] = None) -> Dict:
        """Internet Archive Wayback Machine - 查询任意 URL 历史快照

        Args:
            url: 目标 URL
            timestamp: 优先靠近的时间戳 YYYYMMDD 或 YYYYMMDDhhmmss, 默认最近
        """
        try:
            params = {"url": url}
            if timestamp:
                params["timestamp"] = timestamp
            r = self._get(
                "https://archive.org/wayback/available",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            d = r.json()
            snap = d.get("archived_snapshots", {}).get("closest", {})
            if not snap.get("available"):
                return _ok(
                    {"available": False, "url": url},
                    source="wayback",
                    note="无快照",
                )
            return _ok(
                {
                    "available": True,
                    "snapshot_url": snap.get("url"),
                    "timestamp": snap.get("timestamp"),
                    "status": snap.get("status"),
                    "original_url": url,
                },
                source="wayback",
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Wayback 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Wayback 解析失败: {ex}")

    # ───────────────────────── 32. World Bank ─────────────────────────
    def get_worldbank_indicator(
        self,
        country: str,
        indicator: str = "NY.GDP.MKTP.CD",
        years: int = 10,
    ) -> Dict:
        """World Bank 国家经济/社会指标 (200+ 国家, 完全免费)

        Args:
            country: ISO2 国家代码 (CN/US/JP) 或 'all'
            indicator: 指标代码,常用:
                - NY.GDP.MKTP.CD: GDP (美元)
                - NY.GDP.PCAP.CD: 人均 GDP
                - SP.POP.TOTL: 总人口
                - SL.UEM.TOTL.ZS: 失业率
                - FP.CPI.TOTL.ZG: 通胀率
                - EN.ATM.CO2E.PC: 人均 CO2 排放
                完整列表: https://data.worldbank.org/indicator
            years: 回溯年数, 默认 10
        """
        try:
            current_year = datetime.now().year
            r = self._get(
                f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}",
                params={
                    "format": "json",
                    "date": f"{current_year - years}:{current_year}",
                    "per_page": 100,
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) < 2:
                return _err("World Bank 返回异常", code="PARSE_ERROR")
            meta, rows = data[0], data[1]
            cleaned = []
            for r0 in rows or []:
                if r0.get("value") is not None:
                    cleaned.append(
                        {
                            "country": (r0.get("country") or {}).get("value"),
                            "country_code": (r0.get("country") or {}).get("id"),
                            "year": r0.get("date"),
                            "value": r0.get("value"),
                            "indicator": (r0.get("indicator") or {}).get("value"),
                        }
                    )
            return _ok(
                {"data": cleaned, "page_meta": meta},
                source="worldbank",
                country=country,
                indicator=indicator,
                count=len(cleaned),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"World Bank 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"World Bank 解析失败: {ex}")

    # ───────────────────────── 33. PyPiStats 下载趋势 ─────────────────────────
    def get_pypi_stats(self, package: str, period: str = "recent") -> Dict:
        """PyPI 包下载量趋势 (pypistats.org, 免费 BigQuery 镜像)

        Args:
            package: 包名
            period: recent (最近 1天/1周/1月) / overall (历史总量)
        """
        try:
            if period not in ("recent", "overall"):
                return _err("period 必须是 recent / overall", code="INVALID_PARAM")
            r = self._get(
                f"https://pypistats.org/api/packages/{package}/{period}",
                timeout=15,
            )
            if r.status_code == 404:
                return _err(f"PyPI 未找到 {package}", code="NOT_FOUND")
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "package": d.get("package"),
                    "type": d.get("type"),
                    "data": d.get("data"),
                },
                source="pypistats",
                period=period,
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"PyPiStats 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"PyPiStats 解析失败: {ex}")

    # ───────────────────────── 34. Lobsters API ─────────────────────────
    def get_lobsters(self, kind: str = "hottest", page: int = 1) -> Dict:
        """Lobsters 技术社区 (高质量小众, 比 HN 更专业, 公开 JSON)"""
        try:
            kind = kind.lower()
            if kind not in ("hottest", "newest", "active"):
                return _err("kind 必须是 hottest / newest / active", code="INVALID_PARAM")
            r = self._get(
                f"https://lobste.rs/{kind}.json",
                params={"page": max(1, int(page))},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            stories = []
            for s in data:
                stories.append(
                    {
                        "short_id": s.get("short_id"),
                        "title": s.get("title"),
                        "url": s.get("url"),
                        "score": s.get("score"),
                        "comments_count": s.get("comment_count"),
                        "tags": s.get("tags", []),
                        "submitter": (
                            s.get("submitter_user", {}).get("username")
                            if isinstance(s.get("submitter_user"), dict)
                            else s.get("submitter_user")
                        ),
                        "created_at": s.get("created_at"),
                        "comments_url": s.get("comments_url"),
                    }
                )
            return _ok(
                {"stories": stories},
                source="lobsters",
                kind=kind,
                count=len(stories),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Lobsters 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Lobsters 解析失败: {ex}")

    # ───────────────────────── 35. GitHub Security Advisory ─────────────────────────
    def search_ghsa(
        self,
        query: Optional[str] = None,
        ecosystem: Optional[str] = None,
        severity: Optional[str] = None,
        per_page: int = 25,
    ) -> Dict:
        """GitHub Advisory Database - 开源生态安全公告 (GHSA, 免费无 key)"""
        try:
            params = {"per_page": max(1, min(int(per_page), 100))}
            if query:
                # GHSA REST API 不直接支持全文,用 cve 或 summary 参数拼
                params["cve_id"] = query if query.upper().startswith("CVE-") else None
                if not params["cve_id"]:
                    params.pop("cve_id")
            if ecosystem:
                params["ecosystem"] = ecosystem    # composer/go/maven/npm/nuget/pip/pub/rubygems/rust/actions
            if severity:
                params["severity"] = severity      # unknown/low/medium/high/critical
            r = self._get(
                "https://api.github.com/advisories",
                params=params,
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
            )
            if r.status_code in (401, 403):
                return _err(
                    "GHSA 建议设置 GITHUB_TOKEN 提高配额",
                    code="AUTH_REQUIRED",
                )
            r.raise_for_status()
            items = r.json()
            advisories = []
            # 若 query 非 CVE 且存在, 在结果里做本地过滤
            q_lower = (query or "").lower()
            for a in items:
                summary = a.get("summary", "") or ""
                if query and not q_lower.startswith("cve-") and q_lower not in summary.lower():
                    continue
                vulns = [
                    {
                        "package": (v.get("package") or {}).get("name"),
                        "ecosystem": (v.get("package") or {}).get("ecosystem"),
                        "patched": v.get("patched_versions"),
                        "vulnerable": v.get("vulnerable_version_range"),
                    }
                    for v in (a.get("vulnerabilities") or [])[:5]
                ]
                advisories.append(
                    {
                        "ghsa_id": a.get("ghsa_id"),
                        "cve_id": a.get("cve_id"),
                        "summary": summary,
                        "severity": a.get("severity"),
                        "cvss_score": (a.get("cvss") or {}).get("score"),
                        "published_at": a.get("published_at"),
                        "url": a.get("html_url"),
                        "vulnerabilities": vulns,
                        "references": (a.get("references") or [])[:5],
                    }
                )
            return _ok(
                {"advisories": advisories},
                source="ghsa",
                query=query,
                ecosystem=ecosystem,
                count=len(advisories),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GHSA 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GHSA 解析失败: {ex}")

    # ───────────────────────── 36. Open Library ─────────────────────────
    def search_books(
        self,
        query: str,
        limit: int = 20,
        fields: str = "key,title,author_name,first_publish_year,subject,isbn,language",
    ) -> Dict:
        """Open Library 图书搜索 (Internet Archive 维护, 4000 万+ 书目, 免费)"""
        try:
            r = self._get(
                "https://openlibrary.org/search.json",
                params={
                    "q": query,
                    "limit": max(1, min(int(limit), 100)),
                    "fields": fields,
                },
                timeout=20,
            )
            r.raise_for_status()
            docs = r.json().get("docs", [])
            books = []
            for d in docs:
                key = d.get("key", "")
                books.append(
                    {
                        "title": d.get("title"),
                        "authors": d.get("author_name", [])[:5],
                        "first_publish_year": d.get("first_publish_year"),
                        "subjects": (d.get("subject") or [])[:10],
                        "isbn": (d.get("isbn") or [])[:3],
                        "languages": d.get("language", []),
                        "url": f"https://openlibrary.org{key}" if key else "",
                    }
                )
            return _ok(
                {"books": books},
                source="open_library",
                query=query,
                count=len(books),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Open Library 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Open Library 解析失败: {ex}")

    # ───────────────────────── 37. Crates.io ─────────────────────────
    def search_crates(
        self,
        query: Optional[str] = None,
        sort: str = "downloads",
        per_page: int = 25,
    ) -> Dict:
        """Crates.io Rust 包仓库搜索 / 热门"""
        try:
            params = {
                "per_page": max(1, min(int(per_page), 100)),
                "sort": sort,       # alpha / downloads / recent-downloads / recent-updates / new
            }
            if query:
                params["q"] = query
            r = self._get(
                "https://crates.io/api/v1/crates",
                params=params,
                headers={"User-Agent": "Argus/6.6 (noreply@argus.local)"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            crates = []
            for c in data.get("crates", []):
                crates.append(
                    {
                        "name": c.get("name"),
                        "version": c.get("max_version"),
                        "description": c.get("description"),
                        "downloads": c.get("downloads"),
                        "recent_downloads": c.get("recent_downloads"),
                        "created_at": c.get("created_at"),
                        "updated_at": c.get("updated_at"),
                        "keywords": c.get("keywords", []),
                        "categories": c.get("categories", []),
                        "url": f"https://crates.io/crates/{c.get('name')}",
                        "homepage": c.get("homepage"),
                        "repository": c.get("repository"),
                    }
                )
            return _ok(
                {"crates": crates, "total": data.get("meta", {}).get("total")},
                source="crates_io",
                query=query,
                sort=sort,
                count=len(crates),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Crates.io 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Crates.io 解析失败: {ex}")

    # ───────────────────────── 38. Docker Hub ─────────────────────────
    def search_docker_hub(
        self,
        query: str,
        limit: int = 25,
        is_official: Optional[bool] = None,
    ) -> Dict:
        """Docker Hub 镜像搜索 (容器镜像仓库, 免费)"""
        try:
            params = {
                "query": query,
                "page_size": max(1, min(int(limit), 100)),
                "page": 1,
            }
            r = self._get(
                "https://hub.docker.com/v2/search/repositories/",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            images = []
            for img in data.get("results", []):
                if is_official is not None and img.get("is_official") != is_official:
                    continue
                images.append(
                    {
                        "name": img.get("repo_name"),
                        "description": img.get("short_description"),
                        "stars": img.get("star_count"),
                        "pulls": img.get("pull_count"),
                        "is_official": img.get("is_official"),
                        "is_automated": img.get("is_automated"),
                        "url": f"https://hub.docker.com/r/{img.get('repo_name')}",
                    }
                )
            return _ok(
                {"images": images, "count_total": data.get("count")},
                source="docker_hub",
                query=query,
                count=len(images),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Docker Hub 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Docker Hub 解析失败: {ex}")

    # ───────────────────────── 39. ReliefWeb (UN 人道主义) ─────────────────────────
    def search_reliefweb(
        self,
        query: Optional[str] = None,
        kind: str = "reports",
        limit: int = 25,
        appname: str = "argus",
    ) -> Dict:
        """ReliefWeb - UN OCHA 人道主义与灾难事件库

        注意: 2025 年起 ReliefWeb v2 API 要求注册 appname,
        前往 https://apidoc.reliefweb.int/ 免费注册后, 通过 appname 参数传入。
        """
        try:
            kind = kind.lower()
            if kind not in ("reports", "disasters", "jobs", "training", "countries"):
                return _err("kind 必须是 reports / disasters / jobs / training / countries", code="INVALID_PARAM")
            body = {
                "limit": max(1, min(int(limit), 100)),
                "sort": ["date:desc"],
                "profile": "list",
            }
            if query:
                body["query"] = {"value": query, "operator": "AND"}
            r = self.session.post(
                f"https://api.reliefweb.int/v2/{kind}?appname={appname}",
                json=body,
                timeout=20,
            )
            if r.status_code == 403:
                return _err(
                    "ReliefWeb 需要已登记的 appname, 免费注册: "
                    "https://apidoc.reliefweb.int/ (只需提供项目名+邮箱)",
                    code="AUTH_REQUIRED",
                )
            r.raise_for_status()
            items = r.json().get("data", [])
            results = []
            for it in items:
                f = it.get("fields", {}) or {}
                results.append(
                    {
                        "id": it.get("id"),
                        "title": f.get("title") or f.get("name"),
                        "date": (f.get("date") or {}).get("created")
                                or (f.get("date") or {}).get("original"),
                        "status": f.get("status"),
                        "country": [c.get("name") for c in (f.get("country") or [])][:5],
                        "source": [s.get("name") for s in (f.get("source") or [])][:3],
                        "disaster_type": [d.get("name") for d in (f.get("type") or [])],
                        "url": f.get("url") or it.get("href"),
                    }
                )
            return _ok(
                {kind: results},
                source="reliefweb",
                kind=kind,
                query=query,
                count=len(results),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"ReliefWeb 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"ReliefWeb 解析失败: {ex}")

    # ───────────────────────── 40. Frankfurter (ECB 汇率) ─────────────────────────
    def get_exchange_rates(
        self,
        base: str = "USD",
        symbols: Optional[List[str]] = None,
        date: Optional[str] = None,
    ) -> Dict:
        """Frankfurter 汇率 (欧洲央行数据, 完全免费无 key, 含历史)"""
        try:
            # date = None → latest; 或 YYYY-MM-DD
            path = date if date else "latest"
            params = {"from": base.upper()}
            if symbols:
                params["to"] = ",".join(s.upper() for s in symbols)
            r = self._get(
                f"https://api.frankfurter.app/{path}",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "base": d.get("base"),
                    "date": d.get("date"),
                    "rates": d.get("rates", {}),
                },
                source="frankfurter",
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Frankfurter 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Frankfurter 解析失败: {ex}")

    # ───────────────────────── 41. JSR (JavaScript Registry) ─────────────────────────
    def search_jsr(self, query: str, limit: int = 20) -> Dict:
        """JSR (JavaScript Registry) 包搜索 (Deno 团队运营, 新一代 JS 仓库)"""
        try:
            r = self._get(
                "https://api.jsr.io/packages",
                params={
                    "query": query,
                    "limit": max(1, min(int(limit), 100)),
                },
                timeout=15,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            packages = []
            for p in items:
                packages.append(
                    {
                        "scope": p.get("scope"),
                        "name": p.get("name"),
                        "latest_version": p.get("latestVersion"),
                        "description": p.get("description"),
                        "runtime_compat": p.get("runtimeCompat"),
                        "github_url": p.get("githubRepository"),
                        "score": p.get("score"),
                        "updated_at": p.get("updatedAt"),
                        "url": f"https://jsr.io/@{p.get('scope')}/{p.get('name')}",
                    }
                )
            return _ok(
                {"packages": packages},
                source="jsr",
                query=query,
                count=len(packages),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"JSR 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"JSR 解析失败: {ex}")

    # ───────────────────────── 42. Lemmy ─────────────────────────
    def search_lemmy(
        self,
        query: str,
        instance: str = "lemmy.world",
        type_: str = "All",
        sort: str = "TopDay",
        limit: int = 25,
    ) -> Dict:
        """Lemmy 联邦社区搜索 (开源 Reddit 替代, 免费)"""
        try:
            if type_ not in ("All", "Comments", "Posts", "Communities", "Users", "Url"):
                return _err("type_ 无效", code="INVALID_PARAM")
            r = self._get(
                f"https://{instance}/api/v3/search",
                params={
                    "q": query,
                    "type_": type_,
                    "sort": sort,
                    "limit": max(1, min(int(limit), 50)),
                },
                timeout=20,
            )
            r.raise_for_status()
            d = r.json()
            posts = []
            for pv in d.get("posts", [])[:limit]:
                post = pv.get("post", {}) or {}
                counts = pv.get("counts", {}) or {}
                community = pv.get("community", {}) or {}
                posts.append(
                    {
                        "id": post.get("id"),
                        "title": post.get("name"),
                        "url": post.get("url") or post.get("ap_id"),
                        "body": (post.get("body") or "")[:400],
                        "community": community.get("name"),
                        "community_title": community.get("title"),
                        "published": post.get("published"),
                        "score": counts.get("score"),
                        "comments": counts.get("comments"),
                        "nsfw": post.get("nsfw"),
                    }
                )
            return _ok(
                {
                    "posts": posts,
                    "communities": [c.get("community", {}).get("name") for c in d.get("communities", [])[:10]],
                },
                source="lemmy",
                instance=instance,
                query=query,
                count=len(posts),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Lemmy 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Lemmy 解析失败: {ex}")

    # ───────────────────────── 43. CoinPaprika ─────────────────────────
    def get_crypto_details(
        self,
        coin_id: str = "btc-bitcoin",
    ) -> Dict:
        """CoinPaprika 加密货币详情 (免费替代 CoinGecko, 包含更多历史统计)

        coin_id 格式: 'btc-bitcoin' / 'eth-ethereum' / 'sol-solana' 等
        """
        try:
            # Get coin info
            r = self._get(
                f"https://api.coinpaprika.com/v1/coins/{coin_id}",
                timeout=15,
            )
            if r.status_code == 404:
                return _err(f"未找到 coin_id={coin_id}", code="NOT_FOUND")
            r.raise_for_status()
            info = r.json()
            # Get market ticker
            tick = self._get(
                f"https://api.coinpaprika.com/v1/tickers/{coin_id}",
                timeout=15,
            )
            ticker = tick.json() if tick.status_code == 200 else {}
            q_usd = (ticker.get("quotes") or {}).get("USD", {})
            return _ok(
                {
                    "id": info.get("id"),
                    "name": info.get("name"),
                    "symbol": info.get("symbol"),
                    "rank": info.get("rank"),
                    "type": info.get("type"),
                    "description": (info.get("description") or "")[:500],
                    "started_at": info.get("started_at"),
                    "development_status": info.get("development_status"),
                    "open_source": info.get("open_source"),
                    "links": info.get("links"),
                    "tags": [t.get("name") for t in (info.get("tags") or [])[:10]],
                    "market": {
                        "price_usd": q_usd.get("price"),
                        "volume_24h_usd": q_usd.get("volume_24h"),
                        "market_cap_usd": q_usd.get("market_cap"),
                        "change_1h_pct": q_usd.get("percent_change_1h"),
                        "change_24h_pct": q_usd.get("percent_change_24h"),
                        "change_7d_pct": q_usd.get("percent_change_7d"),
                        "change_30d_pct": q_usd.get("percent_change_30d"),
                        "change_1y_pct": q_usd.get("percent_change_1y"),
                        "ath_price": q_usd.get("ath_price"),
                        "ath_date": q_usd.get("ath_date"),
                    },
                    "url": f"https://coinpaprika.com/coin/{coin_id}/",
                },
                source="coinpaprika",
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"CoinPaprika 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"CoinPaprika 解析失败: {ex}")

    # ───────────────────────── 44. GitLab ─────────────────────────
    def search_gitlab(
        self,
        query: str,
        scope: str = "projects",
        order_by: str = "stars_count",
        per_page: int = 25,
    ) -> Dict:
        """GitLab.com 公开项目搜索 (GitHub 的开源替代)"""
        try:
            if scope not in ("projects", "issues", "merge_requests", "milestones", "snippet_titles", "users", "groups"):
                return _err("scope 无效", code="INVALID_PARAM")
            # GitLab 只支持 id/name/path/created_at/updated_at/last_activity_at/similarity 等
            _allowed_order = {"id", "name", "path", "created_at", "updated_at", "last_activity_at", "similarity"}
            ob = order_by if order_by in _allowed_order else "last_activity_at"
            r = self._get(
                "https://gitlab.com/api/v4/projects",
                params={
                    "search": query,
                    "order_by": ob,
                    "sort": "desc",
                    "per_page": max(1, min(int(per_page), 100)),
                    "visibility": "public",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            projects = []
            for p in data:
                projects.append(
                    {
                        "id": p.get("id"),
                        "name": p.get("name_with_namespace"),
                        "path": p.get("path_with_namespace"),
                        "description": p.get("description"),
                        "star_count": p.get("star_count"),
                        "forks_count": p.get("forks_count"),
                        "created_at": p.get("created_at"),
                        "last_activity_at": p.get("last_activity_at"),
                        "language": p.get("default_branch"),
                        "topics": p.get("topics", []),
                        "url": p.get("web_url"),
                    }
                )
            return _ok(
                {"projects": projects},
                source="gitlab",
                query=query,
                count=len(projects),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"GitLab 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"GitLab 解析失败: {ex}")

    # ───────────────────────── 45. Homebrew ─────────────────────────
    def search_homebrew(
        self,
        query: str,
        kind: str = "formula",
        limit: int = 20,
    ) -> Dict:
        """Homebrew 软件包搜索 (macOS / Linux, 免费, 官方 JSON)"""
        try:
            kind = kind.lower()
            if kind not in ("formula", "cask"):
                return _err("kind 必须是 formula / cask", code="INVALID_PARAM")
            # Homebrew 没有官方搜索 API, 用 formulae.brew.sh 下载全量 index 做本地过滤
            url = (
                "https://formulae.brew.sh/api/formula.json"
                if kind == "formula"
                else "https://formulae.brew.sh/api/cask.json"
            )
            r = self._get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            q_lower = query.lower()
            results = []
            for item in data:
                # formula: name=str; cask: name=list, token=str
                if kind == "formula":
                    primary = (item.get("name") or "") or ""
                    name_field = primary
                else:
                    primary = item.get("token") or ""
                    _name = item.get("name")
                    name_field = _name[0] if isinstance(_name, list) and _name else (_name or primary)
                desc = item.get("desc") or ""
                # 过滤条件 (所有字段全部字符串化)
                hay = " ".join(
                    str(x) for x in (
                        primary,
                        desc,
                        name_field,
                        *(item.get("aliases") or []),
                    )
                ).lower()
                if q_lower not in hay:
                    continue
                if kind == "formula":
                    results.append(
                        {
                            "name": primary,
                            "full_name": item.get("full_name"),
                            "description": desc,
                            "homepage": item.get("homepage"),
                            "stable_version": (item.get("versions") or {}).get("stable"),
                            "license": item.get("license"),
                            "deps": item.get("dependencies", [])[:10],
                            "url": f"https://formulae.brew.sh/formula/{primary}",
                        }
                    )
                else:
                    results.append(
                        {
                            "token": primary,
                            "name": name_field,
                            "description": desc,
                            "homepage": item.get("homepage"),
                            "version": item.get("version"),
                            "url": f"https://formulae.brew.sh/cask/{primary}",
                        }
                    )
                if len(results) >= max(1, min(int(limit), 100)):
                    break
            return _ok(
                {kind + "s": results},
                source="homebrew",
                kind=kind,
                query=query,
                count=len(results),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Homebrew 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Homebrew 解析失败: {ex}")

    # ───────────────────────── 46. Flathub ─────────────────────────
    def search_flathub(self, query: str, limit: int = 20) -> Dict:
        """Flathub Linux 应用商店搜索 (Flatpak 包, 免费)"""
        try:
            r = self._get(
                "https://flathub.org/api/v2/search",
                params={"query": query},
                timeout=20,
            )
            if r.status_code == 405:
                # POST 端点
                r = self.session.post(
                    "https://flathub.org/api/v2/search",
                    json={"query": query},
                    timeout=20,
                )
            r.raise_for_status()
            data = r.json()
            hits = data.get("hits", []) if isinstance(data, dict) else data
            apps = []
            for h in hits[: max(1, min(int(limit), 100))]:
                apps.append(
                    {
                        "id": h.get("id") or h.get("app_id") or h.get("flatpakAppId"),
                        "name": h.get("name"),
                        "summary": h.get("summary"),
                        "description": (h.get("description") or "")[:300],
                        "categories": h.get("categories", []),
                        "developer_name": h.get("developer_name"),
                        "installs_last_month": h.get("installs_last_month"),
                        "icon": h.get("icon"),
                        "url": f"https://flathub.org/apps/{h.get('id') or h.get('app_id') or ''}",
                    }
                )
            return _ok(
                {"apps": apps},
                source="flathub",
                query=query,
                count=len(apps),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Flathub 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Flathub 解析失败: {ex}")

    # ───────────────────────── 47. VSCode Marketplace ─────────────────────────
    def search_vscode_extensions(
        self,
        query: str,
        limit: int = 20,
        sort_by: int = 4,
    ) -> Dict:
        """VSCode Marketplace 扩展搜索

        sort_by: 0=Relevance, 1=LastUpdated, 2=Name, 3=Publisher,
                 4=InstallCount, 5=Rating, 6=TrendingDaily, 7=TrendingWeekly,
                 8=TrendingMonthly, 10=PublishedDate, 12=WeightedRating
        """
        try:
            body = {
                "filters": [
                    {
                        "criteria": [
                            {"filterType": 8, "value": "Microsoft.VisualStudio.Code"},
                            {"filterType": 10, "value": query},
                        ],
                        "pageNumber": 1,
                        "pageSize": max(1, min(int(limit), 100)),
                        "sortBy": int(sort_by),
                        "sortOrder": 0,
                    }
                ],
                "assetTypes": [],
                "flags": 914,
            }
            r = self.session.post(
                "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
                json=body,
                headers={
                    "Accept": "application/json;api-version=3.0-preview.1",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            r.raise_for_status()
            results = r.json().get("results", [{}])
            extensions_raw = results[0].get("extensions", []) if results else []
            extensions = []
            for ext in extensions_raw:
                stats = {s.get("statisticName"): s.get("value") for s in ext.get("statistics", [])}
                versions = ext.get("versions", [])
                latest_version = versions[0].get("version") if versions else ""
                extensions.append(
                    {
                        "id": ext.get("extensionId"),
                        "name": ext.get("extensionName"),
                        "display_name": ext.get("displayName"),
                        "publisher": (ext.get("publisher") or {}).get("publisherName"),
                        "description": ext.get("shortDescription"),
                        "version": latest_version,
                        "install_count": int(stats.get("install", 0) or 0),
                        "rating": stats.get("averagerating"),
                        "rating_count": int(stats.get("ratingcount", 0) or 0),
                        "trending_daily": stats.get("trendingdaily"),
                        "updated": ext.get("lastUpdated"),
                        "url": f"https://marketplace.visualstudio.com/items?itemName={(ext.get('publisher') or {}).get('publisherName')}.{ext.get('extensionName')}",
                    }
                )
            return _ok(
                {"extensions": extensions},
                source="vscode_marketplace",
                query=query,
                count=len(extensions),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"VSCode Marketplace 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"VSCode Marketplace 解析失败: {ex}")

    # ───────────────────────── 48. Open-Meteo Archive (历史天气) ─────────────────────────
    def get_weather_history(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        daily_vars: Optional[List[str]] = None,
    ) -> Dict:
        """Open-Meteo Archive - 1940 至今全球历史天气 (完全免费)

        Args:
            latitude / longitude: 经纬度
            start_date / end_date: YYYY-MM-DD
            daily_vars: 变量列表,默认 [temperature_2m_max, temperature_2m_min, precipitation_sum]
        """
        try:
            if not daily_vars:
                daily_vars = [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "wind_speed_10m_max",
                ]
            r = self._get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "start_date": start_date,
                    "end_date": end_date,
                    "daily": ",".join(daily_vars),
                    "timezone": "auto",
                },
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            return _ok(
                {
                    "location": {
                        "latitude": d.get("latitude"),
                        "longitude": d.get("longitude"),
                        "elevation": d.get("elevation"),
                    },
                    "daily": d.get("daily"),
                    "daily_units": d.get("daily_units"),
                },
                source="open_meteo_archive",
                start_date=start_date,
                end_date=end_date,
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Open-Meteo Archive 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Open-Meteo Archive 解析失败: {ex}")

    # ───────────────────────── 49. Exploit-DB (RSS) ─────────────────────────
    def search_exploit_db(self, query: Optional[str] = None, limit: int = 25) -> Dict:
        """Exploit-DB 漏洞利用代码库 (Offensive Security 维护, 免费)"""
        if not feedparser:
            return _err("feedparser 未安装", code="DEP_MISSING")
        try:
            # Exploit-DB 提供 RSS 最新条目, 搜索通过本地过滤
            r = self._get(
                "https://www.exploit-db.com/rss.xml",
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 Argus/6.6"},
            )
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            q_lower = (query or "").lower()
            entries = []
            for e in feed.entries:
                title = getattr(e, "title", "") or ""
                desc = getattr(e, "summary", "") or ""
                if query and q_lower not in title.lower() and q_lower not in desc.lower():
                    continue
                entries.append(
                    {
                        "title": title,
                        "url": getattr(e, "link", ""),
                        "published": getattr(e, "published", ""),
                        "description": desc[:400],
                        "id": getattr(e, "id", ""),
                        "author": getattr(e, "author", ""),
                    }
                )
                if len(entries) >= max(1, min(int(limit), 100)):
                    break
            return _ok(
                {"exploits": entries},
                source="exploit_db",
                query=query,
                count=len(entries),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Exploit-DB 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Exploit-DB 解析失败: {ex}")

    # ───────────────────────── 50. MusicBrainz ─────────────────────────
    def search_musicbrainz(
        self,
        query: str,
        entity: str = "artist",
        limit: int = 20,
    ) -> Dict:
        """MusicBrainz 开放音乐百科 (50M+ 艺术家/专辑/歌曲, 免费)"""
        try:
            entity = entity.lower()
            if entity not in ("artist", "release", "release-group", "recording", "label", "work"):
                return _err("entity 无效", code="INVALID_PARAM")
            r = self._get(
                f"https://musicbrainz.org/ws/2/{entity}",
                params={
                    "query": query,
                    "limit": max(1, min(int(limit), 100)),
                    "fmt": "json",
                },
                headers={
                    "User-Agent": "Argus/6.6 (noreply@argus.local)",
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            key = {
                "artist": "artists",
                "release": "releases",
                "release-group": "release-groups",
                "recording": "recordings",
                "label": "labels",
                "work": "works",
            }[entity]
            items_raw = data.get(key, [])
            items = []
            for it in items_raw:
                items.append(
                    {
                        "id": it.get("id"),
                        "name": it.get("name") or it.get("title"),
                        "type": it.get("type"),
                        "country": it.get("country"),
                        "score": it.get("score"),
                        "begin": (it.get("life-span") or {}).get("begin"),
                        "end": (it.get("life-span") or {}).get("ended"),
                        "tags": [t.get("name") for t in (it.get("tags") or [])[:10]],
                        "url": f"https://musicbrainz.org/{entity}/{it.get('id')}",
                    }
                )
            return _ok(
                {entity + "s": items, "total": data.get("count")},
                source="musicbrainz",
                entity=entity,
                query=query,
                count=len(items),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"MusicBrainz 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"MusicBrainz 解析失败: {ex}")

    # ───────────────────────── 51. CrossRef Event Data ─────────────────────────
    def get_crossref_events(
        self,
        doi: Optional[str] = None,
        source: Optional[str] = None,
        rows: int = 25,
    ) -> Dict:
        """CrossRef Event Data - DOI 论文在社交媒体的被提及事件 (Wikipedia/Twitter/Reddit/Newsfeed/F1000 等)"""
        try:
            params = {"rows": max(1, min(int(rows), 500))}
            if doi:
                params["obj-id"] = doi
            if source:
                params["source"] = source  # wikipedia / twitter / reddit / newsfeed / f1000 / stackexchange
            r = self._get(
                "https://api.eventdata.crossref.org/v1/events",
                params=params,
                timeout=45,
            )
            r.raise_for_status()
            data = r.json().get("message", {})
            events = []
            for ev in data.get("events", []):
                events.append(
                    {
                        "id": ev.get("id"),
                        "source": ev.get("source_id"),
                        "subj_id": ev.get("subj_id"),   # 提及方(文章/推文)
                        "obj_id": ev.get("obj_id"),     # 被提及的 DOI
                        "relation": ev.get("relation_type_id"),
                        "occurred_at": ev.get("occurred_at"),
                        "updated_date": ev.get("updated_date"),
                        "terms": ev.get("terms"),
                        "action": ev.get("action"),
                    }
                )
            return _ok(
                {"events": events, "total_results": data.get("total-results")},
                source="crossref_events",
                doi=doi,
                source_filter=source,
                count=len(events),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"CrossRef Events 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"CrossRef Events 解析失败: {ex}")

    # ───────────────────────── 52. Artifact Hub (K8s) ─────────────────────────
    def search_artifact_hub(
        self,
        query: str,
        kind: Optional[int] = None,
        limit: int = 25,
    ) -> Dict:
        """Artifact Hub - Kubernetes 生态包 (Helm charts / Operators / OLM / Tekton 等)

        kind: 0=Helm chart / 1=Falco rules / 2=OPA policies / 3=OLM operator /
              4=Tinkerbell actions / 5=KEDA scaler / 6=CoreDNS plugin /
              7=Keptn integration / 8=Container image / 9=Kubewarden policy /
              10=Gatekeeper policy / 11=Kyverno policy / 12=Knative client plugin /
              13=Backstage plugin / 14=Argo template / 15=KubeArmor policy
        """
        try:
            params = {
                "ts_query_web": query,
                "limit": max(1, min(int(limit), 60)),
                "offset": 0,
            }
            if kind is not None:
                params["kind"] = int(kind)
            r = self._get(
                "https://artifacthub.io/api/v1/packages/search",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            pkgs_raw = data.get("packages", []) if isinstance(data, dict) else data
            pkgs = []
            for p in pkgs_raw:
                pkgs.append(
                    {
                        "package_id": p.get("package_id"),
                        "name": p.get("name"),
                        "normalized_name": p.get("normalized_name"),
                        "description": p.get("description"),
                        "version": p.get("version"),
                        "stars": p.get("stars"),
                        "kind": p.get("kind"),
                        "repository": (p.get("repository") or {}).get("name"),
                        "organization": (p.get("repository") or {}).get("organization_display_name"),
                        "verified_publisher": (p.get("repository") or {}).get("verified_publisher"),
                        "official": (p.get("repository") or {}).get("official"),
                        "url": f"https://artifacthub.io/packages/{p.get('repository', {}).get('kind_name', 'helm')}/{(p.get('repository') or {}).get('name', '')}/{p.get('normalized_name', '')}",
                    }
                )
            return _ok(
                {"packages": pkgs},
                source="artifact_hub",
                query=query,
                count=len(pkgs),
            )
        except requests.exceptions.RequestException as ex:
            return _err(f"Artifact Hub 请求失败: {ex}", code="NETWORK_ERROR")
        except Exception as ex:
            return _err(f"Artifact Hub 解析失败: {ex}")
