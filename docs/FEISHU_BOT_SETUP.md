# Argus 飞书机器人接入指南

> 目标:在飞书群 @Argus 或私聊发消息,机器人自动调用 MCP 工具返回结果。

## 🗺️ 架构速览

```
飞书群/私聊
    ↓ @Argus 发消息
飞书开放平台
    ↓ POST 事件回调
Cloudflare Tunnel (公网入口)
    ↓ 转发
你的 Mac: 127.0.0.1:6600 (Starlette 服务)
    ↓ 调用
Argus MCP 工具
    ↓ 渲染回复
发回群/私聊
```

---

## 📋 你要准备的 4 样东西

1. **飞书自建应用**的 `App ID` / `App Secret`
2. **事件订阅**的 `Verification Token` + (可选) `Encrypt Key`
3. **Cloudflare Tunnel** 的公网 URL(免费,~5 分钟搞定)
4. 把上面 4 个填进 Argus 的环境变量

---

## Step 1: 创建飞书自建应用

1. 打开 <https://open.feishu.cn/app>(飞书开放平台)
2. 点 **创建自建应用** → 填名字(例:Argus)→ 上传头像(可选)
3. 建好后进应用详情页

## Step 2: 启用机器人能力

1. 左侧菜单 **添加应用能力** → 找到 **机器人** → **启用**
2. 左侧菜单 **权限管理** → 开启以下权限:
   - `im:message`(接收和发送消息)
   - `im:message.group_at_msg`(接收群里 @ 消息)
   - `im:message.group_at_msg:readonly` 如果有
   - `im:message:send_as_bot`(以机器人身份发消息)
   - `im:chat:read`(读取群信息,方便 debug)
3. **可选**:在"**凭证与基础信息**"里看到 `App ID` 和 `App Secret`,记下来

## Step 3: 配置事件订阅

1. 左侧菜单 **事件订阅**
2. 先**暂不填 URL**,往下:
   - **加密策略**(推荐**关闭**,简单):Encrypt Key 留空
   - 记下 **Verification Token**
3. 往下 **添加事件** → 搜 `im.message.receive_v1`(接收消息 v2.0)→ 勾选

## Step 4: Cloudflare Tunnel(公网暴露)

最简方式(免费,无需登录):

```bash
# 装 cloudflared
brew install cloudflared

# 临时 tunnel(重启会变 URL,先用来调试)
cloudflared tunnel --url http://127.0.0.1:6600
```

运行后会打出一行:
```
Your quick tunnel has been created!
https://<随机子域>.trycloudflare.com
```

记下这个 URL。**稳定使用**需要 Cloudflare 账号(免费)+ Named Tunnel,后面说。

## Step 5: 把凭证填进 Argus

编辑 `~/.zshrc`(或你 shell 的 profile):

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxxxxx"
export FEISHU_VERIFICATION_TOKEN="xxxxxx"
# 如果开了加密, 再加:
# export FEISHU_ENCRYPT_KEY="xxxxxx"
```

然后 `source ~/.zshrc`。

## Step 6: 启动 Argus 飞书机器人

```bash
cd /Users/t/argus
./scripts/start-feishu-bot.sh bg
```

查状态:
```bash
./scripts/start-feishu-bot.sh status
```

日志:`/tmp/argus-feishu-bot.log`

## Step 7: 回飞书后台填回调 URL + 验证

回到飞书 **事件订阅**:

- **请求地址**:填 `https://<你的 cloudflared 子域>.trycloudflare.com/feishu/event`
- 点 **保存** → 飞书立即发 `url_verification` 挑战,Argus 会自动响应,通过则显示"已验证"

## Step 8: 把机器人加到群(或开始私聊)

- **群模式**:打开飞书群 → 设置 → 群机器人 → 添加机器人 → 选刚建的 Argus
- **私聊模式**:飞书搜索你的 App 名字,发起私聊

## Step 9: 测试

在群里 `@Argus 帮助`,应该看到命令菜单。

其他命令:
- `@Argus 搜 AI 监管` — BM25 搜最近 7 天
- `@Argus 早报` — 当日热点速览
- `@Argus 异常` — 突发话题
- `@Argus 热词` — Top 趋势词
- `@Argus 状态` — 系统健康检查

---

## 🔧 稳定方案(可选,给严肃用的)

上面 `cloudflared tunnel --url ...` 是**每次重启 URL 变**。想固定域名:

1. 注册 Cloudflare 账号(免费)+ 绑定你自己的域名(没有可以买 .com 一年 $8)
2. `cloudflared tunnel login`
3. `cloudflared tunnel create argus-bot` 建命名 tunnel
4. 配 `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <tunnel-id>
   credentials-file: /Users/t/.cloudflared/<id>.json
   ingress:
     - hostname: argus.yourdomain.com
       service: http://127.0.0.1:6600
     - service: http_status:404
   ```
5. `cloudflared tunnel route dns argus-bot argus.yourdomain.com`
6. 启动:`cloudflared tunnel run argus-bot`
7. 想开机自启,`brew services start cloudflared`

---

## 🐛 常见问题

| 症状 | 原因 | 解决 |
|---|---|---|
| 飞书 "URL 验证失败" | cloudflared 没在跑 / bot 没启动 | 先 `curl https://xxx.trycloudflare.com/health` 看能不能通 |
| 机器人已加群但不回消息 | 事件订阅没选 `im.message.receive_v1` | 回 Step 3 检查 |
| 群消息要 @ 才响应,私聊没反应 | 权限缺 `im:message` | 回 Step 2 补权限 |
| 回复 403 | token 过期 / App Secret 错 | 检查 env 值 |
| cloudflared 随机 URL 每次重启变 | 用的 quick tunnel | 换成 named tunnel(稳定方案) |

---

## 📂 相关文件

| 路径 | 内容 |
|---|---|
| `argus_server/feishu_bot.py` | 机器人服务代码 + 命令路由 |
| `scripts/start-feishu-bot.sh` | 启停脚本 |
| `/tmp/argus-feishu-bot.log` | 运行日志 |
| 环境变量 | `~/.zshrc` 或 `~/argus/.env` |

加新命令:编辑 `feishu_bot.py`,用 `@command("名字", alias=["别名"], desc="描述")` 装饰一个函数即可。
