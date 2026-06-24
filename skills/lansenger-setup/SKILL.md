---
name: lansenger-setup
description: Guide for first-time Lansenger (蓝信) bot credential binding, DM pairing, Hermes plugin configuration, slash command management, and dangerous command approval — for scenarios where the user wants to set up or reconfigure Lansenger from scratch via conversation.
version: 1.2.0
category: lansenger
tags: [lansenger, setup, configuration, slash-commands, approval]
---

# Lansenger (蓝信) Hermes 配置指南

本技能覆盖蓝信机器人接入 Hermes Agent 的完整流程。Agent 充当配置向导，引导用户获取凭证并通过修改配置文件完成接入。

## 何时使用此技能

- 用户说"配置蓝信"、"绑定蓝信机器人"、"连接蓝信"等。
- 蓝信插件已安装但未配置凭证（`LANSENGER_APP_ID` / `LANSENGER_APP_SECRET` 缺失或错误）。
- 用户想要调整群聊策略、@提及要求、自动 @回复、自动引用回复等设置。
- 用户遇到连接失败、群聊无响应等需要诊断的问题。

## 前提条件

- `hermes-lansenger-adapter` 插件已安装。
- 用户必须有一个已创建好的蓝信**个人机器人**。
- 用户必须能访问**蓝信桌面端**（移动端不支持查看机器人凭证）。

> ⚠️ **私有部署说明**：私有部署的蓝信服务版本各不相同，以下配置项可能并非全部可用：
> - `auto_mention_reply` / `auto_quote_reply` — 需要较新版本的蓝信服务端支持
> - `reminder.botIds` — @提及机器人功能需要较新版本
> - `refMsgId`（引用回复）— 需要服务端支持引用消息
> - `formatText` 入站解析 — 依赖服务端 WebSocket 推送格式
> - 如果某个配置项不生效，建议先确认蓝信服务端版本是否支持该功能

---

## 核心信息：如何获取当前会话的 chat_id 和 user_id

**重要：** 当前会话的 `chat_id` 和 `user_id` 已由系统注入到你的上下文中，**不需要调用 `lansenger_query_groups` 来获取**。

- **当前群聊 ID**：查看系统消息中的 `source.chat_id`。私聊会话的 `chat_id` 就是对方的 user_id，群聊会话的 `chat_id` 就是群的 groupId。
- **当前用户 ID**：查看系统消息中的 `source.user_id`。
- **会话类型**：查看 `source.chat_type` — `group` 表示群聊，`dm` 表示私聊。

**`lansenger_query_groups` 是查询机器人加入的全部群列表的**，不是查询当前 session 的群 ID。该 API 在企业私有部署中可能返回错误，不要依赖它来获取当前群 ID。

### 如何告知用户获取群 ID

如果用户需要获取某个群的 ID 用于配置：
1. 告诉用户当前所在群的 ID 就是 `source.chat_id`（群聊中）
2. 让用户在蓝信客户端打开目标群 → 群设置/群信息中即可看到群 ID
3. 如果以上方式都不行，让用户在目标群里发一条 @机器人的消息，群 ID 会出现在系统消息中

### 如何告知用户获取 staff ID（用户 ID）

- 当前对话的 `source.user_id` 就是发送者的 staff ID
- 每个人在蓝信客户端中只能查看**自己**的 staff ID（通讯录不暴露他人 ID）
- 如需获取其他人的 staff ID：让对方在群里 @机器人发一条消息，其 `source.user_id` 就会出现

---

## 配置参数速查表

所有配置路径均在 Hermes 配置文件 `~/.hermes/config.yaml` 的 `platforms.lansenger.extra` 下，或通过环境变量设置。

**注意：config.yaml 中布尔值使用 YAML 原生格式 `true`/`false`（不加引号）。环境变量中为字符串 `true`/`false`。**

### 核心凭证（必填）

凭证可以设置在 `.env` 文件（环境变量）或 `config.yaml` 的 `platforms.lansenger.extra` 中。**环境变量优先级高于 config.yaml**。

| 配置项 | 环境变量 | config.yaml 路径 | 必填 | 说明 |
|--------|----------|------------------|------|------|
| App ID | `LANSENGER_APP_ID` | `platforms.lansenger.extra.app_id` | ✅ | 机器人 App ID，格式：`orgId-applicationId`。获取路径：蓝信桌面端 → 通讯录 → 智能机器人 → 个人机器人 → ℹ️ |
| App Secret | `LANSENGER_APP_SECRET` | `platforms.lansenger.extra.app_secret` | ✅ | 机器人 App Secret。**敏感信息，绝对不要完整回显，始终脱敏处理。** |
| API Gateway URL | `LANSENGER_API_GATEWAY_URL` | `platforms.lansenger.extra.api_gateway_url` | ❌ | API 网关地址。公有云默认 `https://open.e.lanxin.cn/open/apigw`，企业私有部署需设置自定义地址。 |

