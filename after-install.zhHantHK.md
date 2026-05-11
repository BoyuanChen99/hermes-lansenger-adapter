[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信 轉接器 — 安裝後設定

已安裝兩個插件及一個技能：

1. **lansenger-platform** — 網關頻道轉接器（啟用 藍信 作為訊息頻道）
2. **lansenger-tools** — Agent 工具，用於發送訊息、檔案、圖片、撤回訊息、linkCard 卡片
3. **lansenger-messaging** — 教導 Agent 如何選擇正確 藍信 工具的技能

## 設定

### 方式 A：互動式設定向導（推薦）

執行內建的設定向導——它會逐步引導您完成每個憑證的設定：

```bash
hermes setup gateway
```

從平台清單中選擇 **Lansenger**，然後貼上您的 App ID、App Secret，並可選擇確認 API 網關 URL。已設定的值會顯示出來（密鑰會被遮掩），可以覆蓋修改。

> 💡 App ID 及 App Secret 可在 藍信桌面端 → 通訊錄 → 智能機械人 → 個人機械人 → ℹ️ 圖標中找到（行動端不支援查看憑證）

### 方式 B：config.yaml

將以下內容加入 `~/.hermes/config.yaml` 的 `platforms.lansenger` 部分：

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或您的自訂網關URL
```

### 方式 C：.env 檔案（手動）

編輯 `~/.hermes/.env`，加入以下內容：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## 技能安裝

安裝插件後，將技能複製至 Hermes 技能目錄：

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging && cp ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

此技能教導 Agent 藍信 訊息類型的能力範圍（text 與 formatText），並提供選擇正確工具的決策樹。若缺少此技能，Agent 可能選擇錯誤的訊息類型，導致失去 Markdown 格式或附件支援。

## 重啟網關

設定完成後，重啟 Hermes 網關：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 应在 Plugin toolsets 部分显示 `lansenger-tools`
- `hermes plugins list` 应显示 `hermes-lansenger-adapter` 和 `lansenger-tools` 为已启用状态

## 工具概覽

```
┌─────────────────────────┬──────────────┬──────────────┬──────────────┐
│  Tool                   │  Markdown    │  @mention    │  Attachments │
├─────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text    │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown│  ✓           │  ✗           │  ✗           │
│  lansenger_send_file    │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_image_url│ ✗           │  —           │  ✓ (only)    │
│  lansenger_revoke_message│ —           │  —           │  —           │
│  lansenger_send_link_card│ —           │  —           │  —           │
└─────────────────────────┴──────────────┴──────────────┴──────────────┘
```