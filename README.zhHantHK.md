[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Hermes 藍信轉接器

> 💠 藍信 網關轉接器 + 媒體與訊息工具插件，供 Hermes Agent 使用。

透過 WebSocket 長連線接收即時訊息，並透過 HTTP API 發送訊息，將 Hermes Agent 連接至 藍信 — 一個企業訊息平台。

本repo包含**兩個插件**：

| 插件 | 類型 | 功能說明 |
|--------|------|-------------|
| `platforms/lansenger/` | platform | 網關頻道轉接器 — 接收與發送訊息 |
| `lansenger-tools/` | standalone (tool) | Agent 可呼叫的工具：發送檔案/圖片、撤回訊息、發送 linkCard |

## 功能特色

### 平台轉接器
- **即時訊息** — 透過 WebSocket 長連線實現
- **Markdown 支援** — 使用 `formatText` msgType
- **i18nAppCard** — 互動式審批流程卡片
- **主頻道自動偵測** — 首條 p2p 訊息自動設定預設發送目標
- **定時發送** — 透過 `standalone_sender_fn` 實現排程通知
- **使用者授權** — 透過環境變數設定允許的使用者 / 允許所有使用者
- **零核心修改** — 純插件模式，`git diff HEAD` 保持 PRISTINE

### 媒體與訊息工具插件
- **lansenger_send_file** — 發送任何本地檔案/圖片/影片至指定使用者或群組
- **lansenger_send_image_url** — 從 URL 發送圖片至指定使用者或群組
- **lansenger_revoke_message** — 撤回已發送的 藍信 訊息 🗑️
- **lansenger_send_link_card** — 發送 藍信 linkCard 卡片訊息 🔗
- **自動媒體類型偵測** — 根據副檔名自動分類圖片/影片/文件
- **憑證管控** — 未設定 LANSENGER_APP_ID/SECRET 時工具自動隱藏

## 快速安裝

### 透過 Hermes 插件管理器（推薦）

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### 手動安裝

將本 repo 複製至 `~/.hermes/plugins/`：

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

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## 媒體與訊息工具（來自 lansenger-tools）

這些工具讓 Agent 能夠發送檔案、圖片和影片，撤回訊息，以及發送 linkCard 卡片 — 所有工具均可由 LLM 獨立呼叫。憑證從環境變數（LANSENGER_APP_ID/SECRET）讀取，而非從 `load_gateway_config()` 讀取。

| 工具 | 參數 | 說明 |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | 傳送純文字，支援可選 @提及（僅群聊/員工群）與附件 |
| `lansenger_send_markdown` | `chat_id`, `message` | 傳送 Markdown 格式文字（不支援 @提及與附件） |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 發送本地檔案/圖片/影片至使用者或群組 |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 從 URL 下載圖片並以原生圖片發送 |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已發送的 藍信 訊息（系統提示為固定內容，不可自訂） |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | 發送 藍信 linkCard 卡片訊息 |

**使用範例（Agent 提示）：**

```
"將 report.pdf 發送給使用者 2285568-abc123"
"將圖表圖片分享至專案群組聊天"
"從此 URL 下載圖片並發送給我的同事"
"撤回我剛發送給該使用者的訊息"
"向使用者發送 link card，標題為「專案文件」，連結為 https://..."
```

**限制：**
- 檔案大小上限由組織的 藍信 設定決定（無固定上限）
- 媒體說明文字使用純文字（不支援 Markdown）— 如需 Markdown 格式文字，請另行發送
- `lansenger_send_file` 若未指定 media_type，會根據副檔名自動偵測
- `lansenger_revoke_message`：針對員工/群組聊天類型，必須提供 `sender_id`

## 架構

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # 根manifest（kind: bundle）
                          ├── platforms/lansenger/            # 網關轉接器
                          │   ├── plugin.yaml                 # manifest（kind: platform）
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # 完整轉接器（此處無工具處理器）
                          ├── lansenger-tools/           # 媒體與訊息工具
                          │   ├── plugin.yaml                 # manifest（kind: standalone）
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # LLM面向的工具描述
                          │   └── tools.py                     # 處理器實作
                          ├── skills/                          # Agent決策技能
                          │   └── lansenger-messaging.md       # 工具選擇策略 + token文件
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # pip入口點
                          └── .gitignore
```

## 依賴項

- `websockets` — WebSocket 客戶端，用於長連線
- `httpx` — HTTP 客戶端，用於 API 呼叫（媒體工具亦使用）

## 升級

升級到最新版本：

```bash
hermes plugins update hermes-lansenger-adapter
hermes gateway restart
```

## 更新日誌

### v2.6.0 — 审批流程升級：i18nAppCard → 動態 appCard

- **動態 appCard (isDynamic=True)**：審批、斜線確認、更新提示卡片改用 appCard，支持原地狀態更新（待審批 → 已批准/已拒絕），不再發送重複卡片。
- **語言檢測緩存**：`_user_lang_map` 從 inbound 訊息中用 CJK 啟發式檢測並緩存用戶語言偏好（zh/en），卡片內容自動選擇中/英文。預設中文。


### v2.5.0 — appArticles、appCard、動態卡片更新、群訊息路由、群ID查詢

### v2.4.2 — Home channel 自动升級

- **Home channel 自动升級**: 首次私聊对话自动设为蓝信 home channel。如果未配置 home_channel，或现有 home 是群聊，首次私聊会覆盖它（私聊 > 群聊升級）。靜默写入 config.yaml 和 os.environ，无用户提示。遵循元宝的 AutoSetHomeMiddleware 模式。

- **动态 Agent 簽名**（v2.4.1 起）：所有三个 i18nAppCard 方法均使用 `_build_agent_signature_i18n()`。

### v2.4.1 — send_update_prompt + 動態 Agent 簽名

- **send_update_prompt**: 新增 i18nAppCard 方法，用于 gateway `/update` watcher。卡片展示提示文本和 /approve、/deny 回复提示（i18nFields）。gateway 的文本攔截将 /approve → "y"、/deny → "n" 路由到 `update_prompt.resolve()`。蓝信没有 inline button 回调（如 Telegram/Discord），只能使用文字回覆。

- **動態 Agent 簽名**: 所有 i18nAppCard 卡片（send_update_prompt、send_exec_approval、send_slash_confirm）现在使用 `_build_agent_signature_i18n()`，从 `~/.hermes/SOUL.md` 動態读取 Agent 名称。SOUL.md 不可读时回退到 "Hermes"。不再硬編碼"Hermes 安全審批系統"——簽名现在反映實際的 Agent 人設。

### v2.4.0 — Bundle 安裝時展開 + 展開脚本

- **模組級展開**: 子插件（`lansenger-platform`、`lansenger-tools`）现在在 **import 时**就被複製到 `~/.hermes/plugins/` 頂層，而不是仅在 `register()` 中。這意味著它们在 gateway 重啟之前就能被 `hermes plugins enable` 發現（但仍需重啟才能加載）。

- **expand_sub_plugins.py**: 用于重啟前展開的獨立腳本。安装后運行 `python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py`，即可在首次 gateway 重啟前使子插件可被 `hermes plugins enable` 發現。

- **安装后文档**: 5 个语言版本明確警告：*不要手動 `hermes plugins enable` 子插件* — Bundle 在重啟时自动展開并启用。展開脚本作为重啟前启用的替代方案提供。

