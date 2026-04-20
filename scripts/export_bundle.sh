#!/bin/bash
# Argus 全系统打包脚本
# 把 Argus + RSSHub + CLI 认证凭证 + 配置打成一个压缩包
# 用法: ./scripts/export_bundle.sh [输出目录]
#
# 打包的内容:
#   - Argus 源码 + 配置 (不含 .venv)
#   - RSSHub 源码 + .env (不含 node_modules, 会在新机器上 pnpm install)
#   - 已登录的 CLI 凭证 (~/.bilibili-cli, ~/.xiaohongshu-cli)
#   - launchd plist
#   - 一份部署脚本 install_on_new_mac.sh

set -e

OUT_DIR="${1:-$HOME/Desktop}"
TS=$(date +%Y%m%d_%H%M%S)
BUNDLE_NAME="argus_bundle_${TS}"
STAGING="/tmp/${BUNDLE_NAME}"

echo "═══════════════════════════════════════════════"
echo "  Argus 全系统导出"
echo "═══════════════════════════════════════════════"
echo "输出到: $OUT_DIR/${BUNDLE_NAME}.tar.gz"
echo

rm -rf "$STAGING"
mkdir -p "$STAGING"

# 1. Argus (不含 .venv 和 output 大文件)
echo "[1/5] 打包 Argus..."
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
      --exclude='output/news/*.db' --exclude='output/html/*' \
      /Users/t/argus/ "$STAGING/argus/"

# 2. RSSHub (不含 node_modules, 但保留 .env 和 lib/routes patch)
echo "[2/5] 打包 RSSHub..."
rsync -a --exclude='node_modules' --exclude='.git' --exclude='docs' \
      --exclude='.cache' --exclude='*.log' \
      /Users/t/rsshub/ "$STAGING/rsshub/"

# 3. CLI 凭证 (含登录 cookie, 敏感, 注意保密)
echo "[3/5] 打包 CLI 认证凭证..."
mkdir -p "$STAGING/credentials"
cp -r ~/.bilibili-cli "$STAGING/credentials/" 2>/dev/null || true
cp -r ~/.xiaohongshu-cli "$STAGING/credentials/" 2>/dev/null || true
# twitter / tg / discord 如果有也拷
[ -d ~/.twitter-cli ] && cp -r ~/.twitter-cli "$STAGING/credentials/"
[ -d ~/.tg-cli ] && cp -r ~/.tg-cli "$STAGING/credentials/"
[ -d ~/.discord-cli ] && cp -r ~/.discord-cli "$STAGING/credentials/"

# 4. LaunchAgents
echo "[4/5] 打包 LaunchAgents..."
mkdir -p "$STAGING/LaunchAgents"
cp ~/Library/LaunchAgents/com.argus.*.plist "$STAGING/LaunchAgents/" 2>/dev/null || true

# 5. 生成部署脚本
echo "[5/5] 生成 install_on_new_mac.sh..."
cat > "$STAGING/install_on_new_mac.sh" <<'INSTALLER'
#!/bin/bash
# Argus 一键部署到新 Mac
# 用法: ./install_on_new_mac.sh [目标用户目录, 默认 ~/Desktop]

set -e
TARGET="${1:-$HOME/Desktop}"
BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════════"
echo "  Argus 一键部署"
echo "═══════════════════════════════════════════════"
echo "源包: $BUNDLE_DIR"
echo "目标: $TARGET"
echo

# ---- 0. 检查前置: uv / node / pnpm ----
check_cmd() { command -v "$1" >/dev/null 2>&1; }

if ! check_cmd uv; then
    echo "▶ 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! check_cmd node; then
    echo "❌ 请先装 Node.js 22+ (推荐用 nvm): curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash"
    echo "   然后: nvm install 22 && nvm use 22"
    exit 1
fi

if ! check_cmd pnpm; then
    npm install -g pnpm@10.33.0
fi

# ---- 1. 复制 Argus 和 RSSHub ----
echo "▶ 复制 Argus 到 $TARGET/argus ..."
rsync -a "$BUNDLE_DIR/argus/" "$TARGET/argus/"

echo "▶ 复制 RSSHub 到 $TARGET/rsshub ..."
rsync -a "$BUNDLE_DIR/rsshub/" "$TARGET/rsshub/"

# ---- 2. 重建 Argus 虚拟环境 ----
echo "▶ 重建 Argus Python 环境..."
cd "$TARGET/argus" && uv sync

# ---- 3. 重建 RSSHub node_modules ----
echo "▶ 装 RSSHub 依赖 (这步要几分钟)..."
cd "$TARGET/rsshub" && pnpm install --prod=false

