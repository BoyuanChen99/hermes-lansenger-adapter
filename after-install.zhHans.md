[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Lansenger 适配器 — 安装后配置

已安装两个插件和一个技能：

1. **lansenger-platform** — 网关通道适配器（启用 Lansenger 作为消息通道）
2. **lansenger-tools** — Agent 工具，用于发送消息、文件、图片、撤回消息、linkCard 卡片
3. **lansenger-messaging** — 技能，教会 Agent 如何选择正确的 Lansenger 工具

## 配置

将以下内容添加到 `~/.hermes/config.yaml` 的 `platforms.lansenger` 下：

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或自定义网关 URL
```

或在 `~/.hermes/.env` 中设置为环境变量：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

> 💡 应用 ID 和应用密钥可在 Lansenger (蓝信) → 通讯录 → 个人机器人（非工作空间）中找到

## 技能安装

安装插件后，将技能复制到 Hermes 技能目录：

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging
cp lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

注意：Hermes 要求每个技能为一个包含 `SKILL.md` 文件的目录，而非单独的 `.md` 文件。

此技能教会 Agent Lansenger 消息类型的能力边界（text 与 formatText），并提供选择正确工具的决策树。没有此技能，Agent 可能选择错误的消息类型，从而丢失 Markdown 格式或附件支持。

## 重启网关

配置完成后，重启 Hermes 网关：

```bash
hermes gateway restart
```

## 验证

检查插件是否已加载：
- `hermes tools list` 应在 Plugin toolsets 部分显示 `lansenger-tools`
- `hermes plugins list` 应显示 `hermes-lansenger-adapter` 和 `lansenger-tools` 为已启用

## 工具概览

```
┌─────────────────────────┬──────────────┬──────────────┬──────────────┐
│  工具                    │  Markdown    │  @提及       │  附件        │
├─────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text    │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown│  ✓           │  ✗           │  ✗           │
│  lansenger_send_file    │  ✗           │  —           │  ✓ (仅)      │
│  lansenger_send_image_url│ ✗           │  —           │  ✓ (仅)      │
│  lansenger_revoke_message│ —           │  —           │  —           │
│  lansenger_send_link_card│ —           │  —           │  —           │
└─────────────────────────┴──────────────┴──────────────┴──────────────┘
```