[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信轉接器——安裝後設定

一個 Bundle 插件和一個技能已安裝：

1. **hermes-lansenger-adapter** — Bundle 容器（自動展開為 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 選擇正確藍信工具的技能

> ⚠️ **不要手動執行 `hermes plugins enable lansenger-platform` 或 `hermes plugins enable lansenger-tools`** — Bundle 在網關重啟時會自動展開並啟用兩個子插件。手動啟用會失敗，因為子插件此時還在 Bundle 內部。

> 💡 如果你需要在重啟網關 *之前*啟用子插件，先執行展開腳本：
> ```bash
> python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py
> ```
> 然後就可以執行 `hermes plugins enable lansenger-platform` 和 `hermes plugins enable lansenger-tools`。

## 設定

### 方式 A：互動式設定向導（推薦）

執行內建的設定向導——它會逐步引導您完成每個憑證的設定：

```bash
hermes setup gateway
```

從平台清單中選擇 **Lansenger**，然後貼上您的 App ID、App Secret，並可選擇確認 API 網關 URL。已設定的值會顯示出來（密鑰會被遮掩），可以覆蓋修改。

> 💡 App ID 及 App Secret 可在藍信桌面端 → 通訊錄 → 智能機械人 → 個人機械人 → ℹ️ 圖標中找到（行動端不支援查看憑證）

### 方式 B：config.yaml

將以下內容加入 `~/.hermes/config.yaml` 的 `platforms.lansenger` 部分：

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或您的自訂網關 URL
```

### 方式 C：.env 檔案（手動）

編輯 `~/.hermes/.env`，加入以下內容：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## 技能安裝

安裝插件後，安裝 lansenger-messaging 技能（教導 Agent 訊息類型能力範圍與工具決策樹）：

**方式 A：從本地複製的儲存庫（最快速）：**

```bash
mkdir -p ~/.hermes/skills/lansenger && cp -r ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging ~/.hermes/skills/lansenger/
```

**方式 B：從 GitHub URL 安裝（不需本地複製）：**

```bash
hermes skills install --force --category lansenger https://github.com/lansenger-pm/hermes-lansenger-adapter/raw/main/skills/lansenger-messaging/SKILL.md
```

若缺少此技能，Agent 可能選擇錯誤的訊息類型，導致失去 Markdown 格式或附件支援。

## 重啟網關

設定完成後，重啟 Hermes 網關：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 應在 Plugin toolsets 部分顯示 `lansenger-tools`
- `hermes plugins list` 應顯示 `lansenger-platform` 和 `lansenger-tools` 已啟用（Bundle 自動展開）

## 工具概覽

```
┌───────────────────────────────┬──────────────┬──────────────┬──────────────┐
│  工具                         │  Markdown    │  @提及       │  附件        │
├───────────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text          │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown      │  ✓           │  ✓ (可選)    │  ✗           │
│  lansenger_send_file          │  ✗           │  —           │  ✓ (僅)      │
│  lansenger_send_image_url     │  ✗           │  —           │  ✓ (僅)      │
│  lansenger_send_link_card     │  —           │  —           │  —           │
│  lansenger_send_app_articles  │  —           │  —           │  —           │
│  lansenger_send_app_card      │  ✗ (div)     │  —           │  —           │
│  lansenger_update_dynamic_card│  —           │  —           │  —           │
│  lansenger_revoke_message     │  —           │  —           │  —           │
│  lansenger_query_groups       │  —           │  —           │  —           │
└───────────────────────────────┴──────────────┴──────────────┴──────────────┘

@提及說明：
- send_text：群聊中可用；私聊支援但沒必要（只有一個對話者）
- send_markdown：新版 API 能力；舊版靜默接受不觸發通知。群聊中建議在文字中包含 @姓名。