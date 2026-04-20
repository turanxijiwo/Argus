#!/usr/bin/env bash
# Argus 飞书机器人启动脚本
#
#   ./scripts/start-feishu-bot.sh           前台
#   ./scripts/start-feishu-bot.sh bg        后台
#   ./scripts/start-feishu-bot.sh stop      停
#   ./scripts/start-feishu-bot.sh status    状态

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DIR}/.venv/bin/python"
HOST="${FEISHU_BOT_HOST:-127.0.0.1}"
PORT="${FEISHU_BOT_PORT:-6600}"
PIDFILE="/tmp/argus-feishu-bot.pid"
LOGFILE="/tmp/argus-feishu-bot.log"

cmd="${1:-fg}"

case "$cmd" in
  bg)
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "已运行 (pid=$(cat "$PIDFILE"))"
      exit 0
    fi
    cd "$DIR"
    nohup "$PYTHON" -m argus_server.feishu_bot >"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "启动成功 (pid=$!)  $HOST:$PORT"
    echo "日志: $LOGFILE"
    ;;
  stop)
    if [[ -f "$PIDFILE" ]]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "已停止"
    else
      echo "未运行"
    fi
    ;;
  status)
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "running (pid=$(cat "$PIDFILE"))  $HOST:$PORT"
      tail -5 "$LOGFILE" 2>/dev/null || true
    else
      echo "not running"
    fi
    ;;
  fg|*)
    cd "$DIR"
    exec "$PYTHON" -m argus_server.feishu_bot
    ;;
esac