### 群聊设置

| 配置项 | 环境变量 | config.yaml 路径 | 默认值 | 说明 |
|--------|----------|------------------|--------|------|
| groupPolicy | `LANSENGER_GROUP_POLICY` | `platforms.lansenger.extra.group_policy` | `open` | 群聊策略：`open`（所有群）、`allowlist`（仅列表群）、`disabled`（禁止群消息） |
| groupAllowFrom | `LANSENGER_GROUP_ALLOW_FROM` | `platforms.lansenger.extra.group_allow_from` | — | 允许在群聊中触发机器人的发送者 ID 列表（发送者级白名单，groupPolicy=allowlist 时生效）。留空则允许所有发送者 |
| requireMention | `LANSENGER_REQUIRE_MENTION` | `platforms.lansenger.extra.require_mention` | `true` | 群聊中是否需要 @机器人才触发 |

### 自动回复增强

| 配置项 | 环境变量 | config.yaml 路径 | 默认值 | 说明 |
|--------|----------|------------------|--------|------|
| autoMentionReply | `LANSENGER_AUTO_MENTION_REPLY` | `platforms.lansenger.extra.auto_mention_reply` | `false` | 群聊回复时自动 @发送者。根据 `fromType` 区分：0=用户 → `userIds`，1=app → `botIds` |
| autoQuoteReply | `LANSENGER_AUTO_QUOTE_REPLY` | `platforms.lansenger.extra.auto_quote_reply` | `false` | 回复时自动引用原消息（传 `refMsgId`）。支持群聊和私聊 |

### 按群粒度微调

使用 `platforms.lansenger.extra.groups.<chatId>` 覆盖单个群的设置：

```yaml
# config.yaml
platforms:
  lansenger:
    extra:
      groups:
        "<群ID>":
          enabled: true              # 显式开启/关闭此群
          require_mention: false     # 此群无需 @提及
          auto_mention_reply: true   # 此群自动 @发送者
          auto_quote_reply: true     # 此群自动引用原消息
          allow_from:                # 此群仅允许特定发送者
            - "<staffId1>"
            - "<staffId2>"
```

**决策优先级（从上到下，命中即停止）：**
1. per-group `enabled: false` → 拒绝
2. per-group `allow_from` 非空且 sender 不在列表 → 拒绝
3. per-group `enabled: true` → 跳过全局 policy，进入第5步
4. 全局 `group_policy` → `disabled` 全部拒绝 / `allowlist` 检查 groups 配置 map 的 key（只有列出的群才允许）
5. 全局 `group_allow_from`（发送者级）非空且 sender 不在列表 → 拒绝
6. `require_mention`（per-group > 全局）为 true 且 `is_at_me=false` 且 `is_at_all=false` → 拒绝

---

## 配置流程

### 第一阶段：核心凭证绑定

#### 步骤 1.1：引导用户获取凭证

告诉用户在蓝信桌面端查找机器人凭证：

> 请打开**蓝信桌面端**，按以下步骤获取你的机器人凭证：
> 1. 点击左侧 **通讯录**
> 2. 选择 **智能机器人** 标签页
> 3. 选择 **个人机器人**
> 4. 找到你的机器人，点击右侧的 **ℹ️ 详情图标**
> 5. 你将看到 **App ID** 和 **App Secret**

**务必告知用户的要点：**
- 凭证**仅在桌面端可见**，移动端无法查看。
- App ID 格式：`orgId-applicationId`（如 `13107200-12681216`）。
- App Secret 需妥善保管，相当于机器人密码。

#### 步骤 1.2：收集凭证

向用户询问：
1. **App ID**（必填）
2. **App Secret**（必填）
3. **API Gateway URL**（可选，公有云用户无需提供）

**安全规则：** 绝对不要完整回显 App Secret。确认时始终脱敏处理（如 `63F9***35AD`）。

#### 步骤 1.3：查看当前配置

```bash
cat ~/.hermes/config.yaml | grep -A 20 "platforms:" | grep -A 15 "lansenger:"
```

如果已有 `app_id` / `app_secret`，先与用户确认是否覆盖。

#### 步骤 1.4：写入凭证

**方式 A：写入 config.yaml**（推荐）

