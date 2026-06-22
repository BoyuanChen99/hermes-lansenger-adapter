[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信轉接器——安裝後設定

一個 Bundle 插件和兩個技能已安裝：

1. **hermes-lansenger-adapter** — Bundle 容器（自動展開為 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 選擇正確藍信工具的技能
3. **lansenger-setup** — 教 Agent 設定藍信插件的技能

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
    enabled: true
    extra:
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

## 重啟網關

設定完成後，重啟 Hermes 網關：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 應在 Plugin toolsets 部分顯示 `lansenger-tools`
- `hermes plugins list` 應顯示 `lansenger-platform` 和 `lansenger-tools` 已啟用（Bundle 自動展開）

## 群組聊天設定

所有設定使用 **YAML 原生布爾值**（`true`/`false`，無需引號）。環境變數使用字符串。

### 全域設定

```yaml
platforms:
  lansenger:
    extra:
      group_policy: open              # open | allowlist | disabled
      require_mention: true           # 群組中需要 @bot
      auto_mention_reply: false       # 群組回覆自動 @發送者
      auto_quote_reply: false         # 回覆自動引用 refMsgId（群組 + 私聊）
```

### 單一群組覆寫

```yaml
platforms:
  lansenger:
    extra:
      groups:
        "<group_id>":
          enabled: true
          require_mention: false
          auto_mention_reply: true
          auto_quote_reply: true
          allow_from:
            - "<staff_id>"
```

### 決策優先級（由上至下，首次匹配即生效）

1. 單一群組 `enabled: false` → 已封鎖
2. 單一群組 `allow_from` 非空且發送者不在列表中 → 已封鎖
3. 單一群組 `enabled: true` → 跳過全域策略
4. 全域 `group_policy` → `disabled` 封鎖全部 / `allowlist` 檢查全域列表
5. `require_mention`（單一群組 > 全域）為 true 且 `is_at_me=false` → 已封鎖

## 自動回覆功能

### autoMentionReply

啟用後，群組回覆會自動 @提及發送者。透過 `fromType` 區分：
- `fromType=0`（用戶）→ `reminder.userIds`
- `fromType=1`（應用/機械人）→ `reminder.botIds`

### autoQuoteReply

啟用後，回覆會自動包含引用原始訊息的 `refMsgId`。同時適用於群組聊天和私聊。

## 多工作區（Profiles）

Hermes 透過 Profiles 支援多個隔離的工作區：

```bash
hermes profile create bot-prod
hermes profile create bot-test
hermes -p bot-prod gateway start
hermes -p bot-test gateway start
```

每個 profile 都擁有獨立的 config.yaml、會話、記憶、技能、日誌及數據檔案（token、chat_type、owner）。

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