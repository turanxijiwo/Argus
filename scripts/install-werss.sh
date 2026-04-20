#!/usr/bin/env bash
# 一键安装 WeRSS (微信公众号 → RSS) - Batch 7 辅助脚本
#
# 使用:
#   ./scripts/install-werss.sh            # 克隆到 ~/Desktop/werss 并安装
#   ./scripts/install-werss.sh bg         # 启动 (后台), 默认 8080
#   ./scripts/install-werss.sh stop       # 停止
#   ./scripts/install-werss.sh status     # 状态
#
# 前置: 已装 Node 20+ 和 pnpm (若无 pnpm 会尝试用 npm)
#
# 登录 werss 面板后:
#   1. 打开 http://127.0.0.1:8080/
#   2. 注册账号 → 添加公众号 → 获取 RSS URL
#   3. 回到 Claude, 调用 wechat_add_feed(url=..., name=...) 加到 Argus
set -euo pipefail

DIR="${WERSS_DIR:-$HOME/Desktop/werss}"
PORT="${WERSS_PORT:-8080}"
PIDFILE="/tmp/werss.pid"
LOGFILE="/tmp/werss.log"

cmd="${1:-install}"

has() { command -v "$1" >/dev/null 2>&1; }

case "$cmd" in
  install)
    if [[ -d "$DIR" ]]; then
      echo "已存在 $DIR, 跳过 clone. (删除目录可重装)"
    else
      echo "克隆 WeRSS 到 $DIR ..."
      git clone --depth 1 https://github.com/0x2E/werss.git "$DIR"
    fi

    cd "$DIR"
    if has pnpm; then
      echo "使用 pnpm 安装依赖..."
      pnpm install
    elif has npm; then
      echo "使用 npm 安装依赖..."
      npm install
    else
      echo "未安装 npm 或 pnpm, 请先装 Node.js: https://nodejs.org/"
      exit 1
    fi

    # 写一个 start.sh 便于后续启停
    cat > "$DIR/start.sh" <<EOF
#!/usr/bin/env bash
# werss launcher
set -euo pipefail
cd "\$(dirname "\$0")"
PORT="\${WERSS_PORT:-$PORT}"
case "\${1:-fg}" in
  bg)
    nohup npm start >"$LOGFILE" 2>&1 &
    echo \$! > "$PIDFILE"
    echo "werss started (pid=\$!). http://127.0.0.1:\$PORT/"
    echo "log: $LOGFILE"
    ;;
  stop)
    if [[ -f "$PIDFILE" ]]; then
      kill \$(cat "$PIDFILE") 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "stopped"
    else
      echo "not running"
    fi
    ;;
  fg|*)
    exec npm start
    ;;
esac
EOF
    chmod +x "$DIR/start.sh"

    echo
    echo "✅ WeRSS 已安装到 $DIR"
    echo "启动: $DIR/start.sh bg"
    echo "面板: http://127.0.0.1:$PORT/"
    echo "停止: $DIR/start.sh stop"
    ;;

  bg|stop|fg|status)
    if [[ ! -d "$DIR" ]]; then
      echo "werss 未安装, 先运行 $0 install"
      exit 1
    fi
    if [[ "$cmd" == "status" ]]; then
      if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "running (pid=$(cat "$PIDFILE")). http://127.0.0.1:$PORT/"
      else
        echo "not running"
      fi
      exit 0
    fi
    exec "$DIR/start.sh" "$cmd"
    ;;

  *)
    echo "usage: $0 [install|bg|stop|fg|status]"
    exit 1
    ;;
esac