在 `platforms.lansenger.extra` 下添加：

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      app_id: "<用户提供的 App ID>"
      app_secret: "<用户提供的 App Secret>"
      api_gateway_url: "https://open.e.lanxin.cn/open/apigw"  # 公有云；私有部署用自定义地址
```

**方式 B：写入 .env 文件**

```bash
# 在 ~/.hermes/.env 中添加
LANSENGER_APP_ID=<用户提供的 App ID>
LANSENGER_APP_SECRET=<用户提供的 App Secret>
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

> 注意：如果 `.env` 已存在旧的凭证，需先删除旧行再写入新值。环境变量优先级高于 config.yaml，如果同时存在则以 `.env` 为准。

#### 步骤 1.5：重启并验证

```bash
hermes gateway restart
```

等待几秒后检查日志：
```bash
tail -20 ~/.hermes/logs/gateway.log | grep -i lansenger
```

成功标志：`WebSocket connected to wss://...`

---

### 第二阶段：私聊配对

Hermes 没有 openclaw 的 `pairing` 机制。个人机器人的私聊配对由蓝信平台侧控制——**个人机器人只能接收主人（创建者）的私聊消息。**

用户直接在蓝信客户端给机器人发私聊即可开始对话。如果收不到回复：
1. 检查 config.yaml / .env 中的凭证是否正确
2. 确认 Gateway 已重启且 WS 已连接
3. 确认发消息的用户是机器人主人

---

### 第三阶段：可选——询问其他设置

核心配置完成后，询问用户是否需要调整其他设置。每次 2-3 项，不要一次性全列出。

#### 批次 A：群聊

1. **群聊策略** — 默认 `open`（所有群可触发）
2. **群聊 @提及** — 默认需要 @机器人才会触发
3. **允许的发送者** — 如果设 `allowlist`，可限制哪些发送者能在群中触发机器人。留空则允许所有发送者

```yaml
# config.yaml 中配置
platforms:
  lansenger:
    extra:
      group_policy: allowlist        # open | allowlist | disabled
      group_allow_from: "<发送者ID1>,<发送者ID2>"   # 逗号分隔的发送者白名单（groupPolicy=allowlist 时生效；留空则所有发送者可通过）
      require_mention: false         # 关闭 @提及要求
```

或环境变量：
```bash
export LANSENGER_GROUP_POLICY=allowlist
export LANSENGER_GROUP_ALLOW_FROM="<发送者ID1>,<发送者ID2>"
export LANSENGER_REQUIRE_MENTION=false
```

#### 批次 B：自动回复增强

4. **自动 @发送者** — 群聊回复时自动 @发消息的人。用户 at 到 `userIds`，机器人 at 到 `botIds`，根据 `fromType` 自动区分
5. **自动引用消息** — 回复时带 `refMsgId` 引用原消息，群聊和私聊都生效

```yaml
platforms:
  lansenger:
    extra:
      auto_mention_reply: true       # 群聊自动 @发送者
      auto_quote_reply: true         # 自动引用原消息（群聊+私聊）
```

或环境变量：
```bash
export LANSENGER_AUTO_MENTION_REPLY=true
export LANSENGER_AUTO_QUOTE_REPLY=true
```

#### 批次 C：按群粒度配置

对特定群覆盖全局设置：

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
            - "<staffId1>"
```

**获取群 ID 的方法：** 当前群聊中 `source.chat_id` 就是群 ID。其他群可以让用户在蓝信客户端群设置/群信息中查看。

#### 修改后务必重启

```bash
hermes gateway restart
```

---

## 多 Workspace / 多机器人

Hermes 通过 **Profiles** 支持多 workspace，每个 profile 是独立的 `HERMES_HOME`：

```bash
# 创建独立 profile
hermes profile create bot-prod
hermes profile create bot-test

# 每个 profile 配置不同的凭证
# ~/.hermes/profiles/bot-prod/config.yaml
# ~/.hermes/profiles/bot-test/config.yaml

# 各自独立运行
hermes -p bot-prod gateway start
hermes -p bot-test gateway start
```

每个 profile 完全隔离：不同 config、session、memory、skills、日志。所有数据文件（token、chat_type、owner）都会写入对应 profile 的自有目录。

---

---

## 斜杠命令自动注册

适配器启动时会自动将所有 Hermes 内置命令和插件命令注册到蓝信 Bot API，用户可在聊天输入栏中看到并选择使用。

### 开关控制

如需关闭自动注册（如企业私有部署 API 不支持），可配置：

```yaml
platforms:
  lansenger:
    extra:
      commands:
        native: false   # 关闭斜杠命令自动注册
