[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes 藍信轉接器

> 💠 藍信 閘道適配器 + 媒體與訊息工具插件，供 Hermes Agent 使用。

透過 WebSocket 長連線接收即時訊息，並透過 HTTP API 發送訊息，將 Hermes Agent 連接至 藍信——一個企業即時通訊平台。

此儲存庫包含**兩個插件**：

| 插件 | 類型 | 功能說明 |
|--------|------|-------------|
| `platforms/lansenger/` | platform | 閘道通道適配器——接收與發送訊息 |
| `lansenger-tools/` | standalone (tool) | Agent 可呼叫的工具：傳送檔案/圖片、撤回訊息、傳送 linkCard |

## 功能特色

### 平台適配器
- **即時訊息傳遞**——透過 WebSocket 長連線
- **Markdown 支援**——使用 `formatText` msgType
- **i18nAppCard**——互動式審批流程卡片
- **首頁通道自動偵測**——第一條私聊訊息自動設定為預設傳送目標
- **定時傳送**——透過 `standalone_sender_fn` 發送排程通知
- **使用者授權**——透過環境變數設定允許的使用者或允許所有使用者
- **零核心修改**——純插件模式，`git diff HEAD` 保持 PRISTINE

### 媒體與訊息工具插件
- **lansenger_send_file**——傳送任何本地檔案/圖片/影片至指定使用者或群組
- **lansenger_send_image_url**——透過 URL 傳送圖片至指定使用者或群組
- **lansenger_revoke_message**——撤回已傳送的 藍信 訊息 🗑️
- **lansenger_send_link_card**——傳送 藍信 linkCard 卡片訊息 🔗
- **自動媒體類型偵測**——依副檔名自動分類圖片/影片/文件
- **憑證管控**——未設定 LANSENGER_APP_ID/SECRET 时工具隱藏

## 快速安裝

### 透過 Hermes 插件管理器（建議）

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### 手動安裝

將此儲存庫複製至 `~/.hermes/plugins/`：

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

### 透過 pip（進階）

```bash
pip install hermes-lansenger-adapter
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-tools
hermes gateway restart
```

## 設定

### 必要環境變數

將以下內容加入 `~/.hermes/.env`：

| 變數 | 說明 |範例 |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | 機器人 App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | 機器人 App Secret | `your-app-secret` |

**憑證路徑：** 藍信 用戶端 → 通訊錄 → 個人機器人 → 建立機器人 → 詳情

### 可選環境變數

| 變數 | 說明 | 預設值 |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API 閘道 URL | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | 允許的使用者 ID（以逗號分隔） | — |
| `LANSENGER_ALLOW_ALL_USERS` | 允許任何使用者（僅限開發環境） | `false` |
| `LANSENGER_HOME_CHANNEL` | 預設排程傳送聊天 ID | 自動偵測 |

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## 媒體與訊息工具（來自 lansenger-tools）

這些工具讓 Agent 能傳送檔案、圖片、影片、撤回訊息及傳送 linkCard 卡片——均可由 LLM 狨立呼叫。憑證從環境變數（LANSENGER_APP_ID/SECRET）讀取，而非透過 `load_gateway_config()`。

| 工具 | 參數 | 說明 |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | 傳送純文字，支援可選 @提及（僅群聊/員工群）與附件 |
| `lansenger_send_markdown` | `chat_id`, `message` | 傳送 Markdown 格式文字（不支援 @提及與附件） |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 傳送本地檔案/圖片/影片至使用者或群組 |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 從 URL 下載圖片並以原生圖片傳送 |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已傳送的 藍信 訊息（系統提示固定，不可自訂） |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | 傳送 藍信 linkCard 卡片訊息 |

**使用範例（Agent 提示）：**

```
"將 report.pdf 傳送給使用者 2285568-abc123"
"將該圖表圖片分享至專案群組聊天"
"下載此 URL 圖片並傳送給我的同事"
"撤回我剛傳送給使用者的訊息"
"傳送 link card 至使用者，標題為「專案文件」，連結為 https://..."
```

**限制：**
- 檔案大小上限由組織的 藍信 設定決定（無固定上限）
- 媒體說明文字使用純文字（不支援 Markdown）——若需 Markdown 格式文字，請另外傳送
- `lansenger_send_file` 若未指定 media_type，會依副檔名自動偵測
- `lansenger_revoke_message`：針對員工/群組聊天類型，`sender_id` 必填

## 架構

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # 根 manifest（kind: bundle）
                          ├── platforms/lansenger/            # 閘道適配器
                          │   ├── plugin.yaml                 # manifest（kind: platform）
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # 完整適配器（此處無工具處理器）
                          ├── lansenger-tools/           # 媒體與訊息工具
                          │   ├── plugin.yaml                 # manifest（kind: standalone）
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM 工具描述
                          │   └── tools.py                     # 處理器實作
                          ├── skills/                          # Agent 决策技能
                          │   └── lansenger-messaging.md       # 工具選擇策略 + token 文件
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # pip 入口點
                          └── .gitignore
```

## 依賴套件

- `websockets`——WebSocket 用戶端，用於長連線
- `httpx`——HTTP 用戶端，用於 API 呼叫（媒體工具亦使用）

## 更新日誌

### v2.2.0 (2026-05-11)

- ✅ 實作了 `reminder`（@提及）功能——`reminder_all`（bool，@全體）+ `reminder_user_ids`（array，指定使用者），對應藍信 API 的 `reminder` 物件
- ✅ @提及僅在群聊/員工群生效；私聊不支援
- ✅ 修復 `at_user_ids` schema 欄位定義了但從未傳入轉接器方法的問題

### v2.1.0 (2026-05-11)

- 🔄 遷移至插件模式 — 零核心程式碼修改
- ✅ `ctx.register_platform()` 用於轉接器注入
- ✅ `standalone_sender_fn` 用於定時任務投遞
- ✅ 主頻道自動偵測
- ✅ 透過環境變數實現使用者授權
- ✅ i18nAppCard 審批流程卡片
- ✅ 媒體與訊息工具插件 — `lansenger_send_file`、`lansenger_send_image_url`
- ✅ `lansenger_revoke_message` 和 `lansenger_send_link_card` 從轉接器中提取為獨立工具插件
- ✅ 在藍信轉接器中實作 `send_link_card()` 方法（此前缺失）
- ✅ 修復撤回/linkCard「藍信未設定」錯誤 — 現從環境變數讀取而非 `load_gateway_config()`

## 授權條款

MIT——詳見 [LICENSE](LICENSE)。