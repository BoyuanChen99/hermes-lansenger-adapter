     1|     1|     1|[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)
     2|     2|     2|
     3|     3|     3|# Hermes 蓝信适配器
     4|     4|     4|
     5|     5|     5|> 💠 蓝信 网关适配器 + 媒体与消息工具插件，用于 Hermes Agent。
     6|     6|     6|
     7|     7|     7|通过 WebSocket 长连接实现实时消息接收，通过 HTTP API 实现消息发送，将 Hermes Agent 连接到 蓝信 —— 一个企业即时通讯平台。
     8|     8|     8|
     9|     9|     9|本仓库包含**两个插件**：
    10|    10|    10|
    11|    11|    11|| 插件 | 类型 | 功能 |
    12|    12|    12||--------|------|-------------|
    13|    13|    13|| `platforms/lansenger/` | 平台 | 网关通道适配器 — 接收与发送消息 |
    14|    14|    14|| `lansenger-tools/` | 独立（工具） | Agent 可调用工具：发送文件/图片、撤回消息、发送 linkCard |
    15|    15|    15|
    16|    16|    16|## 功能特性
    17|    17|    17|
    18|    18|    18|### 平台适配器
    19|    19|    19|- **实时消息** — 通过 WebSocket 长连接实现
    20|    20|    20|- **Markdown 支持** — 使用 `formatText` 消息类型
    21|    21|    21|- **i18nAppCard** — 交互式审批流程卡片
    22|    22|    22|- **主通道自动检测** — 首条私聊消息设置默认发送目标
    23|    23|    23|- **定时推送** — 通过 `standalone_sender_fn` 实现计划通知
    24|    24|    24|- **用户授权** — 通过环境变量设置允许的用户 / 允许所有用户
    25|    25|    25|- **零核心修改** — 纯插件模式，`git diff HEAD` 保持纯净
    26|    26|    26|
    27|    27|    27|### 媒体与消息工具插件
    28|    28|    28|- **lansenger_send_file** — 向指定用户或群组发送任意本地文件/图片/视频
    29|    29|    29|- **lansenger_send_image_url** — 从 URL 下载图片并发送给指定用户或群组
    30|    30|    30|- **lansenger_revoke_message** — 撤回已发送的 蓝信 消息 🗑️
    31|    31|    31|- **lansenger_send_link_card** — 发送 蓝信 linkCard 卡片消息 🔗
    32|    32|    32|- **自动媒体类型检测** — 根据文件扩展名自动分类图片/视频/文档
    33|    33|    33|- **凭据控制** — 未设置 LANSENGER_APP_ID/SECRET 时工具自动隐藏
    34|    34|    34|
    35|    35|    35|## 快速安装
    36|    36|    36|
    37|    37|    37|### 通过 Hermes 插件管理器安装（推荐）
    38|    38|    38|
    39|    39|    39|```bash
    40|    40|    40|hermes plugins install lansenger-pm/hermes-lansenger-adapter
    41|    41|    41|hermes plugins enable hermes-lansenger-adapter
    42|    42|    42|hermes gateway restart
    43|    43|    43|```
    44|    44|    44|
    45|    45|    45|### 手动安装
    46|    46|    46|
    47|    47|    47|将本仓库克隆到 `~/.hermes/plugins/`：
    48|    48|    48|
    49|    49|    49|```bash
    50|    50|    50|cd ~/.hermes/plugins/
    51|    51|    51|git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
    52|    52|    52|hermes plugins enable hermes-lansenger-adapter
    53|    53|    53|hermes gateway restart
    54|    54|    54|```
    55|    55|    55|
    56|    56|    56|### 通过 pip 安装（高级）
    57|    57|    57|
    58|    58|    58|```bash
    59|    59|    59|pip install hermes-lansenger-adapter
    60|    60|    60|hermes plugins enable hermes-lansenger-adapter
    61|    61|    61|hermes gateway restart
    62|    62|    62|```
    63|    63|    63|
    64|    64|    64|## 配置
    65|    65|    65|
    66|    66|    66|### 必需环境变量
    67|    67|    67|
    68|    68|    68|将以下内容添加到 `~/.hermes/.env`：
    69|    69|    69|
    70|    70|    70|| 变量 | 说明 | 示例 |
    71|    71|    71||----------|-------------|---------|
    72|    72|    72|| `LANSENGER_APP_ID` | 机器人应用 ID | `your-app-id` |
    73|    73|    73|| `LANSENGER_APP_SECRET` | 机器人应用密钥 | `your-app-secret` |
    74|    74|    74|
    75|    75|    75|**凭据路径：** 蓝信桌面端 → 通讯录 → 智能机器人 → 个人机器人 → 点击右侧 ℹ️ 图标查看凭证（移动端不支持查看凭证）
    76|    76|    76|
    77|    77|    77|### 可选环境变量
    78|    78|    78|
    79|    79|    79|| 变量 | 说明 | 默认值 |
    80|    80|    80||----------|-------------|---------|
    81|    81|    81|| `LANSENGER_API_GATEWAY_URL` | API 网关 URL | `https://open.e.lanxin.cn/open/apigw` |
    82|    82|    82|| `LANSENGER_ALLOWED_USERS` | 允许的用户 ID（逗号分隔） | — |
    83|    83|    83|| `LANSENGER_ALLOW_ALL_USERS` | 允许所有用户（仅开发环境） | `false` |
    84|    84|    84|| `LANSENGER_HOME_CHANNEL` | 默认定时推送的聊天 ID | 自动检测 |
    85|    85|    85|
    86|    86|    86|### config.yaml
    87|    87|    87|
    88|    88|    88|```yaml
    89|    89|    89|platforms:
    90|    90|    90|  lansenger:
    91|    91|    91|    enabled: true
    92|    92|    92|```
    93|    93|    93|
    94|    94|    94|## 媒体与消息工具（来自 lansenger-tools）
    95|    95|    95|
    96|    96|    96|这些工具允许 Agent 发送文件、图片和视频，撤回消息，以及发送 linkCard 卡片 —— 均可由 LLM 独立调用。凭据从环境变量（LANSENGER_APP_ID/SECRET）读取，而非从 `load_gateway_config()` 读取。
    97|    97|    97|
    98|    98|    98|| 工具 | 参数 | 说明 |
    99|    99|    99||------|-----------|-------------|
   100|   100|   100|| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | 发送纯文本，支持可选 @提及（仅群聊/员工群）和附件 |
   101|   101|   101|| `lansenger_send_markdown` | `chat_id`, `message` | 发送 Markdown 格式文本（不支持 @提及和附件） |
   102|   102|   102|| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | 向用户或群组发送本地文件/图片/视频 |
   103|   103|   103|| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | 从 URL 下载图片并以原生图片形式发送 |
   104|   104|   104|| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | 撤回已发送的 蓝信 消息（系统提示为固定内容，不可自定义） |
   105|   105|   105|| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | 发送 蓝信 linkCard 卡片消息 |
   106|   106|   106|
   107|   107|   107|**使用示例（Agent 提示）：**
   108|   108|   108|
   109|   109|   109|```
   110|   110|   110|"将 report.pdf 发送给用户 2285568-abc123"
   111|   111|   111|"将该图表图片分享到项目群聊"
   112|   112|   112|"下载此 URL 图片并发送给我的同事"
   113|   113|   113|"撤回我刚才发送给该用户的消息"
   114|   114|   114|"向用户发送标题为 '项目文档' 且链接为 https://... 的 linkCard 卡片"
   115|   115|   115|```
   116|   116|   116|
   117|   117|   117|**限制：**
   118|   118|   118|- 文件大小限制由组织的 蓝信 配置决定（无固定上限）
   119|   119|   119|- 媒体说明使用纯文本（不支持 Markdown） —— 如需 Markdown 格式文本，请单独发送
   120|   120|   120|- `lansenger_send_file` 在未指定 media_type 时会根据扩展名自动检测
   121|   121|   121|- `lansenger_revoke_message`：对于员工/群聊类型，需要提供 `sender_id`
   122|   122|   122|
   123|   123|   123|## 架构
   124|   124|   124|
   125|   125|   125|```
   126|   126|   126|hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
   127|   127|   127|                          ├── plugin.yaml                     # 根清单 (kind: bundle)
   128|   128|   128|                          ├── platforms/lansenger/            # 网关适配器
   129|   129|   129|                          │   ├── plugin.yaml                 # 清单 (kind: platform)
   130|   130|   130|                          │   ├── __init__.py                  # register() → ctx.register_platform()
   131|   131|   131|                          │   └── adapter.py                   # 完整适配器（此处无工具处理器）
   132|   132|   132|                          ├── lansenger-tools/           # 媒体与消息工具
   133|   133|   133|                          │   ├── plugin.yaml                 # 清单 (kind: standalone)
   134|   134|   134|                          │   ├── __init__.py                  # register() → ctx.register_tool()
   135|   135|   135|                          │   ├── schemas.py                   # LLM 工具描述
   136|   136|   136|                          │   └── tools.py                     # 处理器实现
   137|   137|   137|                          ├── skills/                          # Agent 决策技能
   138|   138|   138|                          │   └── lansenger-messaging.md       # 工具选择策略 + token 文档
   139|   139|   139|                          ├── README.md
   140|   140|   140|                          ├── LICENSE
   141|   141|   141|                          ├── VERSION
   142|   142|   142|                          ├── after-install.md
   143|   143|   143|                          ├── pyproject.toml                   # pip 入口点
   144|   144|   144|                          └── .gitignore
   145|   145|   145|```
   146|   146|   146|
   147|   147|   147|## 依赖
   148|   148|   148|
   149|   149|   149|- `websockets` — WebSocket 长连接客户端
   150|   150|   150|- `httpx` — HTTP 客户端，用于 API 调用（媒体工具也使用）
   151|   151|   151|
   152|   152|   152|## 升级
   153|   153|   153|
   154|   154|   154|升级到最新版本：
   155|   155|   155|
   156|   156|   156|```bash
   157|   157|   157|hermes plugins update hermes-lansenger-adapter
   158|   158|   158|hermes gateway restart
   159|   159|   159|```
   160|   160|   160|
   161|   161|   161|## 更新日志
   162|   162|   162|
   163|   163|   163|### v2.6.0 — 审批流程升级：i18nAppCard → 动态 appCard
   164|   164|   164|
   165|   165|   165|- **动态 appCard (isDynamic=True)**：审批、斜杠确认、更新提示卡片改用 appCard，支持原地状态更新（待审批 → 已批准/已拒绝），不再发送重复卡片。
   166|   166|   166|- **语言检测缓存**：`_user_lang_map` 从 inbound 消息中用 CJK 启发式检测并缓存用户语言偏好（zh/en），卡片内容自动选择中/英文。默认中文。
   167|   167|   167|- **状态更新改用 appCardUpdateMsg**：`update_approval_status` 用 `msgType="appCard"` + `appCardUpdateMsg`（原为 i18nAppCardUpdateMsg），同一张卡片视觉状态原地变更。
   168|   168|   168|- **新增辅助方法**：`_detect_lang()`、`_get_lang()`、`_get_agent_signature(lang)`、`_build_status_div(text, color)`。
   169|   169|   169|- **保留 `_build_i18n_obj_full` 和 `_build_agent_signature_i18n`** 但审批流程不再使用——为未来可能的 i18n 需求保留。
   170|   170|   170|
   171|   171|   171|
   172|   172|   172|### v2.5.0 — appArticles、appCard、动态卡片更新、群消息路由、群ID查询
   173|   173|   173|
   174|   174|   174|### v2.4.2 — Home channel 自动升级
   175|   175|   175|
   176|   176|   176|- **Home channel 自动升级**: 首次私聊对话自动设为蓝信 home channel。如果未配置 home_channel，或现有 home 是群聊，首次私聊会覆盖它（私聊 > 群聊升级）。静默写入 config.yaml 和 os.environ，无用户提示。遵循元宝的 AutoSetHomeMiddleware 模式。
   177|   177|   177|
   178|   178|   178|- **动态 Agent 签名**（v2.4.1 起）：所有三个 i18nAppCard 方法均使用 `_build_agent_signature_i18n()`。
   179|   179|   179|
   180|   180|   180|### v2.4.1 — send_update_prompt + 动态 Agent 签名
   181|   181|   181|
   182|   182|   182|- **send_update_prompt**: 新增 i18nAppCard 方法，用于 gateway `/update` watcher。卡片展示提示文本和 /approve、/deny 回复提示（i18nFields）。gateway 的文本拦截将 /approve → "y"、/deny → "n" 路由到 `update_prompt.resolve()`。蓝信没有 inline button 回调（如 Telegram/Discord），只能使用文字回复。
   183|   183|   183|
   184|   184|   184|- **动态 Agent 签名**: 所有 i18nAppCard 卡片（send_update_prompt、send_exec_approval、send_slash_confirm）现在使用 `_build_agent_signature_i18n()`，从 `~/.hermes/SOUL.md` 动态读取 Agent 名称。SOUL.md 不可读时回退到 "Hermes"。不再硬编码"Hermes 安全审批系统"——签名现在反映实际的 Agent 人设。
   185|   185|   185|
   186|   186|   186|### v2.4.0 — Bundle 安装时展开 + 展开脚本
   187|   187|   187|
   188|   188|   188|- **模块级展开**: 子插件（`lansenger-platform`、`lansenger-tools`）现在在 **import 时**就被复制到 `~/.hermes/plugins/` 顶层，而不是仅在 `register()` 中。这意味着它们在 gateway 重启之前就能被 `hermes plugins enable` 发现（但仍需重启才能加载）。
   189|   189|   189|
   190|   190|   190|- **expand_sub_plugins.py**: 用于重启前展开的独立脚本。安装后运行 `python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py`，即可在首次 gateway 重启前使子插件可被 `hermes plugins enable` 发现。
   191|   191|   191|
   192|   192|   192|- **安装后文档**: 5 个语言版本明确警告：*不要手动 `hermes plugins enable` 子插件* — Bundle 在重启时自动展开并启用。展开脚本作为重启前启用的替代方案提供。
   193|   193|   193|
   228|   228|   228|## 许可证
   229|   229|   229|
   230|   230|   230|MIT — 详情见 [LICENSE](LICENSE)。