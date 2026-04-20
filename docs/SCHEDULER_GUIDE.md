# Argus 定时推送使用指南（Batch 5a）

> 在 Claude Code 里一句话就能创建 launchd 定时任务 → 自动抓数据 → AI 简报 → 推送飞书/钉钉/邮箱。

---

## 🧩 4 个 MCP 工具

| 工具 | 作用 |
|---|---|
| `schedule_task(name, workflow, schedule)` | 创建任务 |
| `list_scheduled_tasks()` | 列出所有任务(含是否已 load 到 launchd) |
| `run_scheduled_task(name)` | 立即手动触发一次(返回 log tail) |
| `remove_scheduled_task(name)` | 卸载并删除 |

---

## 🛠️ 一、在 Claude 里创建任务

### 示例 1:每天 9 点飞书简报

```
帮我用 schedule_task 创建任务:
- name: morning_brief
- schedule: daily@09:00
- workflow 三步: trigger_crawl → ai_brief_news(style=oneline) → send_notification(channel=feishu)
```

Claude 会这样调用:

```python
schedule_task(
  name="morning_brief",
  schedule="daily@09:00",
  description="每日早报",
  workflow={
    "steps": [
      {"tool": "trigger_crawl", "args": {}},
      {"tool": "ai_brief_news", "args": {"style": "oneline", "target_language": "zh-CN"}},
      {"tool": "send_notification", "args": {"channel": "feishu", "title": "🌅 早报"}}
    ]
  }
)
```

### 示例 2:每小时异常话题预警

```python
schedule_task(
  name="anomaly_watch",
  schedule="hourly",                      # 每小时 0 分
  workflow={
    "steps": [
      {"tool": "detect_anomaly", "args": {"z_threshold": 2.5, "top_n": 5}},
      {"tool": "send_notification", "args": {"channel": "feishu", "title": "⚡ 异常话题"}}
    ]
  }
)
```

### 示例 3:每 30 分钟增量拉数据

```python
schedule_task(
  name="incr_sync",
  schedule="every:30m",                   # 每 30 分钟
  workflow={"steps": [{"tool": "trigger_crawl", "args": {}}]}
)
```

### 示例 4:多触发点(早晚两次)

```python
schedule_task(
  name="twice_daily",
  schedule=[{"hour": 9, "minute": 0}, {"hour": 21, "minute": 0}],
  workflow={...}
)
```

---

## ⏰ 二、schedule 格式速查

| 写法 | 含义 | 底层映射 |
|---|---|---|
| `"daily@09:00"` | 每天 09:00 | StartCalendarInterval |
| `"hourly"` | 每小时 0 分 | StartCalendarInterval |
| `"every:30m"` | 每 30 分钟 | StartInterval=1800 |
| `"every:2h"` | 每 2 小时 | StartInterval=7200 |
| `{"hour":9,"minute":0,"weekday":1}` | 周一 09:00 | 原生 dict |
| `[{"hour":9},{"hour":21}]` | 多个时间点 | 原生 list |

macOS launchd 里 weekday 是 0=周日,1=周一...6=周六。

---

## 📝 三、workflow DSL(你需要知道的)

```yaml
steps:
  - tool: <白名单里的工具名>
    args:
      key: value                         # 字面值
      some_param:
        __prev__: data.anomalies         # 引用上一步结果里的字段
    continue_on_error: false             # 失败时是否继续(默认 false, 失败即停)
```

### `__prev__` 链式传递示例

```python
workflow={
  "steps": [
    {"tool": "get_latest_news", "args": {"limit": 20}},
    {"tool": "semantic_deduplicate",
     "args": {"news_items": {"__prev__": "data.items"}}},
    {"tool": "ai_brief_news",
     "args": {"news_items": {"__prev__": "data.clusters"}}},
    {"tool": "send_notification", "args": {"channel": "feishu"}},
  ]
}
```

### 白名单工具(可在 workflow 里调用)

`trigger_crawl` · `sync_from_remote` · `ai_brief_news` · `ai_summarize` · `ai_translate` · `send_notification` · `generate_summary_report` · `detect_anomaly` · `semantic_deduplicate` · `analyze_with_ai` · `get_latest_news` · `get_trending_topics` · `search_news` · `narrative_tracking` · `universal_search`

要加新的 → 改 `argus_server/scheduler_runner.py` 的 `registry` 字典。

