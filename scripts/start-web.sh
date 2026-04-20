#!/usr/bin/env bash
# 启动 Argus Web Dashboard (Batch 6)
#
# 用法:
#   ./scripts/start-web.sh              前台启动
#   ./scripts/start-web.sh bg           后台启动, 日志到 /tmp/argus-web.log
#   ./scripts/start-web.sh stop         停止后台进程

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DIR}/.venv/bin/python"
HOST="${ARGUS_WEB_HOST:-127.0.0.1}"
PORT="${ARGUS_WEB_PORT:-5173}"
PIDFILE="/tmp/argus-web.pid"
LOGFILE="/tmp/argus-web.log"

cmd="${1:-fg}"

case "$cmd" in
  bg)
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "已在后台运行 (pid=$(cat "$PIDFILE")). 访问 http://$HOST:$PORT/"
      exit 0
    fi
    cd "$DIR"
    nohup "$PYTHON" -m argus.web --host "$HOST" --port "$PORT" >"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "已启动 (pid=$!). 访问 http://$HOST:$PORT/"
    echo "日志: $LOGFILE"
    ;;
  stop)
    if [[ -f "$PIDFILE" ]]; then
      pid=$(cat "$PIDFILE")
      kill "$pid" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "已停止 (pid=$pid)"
    else
      echo "未运行"
    fi
    ;;
  fg|*)
    cd "$DIR"
    exec "$PYTHON" -m argus.web --host "$HOST" --port "$PORT"
    ;;
esac
