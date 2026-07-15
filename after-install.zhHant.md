[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信轉接器——安裝後設定

一個 Bundle 插件和兩個技能已安裝：

1. **hermes-lansenger-adapter** — Bundle 容器（自動展開為 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 選擇正確藍信工具的技能
3. **lansenger-setup** — 教 Agent 如何配置藍信插件的技能

> ⚠️ **不要手動執行 `hermes plugins enable lansenger-platform` 或 `hermes plugins enable lansenger-tools`** — Bundle 在閘道重啟時會自動展開並啟用兩個子插件。手動啟用會失敗，因為子插件此時還在 Bundle 內部。

## 設定

### 方式 A：互動式設定向導（建議）

執行內建的設定向導——它會逐步引導您完成每個憑證的設定：

```bash
hermes setup gateway
```

從平台清單中選擇 **Lansenger**，然後貼上您的 App ID、App Secret，並提供 API 閘道 URL（例如 `https://your-api-gateway-url`）。已設定的值會顯示出來（密鑰會被遮掩），可以覆蓋修改。

> 💡 App ID 與 App Secret 可在藍信桌面端 → 通訊錄 → 智慧機器人 → 個人機器人 → ℹ️ 圖標中找到（行動端不支援查看憑證）

### 方式 B：config.yaml

將以下內容加入 `~/.hermes/config.yaml` 的 `platforms.lansenger` 下：

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      app_id: "YOUR_APP_ID"
      app_secret: "YOUR_APP_SECRET"
      api_gateway_url: "https://your-api-gateway-url"   # 必填
```

### 方式 C：.env 檔案（手動）

編輯 `~/.hermes/.env`，加入以下內容：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://your-api-gateway-url
```

## 重啟閘道

設定完成後，重啟 Hermes 閘道：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 應在 Plugin toolsets 段顯示 `lansenger-tools`
- `hermes plugins list` 應顯示 `lansenger-platform` 和 `lansenger-tools` 已啟用（Bundle 自動展開）

## 群聊配置

所有設定使用 **YAML 原生布林值**（`true`/`false`，不加引號）。環境變數使用字串。

### 全域設定

```yaml
platforms:
  lansenger:
    extra:
      group_policy: open              # open | allowlist | disabled
      require_mention: true           # 群組中需要 @bot
      respond_to_at_all: false       # require_mention=true 時不回應 @all
      auto_mention_reply: false       # 群組回覆自動 @發送者
      auto_quote_reply: false         # 自動引用原訊息（群組+私聊）
```

### 按群覆寫

```yaml
platforms:
  lansenger:
    extra:
      groups:
        "<群組 ID>":
          enabled: true
          require_mention: false
          respond_to_at_all: false
          auto_mention_reply: true
          auto_quote_reply: true
          allow_from:
            - "<staff ID>"
```

### 決策優先級（從上到下，命中即停止）

1. 單一群組 `enabled: false` → 封鎖
2. 單一群組 `allow_from` 非空且發送者不在列表 → 封鎖
3. 單一群組 `enabled: true` → 跳過全域策略
4. 全域 `group_policy` → `disabled` 封鎖全部 / `allowlist` 檢查 `groups` 配置 map 的 key
5. 全域 `group_allow_from`（發送者級別）非空且發送者不在列表 → 封鎖
6. `require_mention`（per-group > 全域）為 true 且 `is_at_me=false` → 拒絕（`respond_to_at_all` 預設 false，@all 不回應）

## 自動回覆功能

### autoMentionReply（自動 @傳送者）

啟用後，群聊回覆自動 @傳送者。根據 `fromType` 區分：
- `fromType=0`（使用者）→ `reminder.userIds`
- `fromType=1`（應用/機器人）→ `reminder.botIds`

### autoQuoteReply（自動引用訊息）

啟用後，回覆自動攜帶 `refMsgId` 引用原訊息。群聊和私聊都支援。

## 斜杠命令

啟動時適配器自動將所有 Hermes 內建和外掛程式的斜杠命令（如 `/help`、`/status`、`/approve`）註冊到藍信 Bot API。命令將出現在藍信聊天輸入欄中。

### 關閉自動註冊

```yaml
platforms:
  lansenger:
    extra:
      commands:
        native: false   # 按 profile 禁用斜杠命令註冊
```

或透過環境變數全域關閉：`LANSENGER_SLASH_COMMANDS_NATIVE=0`

### 命令權限

控制哪些聊天可以看見每個命令：

```yaml
platforms:
  lansenger:
    extra:
      command_permissions:
        approve: owner       # 僅主人可看到
        status: everyone     # 所有聊天可看到（預設）
        restart: disabled    # 完全排除此命令
```

| 權限 | 生效範圍 |
|------|----------|
| `owner` | 僅主人私聊 |
| `admin` | 主人私聊 + 所有群管理員 |
| `everyone` | 主人私聊 + 所有群（預設） |
| `disabled` | 命令從註冊中排除 |

## 危險命令審批

當 Hermes 偵測到危險命令（如 `rm -rf`、`curl | sh`、`chmod 777`），會暫停執行並發送一個帶有可點擊按鈕的 **approveCard**。直接透過以下方式批准或拒絕：

- 點擊卡片上的按鈕
- 回覆 `/approve`、`/approve session`、`/approve always` 或 `/deny`

卡片會原地更新顯示決策結果（如「已允許執行一次」）。如果伺服端不支援 approveCard 會自動降級為 appCard。

## 多 Workspace（Profiles）

支援多組藍信憑證透過 Hermes profiles 管理：

```bash
hermes profile create my-org \
  --set platforms.lansenger.enabled=true \
  --set platforms.lansenger.extra.app_id=YOUR_APP_ID \
  --set platforms.lansenger.extra.app_secret=YOUR_APP_SECRET
```

```bash
hermes profile use my-org
```

## 工具總覽

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