---

## 📡 四、你需要准备的:推送渠道接入

所有推送走 Argus 原生 `send_notification`,渠道都在 `config/config.yaml` 的 `notification.channels` 段。

### A. 飞书机器人(最常用)

1. **群里创建机器人**:飞书群 → 设置 → 群机器人 → 添加 → **自定义机器人**
2. 复制 Webhook URL(形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxx`)
3. 改 `config/config.yaml` 第 562 行:

```yaml
notification:
  enabled: true
  channels:
    feishu:
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/你的key"
```

4. 建议**打开签名校验**(飞书后台勾选)防刷,并把 secret 也填到 config(查 `config.yaml` 里的 `secret` 字段)。

### B. 钉钉(加签)

```yaml
dingtalk:
  webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
  secret: "SEC..."                       # 加签模式的 secret
```

### C. 企业微信群

```yaml
wework:
  webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  msg_type: "markdown"                   # 群机器人选 markdown
```

### D. Telegram(国内需代理)

```yaml
telegram:
  bot_token: "123456:ABC-DEF..."         # @BotFather 创建
  chat_id: "-100xxxxxxxxxx"              # 群 id 或用户 id
```

### E. Bark(iOS 推)

```yaml
bark:
  url: "https://api.day.app/YOUR_KEY"
```

### F. ntfy(开源自建/公共)

```yaml
ntfy:
  server_url: "https://ntfy.sh"
  topic: "argus-xxxx"               # 自起一个难猜的 topic
```

### G. 邮件

```yaml
email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 465
  username: "you@gmail.com"
  password: "应用密码(不是登录密码)"
  to: ["recipient@example.com"]
```

---

## 🧪 五、调试 / 验证

### 1. 直接手动触发

在 Claude 里:
```
run_scheduled_task(name="morning_brief")
```

返回里的 `log_tail` 就是 stdout/stderr,`returncode=0` 表示 launchd kickstart 成功。

### 2. 看日志文件

每个任务都有独立日志:
```
output/scheduled_tasks/<name>.log                # stdout+stderr(持续追加)
output/scheduled_tasks/<name>.last_run.json      # 最近一次每步的结果
```

### 3. 检查 launchd 状态

```bash
launchctl list | grep com.argus.task.
```

若某任务没出现 → 看 `~/Library/LaunchAgents/com.argus.task.<name>.plist` 是否存在,或再调一次 `schedule_task(name=..., enabled=True)`。

### 4. 改 workflow / schedule

目前直接编辑 `output/scheduled_tasks/<name>.json`(改 workflow) 或重新 `schedule_task` 同名会覆盖。

---

## 📂 六、产物分布速查

| 路径 | 内容 |
|---|---|
| `~/Library/LaunchAgents/com.argus.task.<name>.plist` | launchd 作业定义 |
| `output/scheduled_tasks/<name>.json` | workflow + schedule 配置 |
| `output/scheduled_tasks/<name>.log` | 运行日志 |
| `output/scheduled_tasks/<name>.last_run.json` | 最近一次各步结果 |
| `argus_server/scheduler_runner.py` | 真正的执行器 (launchd 起它) |

---

## ✅ 常用配方

### 早晚两次 + 飞书 + 话题追踪

```python
schedule_task(
  name="narrative_nvidia",
  schedule=[{"hour": 9}, {"hour": 21}],
  workflow={
    "steps": [
      {"tool": "narrative_tracking",
       "args": {"topic": "Nvidia", "platforms": ["news","hn","xhs","bili"]}},
      {"tool": "send_notification", "args": {"channel": "feishu", "title": "📊 Nvidia 叙事"}}
    ]
  }
)
```

### 工作日 10 点 CVE 简报

```python
schedule_task(
  name="cve_workday",
  schedule=[{"hour": 10, "weekday": i} for i in range(1, 6)],
  workflow={
    "steps": [
      {"tool": "search_cve", "args": {"severity": "CRITICAL", "limit": 10}},
      {"tool": "ai_summarize", "args": {"style": "bullet"}},
      {"tool": "send_notification", "args": {"channel": "feishu"}},
    ]
  }
)
```

---

**就这些,你去准备 webhook,我开始做 Batch 8 语义搜索。** 遇到推送不通的问题,把日志 `output/scheduled_tasks/<name>.log` 发回来。
