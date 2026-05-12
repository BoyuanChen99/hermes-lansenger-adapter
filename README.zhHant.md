     1|     1|     1|[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)
     2|     2|     2|
     3|     3|     3|# Hermes 藍信轉接器
     4|     4|     4|
     5|     5|     5|> 💠 藍信 閘道適配器 + 媒體與訊息工具插件，供 Hermes Agent 使用。
     6|     6|     6|
     7|     7|     7|透過 WebSocket 長連線接收即時訊息，並透過 HTTP API 發送訊息，將 Hermes Agent 連接至 藍信——一個企業即時通訊平台。
     8|     8|     8|
     9|     9|     9|此儲存庫包含**兩個插件**：
    10|    10|    10|
    11|    11|    11|| 插件 | 類型 | 功能說明 |
    12|    12|    12||--------|------|-------------|
    13|    13|    13|| `platforms/lansenger/` | platform | 閘道通道適配器——接收與發送訊息 |
    14|    14|    14|| `lansenger-tools/` | standalone (tool) | Agent 可呼叫的工具：傳送檔案/圖片、撤回訊息、傳送 linkCard |
    15|    15|    15|
    16|    16|    16|## 功能特色
    17|    17|    17|
    18|    18|    18|### 平台適配器
    19|    19|    19|- **即時訊息傳遞**——透過 WebSocket 長連線
    20|    20|    20|- **Markdown 支援**——使用 `formatText` msgType
    21|    21|    21|- **i18nAppCard**——互動式審批流程卡片
    22|    22|    22|- **首頁通道自動偵測**——第一條私聊訊息自動設定為預設傳送目標
    23|    23|    23|- **定時傳送**——透過 `standalone_sender_fn` 發送排程通知
    24|    24|    24|- **使用者授權**——透過環境變數設定允許的使用者或允許所有使用者
    25|    25|    25|- **零核心修改**——純插件模式，`git diff HEAD` 保持 PRISTINE
    26|    26|    26|
    27|    27|    27|### 媒體與訊息工具插件
    28|    28|    28|- **lansenger_send_file**——傳送任何本地檔案/圖片/影片至指定使用者或群組
    29|    29|    29|- **lansenger_send_image_url**——透過 URL 傳送圖片至指定使用者或群組
    30|    30|    30|- **lansenger_revoke_message**——撤回已傳送的 藍信 訊息 🗑️
    31|    31|    31|- **lansenger_send_link_card**——傳送 藍信 linkCard 卡片訊息 🔗
    32|    32|    32|- **自動媒體類型偵測**——依副檔名自動分類圖片/影片/文件
    33|    33|    33|- **憑證管控**——未設定 LANSENGER_APP_ID/SECRET 时工具隱藏
    34|    34|    34|
    35|    35|    35|## 快速安裝
    36|    36|    36|
    37|    37|    37|### 透過 Hermes 插件管理器（建議）
    38|    38|    38|
    39|    39|    39|```bash
    40|    40|    40|hermes plugins install lansenger-pm/hermes-lansenger-adapter
    41|    41|    41|hermes plugins enable hermes-lansenger-adapter
    42|    42|    42|hermes gateway restart
    43|    43|    43|```
    44|    44|    44|
    45|    45|    45|### 手動安裝
    46|    46|    46|
    47|    47|    47|將此儲存庫複製至 `~/.hermes/plugins/`：
    48|    48|    48|
    49|    49|    49|```bash
    50|    50|    50|cd ~/.hermes/plugins/
    51|    51|    51|git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
    52|    52|    52|hermes plugins enable hermes-lansenger-adapter
    53|    53|    53|hermes gateway restart
    54|    54|    54|```
    55|    55|    55|
    56|    56|    56|### 透過 pip（進階）
    57|    57|    57|
    58|    58|    58|```bash
    59|    59|    59|pip install hermes-lansenger-adapter
    60|    60|    60|hermes plugins enable hermes-lansenger-adapter
    61|    61|    61|hermes gateway restart
    62|    62|    62|```
    63|    63|    63|
    64|    64|    64|## 設定
    65|    65|    65|
    66|    66|    66|### 必要環境變數
    67|    67|    67|
    68|    68|    68|將以下內容加入 `~/.hermes/.env`：
    69|    69|    69|
    70|    70|    70|| 變數 | 說明 |範例 |
    71|    71|    71||----------|-------------|---------|
    72|    72|    72|| `LANSENGER_APP_ID` | 機器人 App ID | `your-app-id` |
    73|    73|    73|| `LANSENGER_APP_SECRET` | 機器人 App Secret | `your-app-secret` |
    74|    74|    74|
    75|    75|    75|**憑證路徑：** 藍信桌面端 → 通訊錄 → 智能機器人 → 個人機器人 → 點擊右側 ℹ️ 圖標查看憑證（行動端不支援查看憑證）
    76|    76|    76|
    77|    77|    77|### 可選環境變數
    78|    78|    78|
    79|    79|    79|| 變數 | 說明 | 預設值 |
    80|    80|    80||----------|-------------|---------|
    81|    81|    81|| `LANSENGER_API_GATEWAY_URL` | API 閘道 URL | `https://open.e.lanxin.cn/open/apigw` |
    82|    82|    82|| `LANSENGER_ALLOWED_USERS` | 允許的使用者 ID（以逗號分隔） | — |
    83|    83|    83|| `LANSENGER_ALLOW_ALL_USERS` | 允許任何使用者（僅限開發環境） | `false` |
    84|    84|    84|| `LANSENGER_HOME_CHANNEL` | 預設排程傳送聊天 ID | 自動偵測 |
    85|    85|    85|
    86|    86|    86|### config.yaml
    87|    87|    87|
    88|    88|    88|```yaml
    89|    89|    89|platforms:
    90|    90|    90|  lansenger:
    91|    91|    91|    enabled: true
    92|    92|    92|```
    93|    93|    93|
    94|    94|    94|## 媒體與訊息工具（來自 lansenger-tools）
    95|    95|    95|
    96|    96|    96|這些工具讓 Agent 能傳送檔案、圖片、影片、撤回訊息及傳送 linkCard 卡片——均可由 LLM 狨立呼叫。憑證從環境變數（LANSENGER_APP_ID/SECRET）讀取，而非透過 `load_gateway_config()`。
    97|    97|    97|
    98|    98|    98|| 工具 | 參數 | 說明 |
    99|    99|    99||------|-----------|-------------|
   100|   100|   100|| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | 傳送純文字，支援可選 @提及（僅群聊/員工群）與附件 |
   101|   101|   101|| `lansenger_send_markdown` | `chat_id`, `message` | 傳送 Markdown 格式文字（不支援 @提及與附件） |
   102|   102|   102|| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 傳送本地檔案/圖片/影片至使用者或群組 |
   103|   103|   103|| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 從 URL 下載圖片並以原生圖片傳送 |
   104|   104|   104|| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已傳送的 藍信 訊息（系統提示固定，不可自訂） |
   105|   105|   105|| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | 傳送 藍信 linkCard 卡片訊息 |
   106|   106|   106|
   107|   107|   107|**使用範例（Agent 提示）：**
   108|   108|   108|
   109|   109|   109|```
   110|   110|   110|"將 report.pdf 傳送給使用者 2285568-abc123"
   111|   111|   111|"將該圖表圖片分享至專案群組聊天"
   112|   112|   112|"下載此 URL 圖片並傳送給我的同事"
   113|   113|   113|"撤回我剛傳送給使用者的訊息"
   114|   114|   114|"傳送 link card 至使用者，標題為「專案文件」，連結為 https://..."
   115|   115|   115|```
   116|   116|   116|
   117|   117|   117|**限制：**
   118|   118|   118|- 檔案大小上限由組織的 藍信 設定決定（無固定上限）
   119|   119|   119|- 媒體說明文字使用純文字（不支援 Markdown）——若需 Markdown 格式文字，請另外傳送
   120|   120|   120|- `lansenger_send_file` 若未指定 media_type，會依副檔名自動偵測
   121|   121|   121|- `lansenger_revoke_message`：針對員工/群組聊天類型，`sender_id` 必填
   122|   122|   122|
   123|   123|   123|## 架構
   124|   124|   124|
   125|   125|   125|```
   126|   126|   126|hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
   127|   127|   127|                          ├── plugin.yaml                     # 根 manifest（kind: bundle）
   128|   128|   128|                          ├── platforms/lansenger/            # 閘道適配器
   129|   129|   129|                          │   ├── plugin.yaml                 # manifest（kind: platform）
   130|   130|   130|                          │   ├── __init__.py                  # register() → ctx.register_platform()
   131|   131|   131|                          │   └── adapter.py                   # 完整適配器（此處無工具處理器）
   132|   132|   132|                          ├── lansenger-tools/           # 媒體與訊息工具
   133|   133|   133|                          │   ├── plugin.yaml                 # manifest（kind: standalone）
   134|   134|   134|                          │   ├── __init__.py                  # register() → ctx.register_tool()
   135|   135|   135|                          │   ├── schemas.py                   # LLM 工具描述
   136|   136|   136|                          │   └── tools.py                     # 處理器實作
   137|   137|   137|                          ├── skills/                          # Agent 决策技能
   138|   138|   138|                          │   └── lansenger-messaging.md       # 工具選擇策略 + token 文件
   139|   139|   139|                          ├── README.md
   140|   140|   140|                          ├── LICENSE
   141|   141|   141|                          ├── VERSION
   142|   142|   142|                          ├── after-install.md
   143|   143|   143|                          ├── pyproject.toml                   # pip 入口點
   144|   144|   144|                          └── .gitignore
   145|   145|   145|```
   146|   146|   146|
   147|   147|   147|## 依賴套件
   148|   148|   148|
   149|   149|   149|- `websockets`——WebSocket 用戶端，用於長連線
   150|   150|   150|- `httpx`——HTTP 用戶端，用於 API 呼叫（媒體工具亦使用）
   151|   151|   151|
   152|   152|   152|## 升級
   153|   153|   153|
   154|   154|   154|升級到最新版本：
   155|   155|   155|
   156|   156|   156|```bash
   157|   157|   157|hermes plugins update hermes-lansenger-adapter
   158|   158|   158|hermes gateway restart
   159|   159|   159|```
   160|   160|   160|
   161|   161|   161|## 更新日誌
   162|   162|   162|
   163|   163|   163|### v2.6.0 — 审批流程升級：i18nAppCard → 動態 appCard
   164|   164|   164|
   165|   165|   165|- **動態 appCard (isDynamic=True)**：審批、斜線確認、更新提示卡片改用 appCard，支持原地狀態更新（待審批 → 已批准/已拒絕），不再發送重複卡片。
   166|   166|   166|- **語言檢測緩存**：`_user_lang_map` 從 inbound 訊息中用 CJK 啟發式檢測並緩存用戶語言偏好（zh/en），卡片內容自動選擇中/英文。預設中文。
   167|   167|   167|
   168|   168|   168|
   169|   169|   169|### v2.5.0 — appArticles、appCard、動態卡片更新、群訊息路由、群ID查詢
   170|   170|   170|
   171|   171|   171|### v2.4.2 — Home channel 自动升級
   172|   172|   172|
   173|   173|   173|- **Home channel 自动升級**: 首次私聊对话自动设为蓝信 home channel。如果未配置 home_channel，或现有 home 是群聊，首次私聊会覆盖它（私聊 > 群聊升級）。靜默写入 config.yaml 和 os.environ，无用户提示。遵循元宝的 AutoSetHomeMiddleware 模式。
   174|   174|   174|
   175|   175|   175|- **动态 Agent 簽名**（v2.4.1 起）：所有三个 i18nAppCard 方法均使用 `_build_agent_signature_i18n()`。
   176|   176|   176|
   177|   177|   177|### v2.4.1 — send_update_prompt + 動態 Agent 簽名
   178|   178|   178|
   179|   179|   179|- **send_update_prompt**: 新增 i18nAppCard 方法，用于 gateway `/update` watcher。卡片展示提示文本和 /approve、/deny 回复提示（i18nFields）。gateway 的文本攔截将 /approve → "y"、/deny → "n" 路由到 `update_prompt.resolve()`。蓝信没有 inline button 回调（如 Telegram/Discord），只能使用文字回覆。
   180|   180|   180|
   181|   181|   181|- **動態 Agent 簽名**: 所有 i18nAppCard 卡片（send_update_prompt、send_exec_approval、send_slash_confirm）现在使用 `_build_agent_signature_i18n()`，从 `~/.hermes/SOUL.md` 動態读取 Agent 名称。SOUL.md 不可读时回退到 "Hermes"。不再硬編碼"Hermes 安全審批系統"——簽名现在反映實際的 Agent 人設。
   182|   182|   182|
   183|   183|   183|### v2.4.0 — Bundle 安裝時展開 + 展開脚本
   184|   184|   184|
   185|   185|   185|- **模組級展開**: 子插件（`lansenger-platform`、`lansenger-tools`）现在在 **import 时**就被複製到 `~/.hermes/plugins/` 頂層，而不是仅在 `register()` 中。這意味著它们在 gateway 重啟之前就能被 `hermes plugins enable` 發現（但仍需重啟才能加載）。
   186|   186|   186|
   187|   187|   187|- **expand_sub_plugins.py**: 用于重啟前展開的獨立腳本。安装后運行 `python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py`，即可在首次 gateway 重啟前使子插件可被 `hermes plugins enable` 發現。
   188|   188|   188|
   189|   189|   189|- **安装后文档**: 5 个语言版本明確警告：*不要手動 `hermes plugins enable` 子插件* — Bundle 在重啟时自动展開并启用。展開脚本作为重啟前启用的替代方案提供。
   190|   190|   190|
   225|   225|   225|## 授權條款
   226|   226|   226|
   227|   227|   227|MIT——詳見 [LICENSE](LICENSE)。