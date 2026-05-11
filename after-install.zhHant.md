[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 藍信 Adapter — 安裝後設定

已安裝兩個插件與一個技能：

1. **lansenger-platform**——閘道通道適配器（啟用 藍信 作為訊息通道）
2. **lansenger-tools**——Agent 工具，用於傳送訊息、檔案、圖片、撤回訊息、linkCard 卡片
3. **lansenger-messaging**——教導 Agent 如何選擇正確 藍信 工具的技能

## 設定

### 方式 A：一行命令設定（推薦）

將 `YOUR_APP_ID` 和 `YOUR_APP_SECRET` 替換為您的實際憑證，然後執行：

```bash
grep -q "^LANSENGER_APP_ID=" ~/.hermes/.env 2>/dev/null || echo "LANSENGER_APP_ID=YOUR_APP_ID" >> ~/.hermes/.env && \
grep -q "^LANSENGER_APP_SECRET=" ~/.hermes/.env 2>/dev/null || echo "LANSENGER_APP_SECRET=YOUR_APP_SECRET" >> ~/.hermes/.env
```

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

> 💡 App ID 與 App Secret 可在 藍信 → 通訊錄 → 個人機器人（非工作空間）中找到

## 技能安裝

安裝插件後，將技能複製至 Hermes 技能目錄：

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging
cp lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

注意：Hermes 要求每個技能為包含 `SKILL.md` 檔案的目錄，而非單獨的 `.md` 檔案。

此技能教導 Agent 藍信 訊息類型能力邊界（文字 vs formatText），並提供決策樹以選擇正確工具。若缺少此技能，Agent 可能選擇錯誤的訊息類型，導致失去 Markdown 格式或附件支援。

## 重啟閘道

設定完成後，重啟 Hermes 閘道：

```bash
hermes gateway restart
```

## 驗證

檢查插件是否已載入：
- `hermes tools list` 应在 Plugin toolsets 段顯示 `lansenger-tools`
- `hermes plugins list` 应顯示 `hermes-lansenger-adapter` 與 `lansenger-tools` 已啟用

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