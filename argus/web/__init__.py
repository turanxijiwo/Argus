"""Argus Web Dashboard (Batch 6)

轻量级 starlette 应用, 提供实时看板 + SSE 推流。
复用 fastmcp 自带的 starlette + uvicorn, 不新增依赖。

入口: python -m argus.web  或 scripts/start-web.sh
"""
