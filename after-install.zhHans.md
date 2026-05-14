[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 蓝信 适配器 — 安装后配置

一个 Bundle 插件和一个技能已安装：

1. **hermes-lansenger-adapter** — Bundle 容器（自动展开为 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 选择正确蓝信工具的技能

> ⚠️ **不要手动运行 `hermes plugins enable lansenger-platform` 或 `hermes plugins enable lansenger-tools`** — Bundle 在 gateway 重启时会自动展开并启用两个子插件。手动 enable 会失败，因为子插件此时还在 Bundle 内部。

> 💡 如果你需要在重启 gateway *之前*启用子插件，先运行展开脚本：
> ```bash
> python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py
> ```
> 然后就可以运行 `hermes plugins enable lansenger-platform` 和 `hermes plugins enable lansenger-tools`。

## 配置

### 方式 A：交互式设置向导（推荐）

运行内置的设置向导——它会逐步引导您完成每个凭据的配置：

```bash
hermes setup gateway
```

从平台列表中选择 **Lansenger**，然后粘贴您的 App ID、App Secret，并可选择确认 API 网关 URL。已配置的值会显示出来（密钥会被遮掩），可以覆盖修改。

> 💡 应用 ID 和应用密钥可在 蓝信桌面端 → 通讯录 → 智能机器人 → 个人机器人 → ℹ️ 图标中找到（移动端不支持查看凭证）

### 方式 B：config.yaml

将以下内容添加到 `~/.hermes/config.yaml` 的 `platforms.lansenger` 下：

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或自定义网关 URL
```

### 方式 C：.env 文件（手动）

编辑 `~/.hermes/.env`，添加以下内容：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## 技能安装

安装插件后，安装 lansenger-messaging 技能（教会 Agent 消息类型能力边界与工具决策树）：

**方式 A：从本地克隆仓库复制（最快）：**

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging && cp ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

**方式 B：从 GitHub URL 安装（无需本地克隆）：**

```bash
hermes skills install --force --category lansenger https://github.com/lansenger-pm/hermes-lansenger-adapter/raw/main/skills/lansenger-messaging.md
```

没有此技能，Agent 可能选择错误的消息类型，从而丢失 Markdown 格式或附件支持。

## 重启网关

配置完成后，重启 Hermes 网关：

```bash
hermes gateway restart
```

## 验证

检查插件是否已加载：
- `hermes tools list` 应在 Plugin toolsets 部分显示 `lansenger-tools`
- `hermes plugins list` 应显示 `lansenger-platform` 和 `lansenger-tools` 已启用（Bundle 自动展开）

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

@提及说明：
- send_text：群聊中可用；私聊支持但没必要（只有一个对话者）
- send_markdown：新版 API 能力（spec 4.6.4.12）；旧版静默接受不触发通知。群聊中建议在文本中包含 @姓名。
```