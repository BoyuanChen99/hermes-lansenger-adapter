[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 蓝信适配器 — 安装后配置

一个 Bundle 插件和两个技能已安装：

1. **hermes-lansenger-adapter** — Bundle 容器（自动展开为 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 选择正确蓝信消息类型的技能
3. **lansenger-setup** — 教 Agent 如何配置蓝信插件的技能

> ⚠️ **不要手动运行 `hermes plugins enable lansenger-platform` 或 `hermes plugins enable lansenger-tools`** — Bundle 在 gateway 重启时会自动展开并启用两个子插件。

## 配置

### 方式 A：交互式设置向导（推荐）

```bash
hermes setup gateway
```

从平台列表中选择 **Lansenger**，然后粘贴您的 App ID、App Secret，并可选择确认 API 网关 URL。

> 💡 App ID 和 App Secret 可在蓝信桌面端 → 通讯录 → 智能机器人 → 个人机器人 → ℹ️ 图标中找到（移动端不支持查看凭证）

### 方式 B：config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      app_id: "YOUR_APP_ID"
      app_secret: "YOUR_APP_SECRET"
      api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或你自定义的网关地址
```

### 方式 C：.env 文件

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## 重启网关

```bash
hermes gateway restart
```

## 验证

- `hermes tools list` 应在 Plugin toolsets 部分显示 `lansenger-tools`
- `hermes plugins list` 应显示 `lansenger-platform` 和 `lansenger-tools` 已启用

## 群聊配置

所有设置使用 **YAML 原生布尔值**（`true`/`false`，不加引号）。环境变量使用字符串。

### 全局设置

```yaml
platforms:
  lansenger:
    extra:
      group_policy: open              # open | allowlist | disabled
      require_mention: true           # 群聊中需要 @机器人才触发
      auto_mention_reply: false       # 群聊回复自动 @发送者
      auto_quote_reply: false         # 自动引用原消息（群聊+私聊）
```

### 按群覆盖

```yaml
platforms:
  lansenger:
    extra:
      groups:
        "<群ID>":
          enabled: true
          require_mention: false
          auto_mention_reply: true
          auto_quote_reply: true
          allow_from:
            - "<staffId>"
```

### 决策优先级（从上到下，命中即停止）

1. per-group `enabled: false` → 拒绝
2. per-group `allow_from` 非空且 sender 不在列表 → 拒绝
3. per-group `enabled: true` → 跳过全局策略
4. 全局 `group_policy` → `disabled` 全部拒绝 / `allowlist` 检查 `groups` 配置 map 的 key
5. 全局 `group_allow_from`（发送者级）非空且 sender 不在列表 → 拒绝
6. `require_mention`（per-group > 全局）为 true 且 `is_at_me=false` 且 `is_at_all=false` → 拒绝

## 自动回复功能

### autoMentionReply（自动 @发送者）

启用后，群聊回复自动 @发送者。根据 `fromType` 区分：
- `fromType=0`（用户）→ `reminder.userIds`
- `fromType=1`（应用/机器人）→ `reminder.botIds`

### autoQuoteReply（自动引用消息）

启用后，回复自动携带 `refMsgId` 引用原消息。群聊和私聊都支持。

## 斜杠命令

启动时适配器自动将所有 Hermes 内置和插件的斜杠命令（如 `/help`、`/status`、`/approve`）注册到蓝信 Bot API。命令将出现在蓝信聊天输入栏中。

### 关闭自动注册

```yaml
platforms:
  lansenger:
    extra:
      commands:
        native: false   # 按 profile 禁用斜杠命令注册
```

或通过环境变量全局关闭：`LANSENGER_SLASH_COMMANDS_NATIVE=0`

### 命令权限

控制哪些聊天可以看见每个命令：

```yaml
platforms:
  lansenger:
    extra:
      command_permissions:
        approve: owner       # 仅主人可看到
        status: everyone     # 所有聊天可看到（默认）
        restart: disabled    # 完全排除此命令
```

| 权限 | 生效范围 |
|------|----------|
| `owner` | 仅主人私聊 |
| `admin` | 主人私聊 + 所有群管理员 |
| `everyone` | 主人私聊 + 所有群（默认） |
| `disabled` | 命令从注册中排除 |

## 危险命令审批

当 Hermes 检测到危险命令（如 `rm -rf`、`curl | sh`、`chmod 777`），会暂停执行并发送一个带有可点击按钮的 **approveCard**。直接通过以下方式批准或拒绝：

- 点击卡片上的按钮
- 回复 `/approve`、`/approve session`、`/approve always` 或 `/deny`

卡片会原地更新显示决策结果（如"已允许执行一次"）。如果服务端不支持 approveCard 会自动降级为 appCard。

## 多 Workspace（Profiles）

Hermes 通过 Profiles 支持多 workspace 隔离：

```bash
hermes profile create bot-prod
hermes profile create bot-test
hermes -p bot-prod gateway start
hermes -p bot-test gateway start
```

每个 profile 拥有独立的 config.yaml、sessions、memories、skills、日志和数据文件（token、chat_type、owner）。

## 工具概览

```
┌───────────────────────────────┬──────────────┬──────────────┬──────────────┐
│  工具                         │  Markdown    │  @提及       │  附件        │
├───────────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text          │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown      │  ✓           │  ✓ (可选)    │  ✗           │
│  lansenger_send_file          │  ✗           │  —           │  ✓ (仅)      │
│  lansenger_send_image_url     │  ✗           │  —           │  ✓ (仅)      │
│  lansenger_send_link_card     │  —           │  —           │  —           │
│  lansenger_send_app_articles  │  —           │  —           │  —           │
│  lansenger_send_app_card      │  ✗ (div)     │  —           │  —           │
│  lansenger_update_dynamic_card│  —           │  —           │  —           │
│  lansenger_revoke_message     │  —           │  —           │  —           │
│  lansenger_query_groups       │  —           │  —           │  —           │
└───────────────────────────────┴──────────────┴──────────────┴──────────────┘
```