```

或环境变量：`LANSENGER_SLASH_COMMANDS_NATIVE=0`

优先级：per-platform config > 环境变量 > 默认 true

### 命令权限

控制不同聊天中可见的命令：

```yaml
platforms:
  lansenger:
    extra:
      command_permissions:
        approve: owner       # 仅主人私聊可见
        status: everyone     # 所有聊天可见（默认值）
        restart: disabled    # 完全排除此命令
```

| 权限值 | 生效范围 |
|--------|----------|
| `owner` | 仅主人私聊（scopeType=1） |
| `admin` | 主人私聊 + 所有群管理员（scopeType=1+6） |
| `everyone` | 主人私聊 + 所有群（scopeType=1+5，默认值） |
| `disabled` | 命令不注册 |

---
## 危险命令审批

当 Hermes 检测到危险命令（如 `rm -rf`、`curl | sh`、`chmod 777`），会暂停执行并发送 **approveCard** 审批卡片，包含 4 个可点击按钮：

- **批准一次** — 仅本次执行
- **本会话有效** — 本次会话内自动批准
- **永久允许** — 永久不再审批此模式
- **拒绝** — 拒绝执行

用户也可以直接回复文本命令完成审批：`/approve`、`/approve session`、`/approve always`、`/deny`。

卡片会在审批完成后原地更新状态（如"已允许执行一次"）。如果蓝信服务端不支持 approveCard，会自动降级为 appCard。

> **前提：** Hermes 的 `approvals.mode` 必须设为 `manual`（默认值），且被检测命令不在 `command_allowlist` 中。审批行为由 Hermes 核心控制，适配器仅负责卡片展示。

---

## 故障排除

### 机器人无响应

1. 检查 Gateway 是否在运行：
   ```bash
   hermes gateway status
   ```
2. 检查 WS 连接：
   ```bash
   tail -20 ~/.hermes/logs/gateway.log | grep -i "WebSocket"
   ```
3. 检查凭证是否正确（环境变量是否覆盖了 config.yaml）：
   ```bash
   env | grep LANSENGER
   ```

### 群聊无响应

1. 检查 `group_policy` 不是 `disabled`
2. 如果 `group_policy` 是 `allowlist`，确认群 ID 已被添加到 `groups` 配置 map 中
3. 如果 `group_allow_from`（发送者级）非空，确认发送者在列表中
4. 检查 `require_mention` — 如果为 `true`，用户必须 @机器人名称（@all 消息除外）
5. 检查 `groups.<chatId>` 下的按群覆盖设置 — 它们优先于全局设置
6. 查看日志确认消息是否被 BLOCKED：
   ```bash
   tail -50 ~/.hermes/logs/gateway.log | grep -i "BLOCKED\|Group msg"
   ```

### 收不到其他机器人的 Markdown 消息

Hermes 支持解析 `msgType=format`（即 formatText / Markdown）入站消息，来自 OpenClaw 等机器人。如果收不到，检查消息类型是否为 `bot_group_message` 且 `msgType=format`。

### 插件未安装

```bash
# 安装
hermes plugins install <git-url-or-owner/repo>

# 确认已启用
hermes plugins list
hermes plugins enable hermes-lansenger-adapter
```

### 连接失败

1. 确认 `api_gateway_url` 与部署方式匹配
2. 检查网络连通性
3. 确认机器人未被删除或重新创建（凭证可能已变更）

---

## 重要注意事项

- **不要编造或猜测凭证。** 仅使用用户明确提供的值。
- **绝对不要完整显示 App Secret。** 任何消息中都必须脱敏处理。
- **任何凭证或配置变更后必须重启 Gateway**（`hermes gateway restart`）。
- **群 ID 来自 `source.chat_id`** — 不要调用 `lansenger_query_groups` 来获取当前群 ID。
- **用户 ID（staff ID）来自 `source.user_id`** — 系统已自动提供。
- **蓝信客户端不暴露他人的 staff ID** — 获取他人 ID 需让对方在群里 @机器人发消息。
- **个人机器人只能接收主人的私聊。** 这是蓝信平台限制，与 Hermes 配置无关。
- **环境变量优先级高于 config.yaml** — 如果同时存在，以环境变量为准。排查问题时先检查 `env | grep LANSENGER`。
- **config.yaml 布尔值使用 YAML 原生格式** — `true`/`false` 不加引号。
- **多机器人用 Hermes Profiles** — `hermes profile create <name>` 创建独立 workspace。
