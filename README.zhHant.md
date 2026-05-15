[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes 藍信轉接器

> 💠 藍信閘道轉接器 + 媒體與訊息工具插件，供 Hermes Agent 使用。

透過 WebSocket 長連線接收即時訊息，並透過 HTTP API 發送訊息，將 Hermes Agent 連接至藍信——一個企業即時通訊平台。

此儲存庫包含**兩個插件**：

| 插件 | 類型 | 功能說明 |
|--------|------|-------------|
| `platforms/lansenger/` | platform | 閘道通道轉接器——接收與發送訊息 |
| `lansenger-tools/` | standalone (tool) | Agent 可呼叫的工具：傳送訊息/卡片/檔案、撤回訊息、查詢群組 |

## 功能特色

### 平台轉接器
- **即時訊息傳遞**——透過 WebSocket 長連線（內建 ping/pong）
- **Markdown 支援**——使用 `formatText` msgType（可選 @提及，新版 API）
- **審批卡片**——appCard 支援審批後原地更新卡片狀態
- **首頁通道自動偵測**——第一條私聊訊息自動設定為預設傳送目標
- **聊天類型持久化**——入站 chat_id→群/私聊映射持久化，跨進程群路由
- **定時傳送**——透過 `standalone_sender_fn` 傳送排程通知
- **使用者授權**——透過環境變數設定允許的使用者或允許所有使用者
- **零核心修改**——純插件模式，`git diff HEAD` 保持 PRISTINE

### 媒體與訊息工具插件
- **lansenger_send_text** — 傳送純文字，可選 @提及和附件
- **lansenger_send_markdown** — 傳送 Markdown 文字，可選 @提及（新版 API，不支援附件）
- **lansenger_send_file** — 向指定使用者或群組傳送任何本地檔案/圖片/影片
- **lansenger_send_image_url** — 從 URL 下載圖片並傳送至指定使用者或群組
- **lansenger_revoke_message** — 撤回已傳送的訊息（僅 bot/group）
- **lansenger_send_link_card** — 傳送 linkCard 卡片訊息（spec 規定 6 個必填欄位）
- **lansenger_send_app_articles** — 傳送 appArticles 多文章卡片
- **lansenger_send_app_card** — 傳送 appCard 富卡片，可選動態更新
- **lansenger_update_dynamic_card** — 原地更新動態 appCard 狀態
- **lansenger_query_groups** — 查詢機器人的群 ID 列表
- **自動媒體類型偵測** — 依副檔名自動分類圖片/影片/文件
- **憑證管控** — 未設定 LANSENGER_APP_ID/SECRET 時工具隱藏

## 快速安裝

### 透過 Hermes 插件管理器（建議）

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### 手動安裝

將此儲存庫複製至 `~/.hermes/plugins/`：

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

> **注意：** Bundle 在首次閘道重啟時自動展開。子插件（`lansenger-platform` 和 `lansenger-tools`）會自動複製至 `~/.hermes/plugins/`、自動啟用於 `config.yaml` 並就地載入——無需為每個子插件分別執行 `hermes plugins enable`。

## 設定

### 必要環境變數

將以下內容加入 `~/.hermes/.env`：

| 變數 | 說明 |範例 |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | 機器人 App ID | `your-app-id` |
| `LANSENGER_APP_SECRET` | 機器人 App Secret | `your-app-secret` |

**憑證路徑：** 藍信桌面端 → 通訊錄 → 智慧機器人 → 個人機器人 → 點擊右側 ℹ️ 圖標查看憑證（行動端不支援查看憑證）

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

這些工具讓 Agent 能傳送訊息、檔案、圖片、卡片、撤回訊息、查詢群組——均可由 LLM 獨立呼叫。憑證從環境變數（LANSENGER_APP_ID/SECRET）讀取，而非透過 `load_gateway_config()`。

| 工具 | 參數 | 說明 |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`?, `file_path`?, `media_type`? | 傳送純文字，可選 @提及和附件 |
| `lansenger_send_markdown` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`? | 傳送 Markdown 文字，可選 @提及（新版 API，不支援附件） |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 傳送本地檔案/圖片/影片至使用者或群組 |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 從 URL 下載圖片並以原生圖片傳送 |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已傳送訊息（僅 bot/group；group 需要 sender_id） |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`, `icon_link`, `from_name`, `from_icon_link`, `pc_link`? | 傳送 linkCard 卡片（spec 規定 6 個必填欄位，pc_link 可選） |
| `lansenger_send_app_articles` | `chat_id`, `articles` | 傳送 appArticles 多文章卡片 |
| `lansenger_send_app_card` | `chat_id`, `body_title`, `head_title`?, `is_dynamic`?, `head_status_info`?, ... | 傳送 appCard 富卡片，可選動態更新 |
| `lansenger_update_dynamic_card` | `msg_id`, `head_status_info`?, `is_last_update`? | 原地更新動態 appCard 瀏覽狀態 |
| `lansenger_query_groups` | `page_offset`?, `page_size`? | 查詢機器人的群 ID 列表 |

**使用範例（Agent 提示）：**

```
"將 report.pdf 傳送給使用者 2285568-abc123"
"將該圖表圖片分享至專案群組聊天"
"下載此 URL 圖片並傳送給我的同事"
"撤回我剛傳送給使用者的訊息"
"傳送標題為「專案文件」且連結為 https://... 的 linkCard 卡片"
"傳送 appCard 審批卡片用於危險命令"
"將審批卡片狀態更新為「已批准」"
```

**限制：**
- 檔案大小上限由組織的藍信設定決定（無固定上限）
- 媒體說明文字使用純文字（不支援 Markdown）——若需 Markdown 格式文字，請另外傳送
- `lansenger_send_file` 若未指定 media_type，會依副檔名自動偵測
- `lansenger_revoke_message`：僅支援 bot/group 類型；group 需要 sender_id；系統提示固定不可自訂
- `lansenger_send_link_card`：spec 規定 6 個必填欄位（title, description, iconLink, link, fromName, fromIconLink）；pc_link 可選
- `lansenger_send_markdown` @提及：新版 API 能力；舊版靜默接受但不觸發通知
- 影片（mediaType=1）需要 2 個 mediaIds（影片+封面圖）

## 架構

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # 根 manifest（kind: bundle）
                          ├── platforms/lansenger/            # 閘道轉接器
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

## 依賴套件

- `websockets`——WebSocket 用戶端，用於長連線
- `httpx`——HTTP 用戶端，用於 API 呼叫（媒體工具亦使用）

## 升級

升級到最新版本：

```bash
hermes plugins update hermes-lansenger-adapter
hermes gateway restart
```

## 更新日誌

### v2.6.3 — Bug 修復 + 展開腳本自動安裝技能

- 修復 `_running` 標志：`connect()` 現在在建立 WS task 之前設定 `_running=True`（之前靜默退出）
- 修復模組頂層缺少 `import json` — `_persist_token()` 之前靜默失敗
- 展開腳本現在自動將技能安裝到 `~/.hermes/skills/lansenger/`（與子插件一起）
- 從安裝後文件中移除手動技能安裝步驟

### v2.6.2 — WS 日誌 + 文檔修復

- 改進 WS 連線生命週期日誌：完整端點回應、HTTP 錯誤詳情（狀態碼/回應體）、重連嘗試序號
- 修復日誌中 wsEndpoint URL 截斷問題（之前只顯示 ticket 的 4 個字元）
- 重新翻譯所有繁體中文檔案（zhHant/zhHantHK），消除簡體字混入；修復法文錯誤

### v2.6.1 — 訊息體審計 + formatText @提及

- formatText 支援 @提及（reminder）；舊版 API 靜默接受不觸發通知
- 撤回僅支援 bot/group；linkCard 6 個必填欄位；appArticles pcUrl 改為可選
- 移除手動 WS 心跳（使用 websockets 內建 ping/pong）；chat_type_map 持久化支援群路由

### v2.6.0 — 審批卡片支援動態狀態更新

- 審批卡片支援審批後原地更新卡片狀態
- 按使用者語言偵測傳送對應語言內容（中/英）
- 修復 bodyContent 縮進問題：text-indent 設為 0em

### v2.5.0 — appArticles、appCard、動態卡片更新、群訊息路由、群 ID 查詢

- appArticles、appCard、動態卡片更新、群訊息路由、群 ID 查詢

### v2.4.2 — Home channel 自動升級

- Home channel 自動升級（DM > 群）

### v2.4.1 — send_update_prompt + 動態 Agent 簽名

- send_update_prompt + 動態 Agent 签名

### v2.4.0 — Bundle 安裝時展開 + 展開腳本

- Bundle 安裝時自動展開

### v2.3.2 (2026-05-12)

- Bug 修復：`_make_config()` platform 參數

### v2.3.1 (2026-05-12)

- Bug 修復：`_get_adapter_class()` 路徑

### v2.3.0 (2026-05-12)

- Bundle 自動展開 + 簡化安裝流程

### v2.2.0 (2026-05-11)

- Reminder (@提及) 支援（群聊）

### v2.1.0 (2026-05-11)

- 插件模式遷移——零核心修改

## 授權條款

MIT——詳見 [LICENSE](LICENSE)。