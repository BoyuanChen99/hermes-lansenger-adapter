[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes 藍信轉接器

> 💠 藍信網關轉接器 + 媒體與訊息工具插件，供 Hermes Agent 使用。

透過 WebSocket 長連線接收即時訊息，並透過 HTTP API 發送訊息，將 Hermes Agent 連接至藍信——一個企業訊息平台。

本儲存庫包含**兩個插件**：

| 插件 | 類型 | 功能說明 |
|--------|------|-------------|
| `platforms/lansenger/` | platform | 網關通道轉接器——接收與發送訊息 |
| `lansenger-tools/` | standalone (tool) | Agent 可呼叫的工具：發送訊息/卡片/檔案、撤回訊息、查詢群組 |

## 功能特色

### 平台轉接器
- **即時訊息**——透過 WebSocket 長連線實現（內建 ping/pong）
- **Markdown 支援**——使用 `formatText` msgType（可選 @提及，新版 API）
- **審批卡片**——appCard 支援審批後原地更新卡片狀態
- **主頻道自動偵測**——首條私聊訊息自動設定預設發送目標
- **聊天類型持久化**——入站 chat_id→群/私聊映射持久化，跨進程群路由
- **定時發送**——透過 `standalone_sender_fn` 發送排程通知
- **使用者授權**——透過環境變數設定允許的使用者 / 允許所有使用者
- **零核心修改**——純插件模式，`git diff HEAD` 保持 PRISTINE
- **群組聊天策略**——開放/白名單/停用，支援逐群覆寫（require_mention、auto_mention_reply、auto_quote_reply、allow_from 發送者過濾）
- **自動 @提及回覆**——在群組回覆中自動 @提及發送者（使用者使用 userIds，機械人使用 botIds，根據 fromType 0/1 判斷）
- **自動引用回覆**——自動包含引用入站訊息的 refMsgId（群組 + 私聊）
- **多工作區支援**——遵循 HERMES_HOME 環境變數；所有 token/chat_type/owner 檔案作用域限定於當前設定檔
- **FormatText 入站解析**——正確解析來自 OpenClaw 及其他機械人的 msgType=format Markdown 訊息

### 媒體與訊息工具插件
- **lansenger_send_text** — 發送純文字，可選 @提及和附件
- **lansenger_send_markdown** — 發送 Markdown 文字，可選 @提及（新版 API，不支援附件）
- **lansenger_send_file** — 向指定使用者或群組發送任何本地檔案/圖片/影片
- **lansenger_send_image_url** — 從 URL 下載圖片並發送至指定使用者或群組
- **lansenger_revoke_message** — 撤回已發送的訊息（僅 bot/group）
- **lansenger_send_link_card** — 發送 linkCard 卡片訊息（spec 規定 6 個必填欄位）
- **lansenger_send_app_articles** — 發送 appArticles 多文章卡片
- **lansenger_send_app_card** — 發送 appCard 富卡片，可選動態更新
- **lansenger_update_dynamic_card** — 原地更新動態 appCard 瀏覽狀態
- **lansenger_query_groups** — 查詢機械人的群 ID 列表
- **自動媒體類型偵測** — 依副檔名自動分類圖片/影片/文件
- **憑證管控** — 未設定 LANSENGER_APP_ID/SECRET 時工具自動隱藏

## 快速安裝

### 透過 Hermes 插件管理器（推薦）

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### 手動安裝

將本儲存庫複製至 `~/.hermes/plugins/`：

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### 透過 pip（進階）

```bash
pip install hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

> **注意：** Bundle 在首次網關重啟時自動展開。子插件（`lansenger-platform` 和 `lansenger-tools`）會自動複製至 `~/.hermes/plugins/`、自動啟用於 `config.yaml` 並就地載入——無需為每個子插件分別執行 `hermes plugins enable`。

## 設定

### 必要環境變數

將以下內容加入 `~/.hermes/.env`：

| 變數 | 說明 | 範例 |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | Bot App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | Bot App Secret | `your-app-secret` |

**憑證路徑：** 藍信桌面端 → 通訊錄 → 智能機械人 → 個人機械人 → 點擊右側 ℹ️ 圖標查看憑證（行動端不支援查看憑證）

### 可選環境變數

| 變數 | 說明 | 預設值 |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API 網關 URL | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | 允許的使用者 ID（以逗號分隔） | — |
| `LANSENGER_ALLOW_ALL_USERS` | 允許任何使用者（僅限開發用途） | `false` |
| `LANSENGER_HOME_CHANNEL` | 預設定時發送聊天 ID | 自動偵測 |
| `LANSENGER_HOOK_LOGGING` | 啟用/停用鉤子日誌 | `true` |

### config.yaml

憑證可透過環境變數（建議）或 config.yaml 設定。環境變數優先級較高。

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      # 憑證（若已透過環境變數設定則可省略；環境變數優先）
      # app_id: "your-app-id"
      # app_secret: "your-app-secret"
      # api_gateway_url: "https://open.e.lanxin.cn/open/apigw"
      # 可選：停用鉤子日誌（預設：true）
      # hook_logging: false
```

## 媒體與訊息工具（來自 lansenger-tools）

這些工具讓 Agent 能發送訊息、檔案、圖片、卡片、撤回訊息、查詢群組——均可由 LLM 獨立呼叫。憑證從環境變數（LANSENGER_APP_ID/SECRET）讀取，而非從 `load_gateway_config()`。

| 工具 | 參數 | 說明 |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`?, `file_path`?, `media_type`? | 發送純文字，可選 @提及和附件 |
| `lansenger_send_markdown` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`? | 發送 Markdown 文字，可選 @提及（新版 API，不支援附件） |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 發送本地檔案/圖片/影片至使用者或群組 |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 從 URL 下載圖片並以原生圖片發送 |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已發送訊息（僅 bot/group；group 需要 sender_id） |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`, `icon_link`, `from_name`, `from_icon_link`, `pc_link`? | 發送 linkCard 卡片（spec 規定 6 個必填欄位，pc_link 可選） |
| `lansenger_send_app_articles` | `chat_id`, `articles` | 發送 appArticles 多文章卡片 |
| `lansenger_send_app_card` | `chat_id`, `body_title`, `head_title`?, `is_dynamic`?, `head_status_info`?, ... | 發送 appCard 富卡片，可選動態更新 |
| `lansenger_update_dynamic_card` | `msg_id`, `head_status_info`?, `is_last_update`? | 原地更新動態 appCard 瀏覽狀態 |
| `lansenger_query_groups` | `page_offset`?, `page_size`? | 查詢機械人的群 ID 列表 |

**使用範例（Agent 提示）：**

```
"將 report.pdf 發送給使用者 2285568-abc123"
"將該圖表圖片分享至專案群組聊天"
"從此 URL 下載圖片並發送給我的同事"
"撤回我剛發送給該使用者的訊息"
"發送標題為「專案文件」且連結為 https://... 的 linkCard 卡片"
"發送 appCard 審批卡片用於危險命令"
"將審批卡片狀態更新為「已批准」"
```

**限制：**
- 檔案大小上限由組織的藍信設定決定（無固定上限）
- 媒體說明文字使用純文字（不支援 Markdown）——如需 Markdown 格式文字，請另行發送
- `lansenger_send_file` 若未指定 media_type，會依副檔名自動偵測
- `lansenger_revoke_message`：僅支援 bot/group 類型；group 需要 sender_id；系統提示固定不可自訂
- `lansenger_send_link_card`：spec 規定 6 個必填欄位（title, description, iconLink, link, fromName, fromIconLink）；pc_link 可選
- `lansenger_send_markdown` @提及：新版 API 能力；舊版靜默接受但不觸發通知
- 影片（mediaType=1）需要 2 個 mediaIds：[videoId, coverImageId]（影片和封面圖分別上載後組合）

## 架構

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # 根 manifest（kind: bundle）
                          ├── platforms/lansenger/            # 網關轉接器
                          │   ├── plugin.yaml                 # manifest（kind: platform）
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # 完整轉接器（此處無工具處理器）
                          ├── lansenger-tools/           # 媒體與訊息工具
                          │   ├── plugin.yaml                 # manifest（kind: standalone）
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM 工具描述
                          │   └── tools.py                     # 處理器實作
                          ├── skills/                          # Agent 決策技能
                          │   └── lansenger-messaging/           # skill 目錄 (SKILL.md + references/)
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # pip 入口點
                          └── .gitignore
```

## 依賴項

- `websockets`——WebSocket 客戶端，用於長連線
- `httpx`——HTTP 客戶端，用於 API 呼叫（媒體工具亦使用）

## 升級

升級到最新版本：

```bash
hermes plugins update hermes-lansenger-adapter
hermes gateway restart
```

## 更新日誌

詳見 [CHANGELOG.md](CHANGELOG.md)。

## 授權條款

MIT——詳見 [LICENSE](LICENSE)。