# ---- 4. 装 Puppeteer Chromium ----
echo "▶ 装 Chromium for Puppeteer..."
cd "$TARGET/rsshub" && npx puppeteer browsers install chrome

# ---- 5. 安装 5 个 CLI ----
echo "▶ 安装 AI agent CLIs..."
uv tool install bilibili-cli || true
uv tool install xiaohongshu-cli || true
uv tool install twitter-cli || true
uv tool install kabi-tg-cli || true
uv tool install kabi-discord-cli || true

# ---- 6. 复制认证凭证 ----
echo "▶ 恢复 CLI 认证凭证..."
for src in "$BUNDLE_DIR/credentials"/*; do
    [ -d "$src" ] || continue
    name="$(basename "$src")"
    dst="$HOME/$name"
    if [ -e "$dst" ]; then
        echo "  ⚠️  $dst 已存在, 备份为 $dst.bak"
        mv "$dst" "$dst.bak"
    fi
    cp -r "$src" "$dst"
    chmod 700 "$dst"
    find "$dst" -type f -exec chmod 600 {} \;
done

# ---- 7. LaunchAgents (可选, 开机自启 RSSHub) ----
if [ -d "$BUNDLE_DIR/LaunchAgents" ]; then
    read -p "是否安装 RSSHub 开机自启? (y/N) " yn
    if [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
        cp "$BUNDLE_DIR/LaunchAgents"/*.plist ~/Library/LaunchAgents/
        # plist 里的路径可能要改, 提醒用户
        echo "  ⚠️  ~/Library/LaunchAgents/com.argus.rsshub.plist 里的路径需手动检查"
        echo "     确认后: launchctl load ~/Library/LaunchAgents/com.argus.rsshub.plist"
    fi
fi

# ---- 8. 注册 MCP server ----
if check_cmd claude; then
    echo "▶ 注册 Argus MCP server..."
    UV_PATH=$(which uv)
    claude mcp add argus -- "$UV_PATH" --directory "$TARGET/argus" run python -m argus_server.server || true
fi

echo
echo "═══════════════════════════════════════════════"
echo "  ✅ 部署完成"
echo "═══════════════════════════════════════════════"
echo
echo "下一步:"
echo "  1. cd $TARGET/rsshub && ./start.sh bg       # 启动 RSSHub"
echo "  2. cd $TARGET/argus"
echo "  3. ./.venv/bin/python -m argus          # 跑一次验证"
echo "  4. 在 Claude Code 重启或重连 MCP"
echo
echo "注意: 如果浏览器 cookie 失效, 可能需要重新在新机器登录目标站点"
INSTALLER

chmod +x "$STAGING/install_on_new_mac.sh"

# 生成 README
cat > "$STAGING/README.md" <<'README'
# Argus 全系统导出包

## 内容
- `argus/` — 主系统 + MCP server + 配置
- `rsshub/` — 本地 RSSHub 服务 (不含 node_modules, 需重装)
- `credentials/` — CLI 工具的认证凭证 (含登录 token, 注意保密)
- `LaunchAgents/` — 开机自启配置
- `install_on_new_mac.sh` — 一键部署脚本

## 部署到新 Mac
```bash
./install_on_new_mac.sh
```

## 前置条件
- macOS 11+
- Node.js 22+
- Python 3.12+
- Git
- 网络能访问 PyPI + npm + GitHub

## 首次部署预计时间
- uv tool 装 5 个 CLI: 3-5 分钟
- RSSHub pnpm install: 2-3 分钟
- Chromium 下载: 1-2 分钟
- Argus uv sync: 1 分钟
- 合计约 10-15 分钟

## 敏感内容警告
`credentials/` 目录里的 cookie 文件代表了登录态, 等同密码。
不要把整包上传到公网 Git, 不要分享给他人。
README

# 压缩
echo
echo "压缩中..."
cd /tmp && tar -czf "${OUT_DIR}/${BUNDLE_NAME}.tar.gz" "${BUNDLE_NAME}"
SIZE=$(du -sh "${OUT_DIR}/${BUNDLE_NAME}.tar.gz" | awk '{print $1}')
rm -rf "$STAGING"

echo
echo "═══════════════════════════════════════════════"
echo "  ✅ 打包完成"
echo "═══════════════════════════════════════════════"
echo "文件: ${OUT_DIR}/${BUNDLE_NAME}.tar.gz"
echo "大小: $SIZE"
echo
echo "部署到新 Mac:"
echo "  1. 拷贝 ${BUNDLE_NAME}.tar.gz 到目标机器"
echo "  2. tar -xzf ${BUNDLE_NAME}.tar.gz"
echo "  3. cd ${BUNDLE_NAME} && ./install_on_new_mac.sh"
