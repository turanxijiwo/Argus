"""
Starlette app: REST + SSE + 单 HTML 仪表盘

Endpoints:
    GET  /                    — 单 HTML dashboard
    GET  /api/health          — 健康检查
    GET  /api/latest          — 最新日期全量新闻 (按平台分组)
    GET  /api/trending        — 热点话题 (基于本地分析)
    GET  /api/anomalies       — 异常检测 (复用 detect_anomaly)
    GET  /api/dates           — 可用日期列表
    GET  /api/stream          — SSE 推流: 每 30s 推一次最新 5 条 + 异常计数
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.responses import StreamingResponse
from starlette.routing import Route


PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ────────────────────── 数据加载 helper ──────────────────────

def _list_dates() -> List[str]:
    p = PROJECT_ROOT / "output" / "news"
    if not p.exists():
        return []
    return sorted([f.stem for f in p.glob("*.db")], reverse=True)


def _load_day(ds: str) -> Dict[str, Any]:
    from argus.storage import get_storage_manager
    sm = get_storage_manager()
    data = sm.get_today_all_data(ds)
    if data is None:
        return {"date": ds, "total": 0, "platforms": {}}
    items_dict = getattr(data, "items", None) or {}
    id_to_name = getattr(data, "id_to_name", {}) or {}
    plat_out = {}
    total = 0
    for pid, items in (items_dict.items() if isinstance(items_dict, dict) else []):
        rows = []
        for it in items or []:
            title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
            url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
            ranks = getattr(it, "ranks", None) or (it.get("ranks") if isinstance(it, dict) else [])
            if not title:
                continue
            rows.append({"title": title, "url": url, "ranks": ranks})
        if rows:
            plat_out[id_to_name.get(pid, pid)] = rows
            total += len(rows)
    return {"date": ds, "total": total, "platforms": plat_out}


def _count_trending(day: Dict[str, Any], top_n: int = 20) -> List[Dict]:
    counter: Counter = Counter()
    platforms: Dict[str, set] = {}
    for plat, items in (day.get("platforms") or {}).items():
        for it in items:
            title = it.get("title") or ""
            for tok in title.replace("、", " ").replace(",", " ").split():
                if len(tok) < 2:
                    continue
                counter[tok] += 1
                platforms.setdefault(tok, set()).add(plat)
    top = counter.most_common(top_n)
    return [
        {"keyword": k, "count": c, "platform_count": len(platforms.get(k, ()))}
        for k, c in top
    ]


# ────────────────────── Endpoints ──────────────────────

async def health(_req: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "ts": int(time.time())})


async def api_dates(_req: Request) -> JSONResponse:
    return JSONResponse({"dates": _list_dates()})


async def api_latest(_req: Request) -> JSONResponse:
    dates = _list_dates()
    if not dates:
        return JSONResponse({"error": "no_data"}, status_code=404)
    day = await asyncio.to_thread(_load_day, dates[0])
    return JSONResponse(day)


async def api_trending(req: Request) -> JSONResponse:
    dates = _list_dates()
    if not dates:
        return JSONResponse({"error": "no_data"}, status_code=404)
    ds = req.query_params.get("date", dates[0])
    top = int(req.query_params.get("top", 20))
    day = await asyncio.to_thread(_load_day, ds)
    trending = _count_trending(day, top_n=top)
    return JSONResponse({"date": ds, "trending": trending})


async def api_anomalies(req: Request) -> JSONResponse:
    try:
        from argus_server.tools.ai_analytics import AIAnalyticsTools
    except Exception as ex:
        return JSONResponse({"error": str(ex)}, status_code=500)
    tool = AIAnalyticsTools(str(PROJECT_ROOT))
    topic = req.query_params.get("topic") or None
    days = int(req.query_params.get("lookback", 14))
    res = await asyncio.to_thread(
        tool.detect_anomaly, topic=topic, lookback_days=days
    )
    return JSONResponse(res)


async def api_stream(_req: Request) -> StreamingResponse:
    """SSE: 每 30s 推一次快照"""

    async def gen():
        while True:
            dates = _list_dates()
            if dates:
                day = await asyncio.to_thread(_load_day, dates[0])
                trending = _count_trending(day, top_n=10)
                # 抽 latest 5 条 (按平台头部)
                latest = []
                for plat, items in (day.get("platforms") or {}).items():
                    for it in items[:2]:
                        latest.append({
                            "platform": plat,
                            "title": it["title"],
                            "url": it.get("url", ""),
                        })
                    if len(latest) >= 10:
                        break
                payload = {
                    "ts": int(time.time()),
                    "date": day["date"],
                    "total": day["total"],
                    "trending_top": trending[:5],
                    "latest": latest[:10],
                }
            else:
                payload = {"ts": int(time.time()), "error": "no_data"}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ────────────────────── 单 HTML dashboard ──────────────────────

_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Argus Dashboard</title>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --warn:#f59e0b; --err:#f87171; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 -apple-system,Segoe UI,sans-serif; background:var(--bg); color:var(--text); }
  header { padding:18px 24px; background:var(--card); border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center; }
  header h1 { margin:0; font-size:18px; }
  .meta { color:var(--muted); font-size:12px; }
  main { display:grid; grid-template-columns: 1fr 1fr; gap:16px; padding:16px; }
  .card { background:var(--card); border-radius:8px; padding:16px; border:1px solid #334155; }
  .card h2 { margin:0 0 12px; font-size:14px; color:var(--accent); text-transform:uppercase; letter-spacing:0.5px; }
  .kw { display:inline-block; margin:2px 4px 2px 0; padding:2px 8px; background:#334155; border-radius:12px; font-size:12px; }
  .kw b { color:var(--accent); margin-left:4px; }
  ul { margin:0; padding-left:18px; }
  li { padding:4px 0; }
  li a { color:var(--text); text-decoration:none; }
  li a:hover { color:var(--accent); text-decoration:underline; }
  .plat { color:var(--muted); font-size:11px; }
  .anomaly { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #334155; }
  .anomaly .kw-name { font-weight:600; }
  .spike { color:var(--err); }
  .decline { color:var(--warn); }
  .new_emergence { color:var(--accent); }
  .stream-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--accent); margin-right:6px; animation:blink 1.5s infinite; }
  @keyframes blink { 50% { opacity: 0.3; } }
  button { background:#334155; color:var(--text); border:none; padding:6px 12px; border-radius:4px; cursor:pointer; margin-left:8px; }
  button:hover { background:#475569; }
</style>
</head>
<body>
<header>
  <h1>📊 Argus Dashboard</h1>
  <div class="meta">
    <span class="stream-dot"></span>
    <span id="status">connecting...</span>
    <button onclick="loadAll()">刷新</button>
  </div>
</header>
<main>
  <div class="card">
    <h2>🔥 Top 趋势词</h2>
    <div id="trending">加载中…</div>
  </div>
  <div class="card">
    <h2>📰 各平台最新</h2>
    <div id="latest">加载中…</div>
  </div>
  <div class="card">
    <h2>⚡ 异常检测 (7 天)</h2>
    <div id="anomalies">加载中…</div>
  </div>
  <div class="card">
    <h2>📅 可用日期</h2>
    <div id="dates">加载中…</div>
  </div>
</main>

<script>
async function jget(u) { const r = await fetch(u); return r.json(); }

async function loadTrending() {
  const d = await jget('/api/trending?top=30');
  const box = document.getElementById('trending');
  if (d.error) { box.textContent = '无数据'; return; }
  box.innerHTML = d.trending.map(t =>
    `<span class="kw">${t.keyword}<b>${t.count}</b></span>`
  ).join('');
}

async function loadLatest() {
  const d = await jget('/api/latest');
  const box = document.getElementById('latest');
  if (d.error) { box.textContent = '无数据'; return; }
  const platforms = Object.entries(d.platforms).slice(0, 6);
  box.innerHTML = platforms.map(([p, items]) => `
    <div style="margin-bottom:12px;">
      <div class="plat">${p} (${items.length})</div>
      <ul>${items.slice(0,3).map(it =>
        `<li><a href="${it.url||'#'}" target="_blank">${it.title}</a></li>`
      ).join('')}</ul>
    </div>
  `).join('');
}

async function loadAnomalies() {
  const d = await jget('/api/anomalies?lookback=7');
  const box = document.getElementById('anomalies');
  if (!d.success) { box.textContent = (d.error && d.error.message) || '数据不足'; return; }
  const anos = d.data.anomalies || [];
  if (!anos.length) { box.textContent = '未检测到异常'; return; }
  box.innerHTML = anos.slice(0, 15).map(a => `
    <div class="anomaly">
      <span class="kw-name">${a.keyword}</span>
      <span class="${a.trend}">${a.trend} z=${a.z_score} (${a.latest_count})</span>
    </div>
  `).join('');
}

async function loadDates() {
  const d = await jget('/api/dates');
  document.getElementById('dates').innerHTML = (d.dates || [])
    .slice(0, 14).map(ds => `<span class="kw">${ds}</span>`).join('');
}

function startStream() {
  const es = new EventSource('/api/stream');
  es.onopen = () => document.getElementById('status').textContent = 'streaming';
  es.onerror = () => document.getElementById('status').textContent = 'reconnecting';
  es.onmessage = (e) => {
    try {
      const p = JSON.parse(e.data);
      if (p.ts) {
        document.getElementById('status').textContent =
          'live · ' + new Date(p.ts*1000).toLocaleTimeString() +
          ' · ' + (p.date || '?') + ' · ' + (p.total || 0) + ' 条';
      }
    } catch {}
  };
}

async function loadAll() {
  await Promise.all([loadTrending(), loadLatest(), loadAnomalies(), loadDates()]);
}

loadAll();
startStream();
setInterval(loadAll, 60000);
</script>
</body></html>
"""


async def index(_req: Request) -> HTMLResponse:
    return HTMLResponse(_HTML)


def create_app() -> Starlette:
    routes = [
        Route("/", index),
        Route("/api/health", health),
        Route("/api/latest", api_latest),
        Route("/api/trending", api_trending),
        Route("/api/anomalies", api_anomalies),
        Route("/api/dates", api_dates),
        Route("/api/stream", api_stream),
    ]
    return Starlette(routes=routes)


app = create_app()
