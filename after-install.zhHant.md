[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信 Adapter — 安裝後設定

一個 Bundle 插件和一個技能已安裝：

1. **hermes-lansenger-adapter** — Bundle 容器（自動展開為 `lansenger-platform` + `lansenger-tools`）
2. **lansenger-messaging** — 教 Agent 選擇正確藍信工具的技能

> ⚠️ **不要手動運行 `hermes plugins enable lansenger-platform` 或 `hermes plugins enable lansenger-tools`** — Bundle 在 gateway 重啟時會自動展開並啟用兩個子插件。手動 enable 會失敗，因為子插件此時還在 Bundle 內部。

> 💡 如果你需要在重啟 gateway *之前*啟用子插件，先運行展開腳本：
> ```bash
> python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py
> ```
> 然後就可以運行 `hermes plugins enable lansenger-platform` 和 `hermes plugins enable lansenger-tools`。

## 設定

### 方式 A：互動式設定向導（推薦）

執行內建的設定向導——它會逐步引導您完成每個憑證的設定：

```bash
hermes setup gateway
```

從平台清單中選擇 **Lansenger**，然後貼上您的 App ID、App Secret，並可選擇確認 API 閘道 URL。已設定的值會顯示出來（密鑰會被遮掩），可以覆蓋修改。

> 💡 App ID 與 App Secret 可在 藍信桌面端 → 通訊錄 → 智能機器人 → 個人機器人 → ℹ️ 圖標中找到（行動端不支援查看憑證）

### 方式 B：config.yaml

將以下內容加入 `~/.hermes/config.yaml` 的 `platforms.lansenger` 下：

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # 或您的自訂閘道 URL
```

### 方式 C：.env 檔案（手動）

編輯 `~/.hermes/.env`，加入以下內容：

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## 技能安裝

安裝插件後，安裝 lansenger-messaging 技能（教導 Agent 訊息類型能力邊界與工具決策樹）：

**方式 A：從本地克隆倉庫複製（最快速）：**

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging && cp ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

**方式 B：從 GitHub URL 安裝（不需本地克隆）：**

```bash
hermes skills install --force --category lansenger https://github.com/lansenger-pm/hermes-lansenger-adapter/raw/main/skills/lansenger-messaging.md
```

若缺少此技能，Agent 可能選擇錯誤的訊息類型，導致失去 Markdown 格式或附件支援。

## 重啟閘道

設定完成後，重啟 Hermes 閘道：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 应在 Plugin toolsets 段顯示 `lansenger-tools`
- `hermes plugins list` 应显示 `lansenger-platform` 和 `lansenger-tools` 已启用（Bundle 自动展开）

## 工具總览

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