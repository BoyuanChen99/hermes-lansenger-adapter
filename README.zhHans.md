[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes 蓝信适配器

> 💠 蓝信 网关适配器 + 媒体与消息工具插件，用于 Hermes Agent。

通过 WebSocket 长连接实现实时消息接收，通过 HTTP API 实现消息发送，将 Hermes Agent 连接到 蓝信 —— 一个企业即时通讯平台。

本仓库包含**两个插件**：

| 插件 | 类型 | 功能 |
|--------|------|-------------|
| `platforms/lansenger/` | 平台 | 网关通道适配器 — 接收与发送消息 |
| `lansenger-tools/` | 独立（工具） | Agent 可调用工具：发送文件/图片、撤回消息、发送 linkCard |

## 功能特性

### 平台适配器
- **实时消息** — 通过 WebSocket 长连接实现
- **Markdown 支持** — 使用 `formatText` 消息类型
- **i18nAppCard** — 交互式审批流程卡片
- **主通道自动检测** — 首条私聊消息设置默认发送目标
- **定时推送** — 通过 `standalone_sender_fn` 实现计划通知
- **用户授权** — 通过环境变量设置允许的用户 / 允许所有用户
- **零核心修改** — 纯插件模式，`git diff HEAD` 保持纯净

### 媒体与消息工具插件
- **lansenger_send_file** — 向指定用户或群组发送任意本地文件/图片/视频
- **lansenger_send_image_url** — 从 URL 下载图片并发送给指定用户或群组
- **lansenger_revoke_message** — 撤回已发送的 蓝信 消息 🗑️
- **lansenger_send_link_card** — 发送 蓝信 linkCard 卡片消息 🔗
- **自动媒体类型检测** — 根据文件扩展名自动分类图片/视频/文档
- **凭据控制** — 未设置 LANSENGER_APP_ID/SECRET 时工具自动隐藏

## 快速安装

### 通过 Hermes 插件管理器安装（推荐）

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### 手动安装

将本仓库克隆到 `~/.hermes/plugins/`：

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### 通过 pip 安装（高级）

```bash
pip install hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

## 配置

### 必需环境变量

将以下内容添加到 `~/.hermes/.env`：

| 变量 | 说明 | 示例 |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | 机器人应用 ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | 机器人应用密钥 | `your-app-secret` |

**凭据路径：** 蓝信 客户端 → 通讯录 → 个人机器人 → 创建机器人 → 详情

### 可选环境变量

| 变量 | 说明 | 默认值 |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API 网关 URL | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | 允许的用户 ID（逗号分隔） | — |
| `LANSENGER_ALLOW_ALL_USERS` | 允许所有用户（仅开发环境） | `false` |
| `LANSENGER_HOME_CHANNEL` | 默认定时推送的聊天 ID | 自动检测 |

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## 媒体与消息工具（来自 lansenger-tools）

这些工具允许 Agent 发送文件、图片和视频，撤回消息，以及发送 linkCard 卡片 —— 均可由 LLM 独立调用。凭据从环境变量（LANSENGER_APP_ID/SECRET）读取，而非从 `load_gateway_config()` 读取。

| 工具 | 参数 | 说明 |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | 发送纯文本，支持可选 @提及（仅群聊/员工群）和附件 |
| `lansenger_send_markdown` | `chat_id`, `message` | 发送 Markdown 格式文本（不支持 @提及和附件） |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 向用户或群组发送本地文件/图片/视频 |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 从 URL 下载图片并以原生图片形式发送 |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已发送的 蓝信 消息（系统提示为固定内容，不可自定义） |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | 发送 蓝信 linkCard 卡片消息 |

**使用示例（Agent 提示）：**

```
"将 report.pdf 发送给用户 2285568-abc123"
"将该图表图片分享到项目群聊"
"下载此 URL 图片并发送给我的同事"
"撤回我刚才发送给该用户的消息"
"向用户发送标题为 '项目文档' 且链接为 https://... 的 linkCard 卡片"
```

**限制：**
- 文件大小限制由组织的 蓝信 配置决定（无固定上限）
- 媒体说明使用纯文本（不支持 Markdown） —— 如需 Markdown 格式文本，请单独发送
- `lansenger_send_file` 在未指定 media_type 时会根据扩展名自动检测
- `lansenger_revoke_message`：对于员工/群聊类型，需要提供 `sender_id`

## 架构

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # 根清单 (kind: bundle)
                          ├── platforms/lansenger/            # 网关适配器
                          │   ├── plugin.yaml                 # 清单 (kind: platform)
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # 完整适配器（此处无工具处理器）
                          ├── lansenger-tools/           # 媒体与消息工具
                          │   ├── plugin.yaml                 # 清单 (kind: standalone)
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM 工具描述
                          │   └── tools.py                     # 处理器实现
                          ├── skills/                          # Agent 决策技能
                          │   └── lansenger-messaging.md       # 工具选择策略 + token 文档
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # pip 入口点
                          └── .gitignore
```

## 依赖

- `websockets` — WebSocket 长连接客户端
- `httpx` — HTTP 客户端，用于 API 调用（媒体工具也使用）

## 更新日志

### v2.2.0 (2026-05-11)

- ✅ 实现了 `reminder`（@提及）功能——`reminder_all`（bool，@全体）+ `reminder_user_ids`（array，指定用户），对应蓝信 API 的 `reminder` 对象
- ✅ @提及仅在群聊/员工群生效；私聊不支持
- ✅ 修复 `at_user_ids` schema 字段定义了但从未传入适配器方法的问题

### v2.1.0 (2026-05-11)

- 🔄 迁移至插件模式 — 零核心代码修改
- ✅ `ctx.register_platform()` 用于适配器注入
- ✅ `standalone_sender_fn` 用于定时任务投递
- ✅ 主频道自动检测
- ✅ 通过环境变量实现用户授权
- ✅ i18nAppCard 审批流程卡片
- ✅ 媒体与消息工具插件 — `lansenger_send_file`、`lansenger_send_image_url`
- ✅ `lansenger_revoke_message` 和 `lansenger_send_link_card` 从适配器中提取为独立工具插件
- ✅ 在蓝信适配器中实现 `send_link_card()` 方法（此前缺失）
- ✅ 修复撤回/linkCard "蓝信未配置"错误 — 现从环境变量读取而非 `load_gateway_config()`

## 许可证

MIT — 详情见 [LICENSE](LICENSE)。