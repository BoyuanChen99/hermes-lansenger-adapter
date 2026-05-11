# 💠 Lansenger Adapter — Post-Install Setup

Two plugins were installed:

1. **lansenger-platform** — Gateway channel adapter
2. **lansenger-media-tools** — Agent tools for sending files/images, revoking messages, sending linkCard cards

## Step 1: Configure Credentials

Add these to `~/.hermes/.env`:

```
LANSENGER_APP_ID=your-app-id
LANSENGER_APP_SECRET=your-app-secret
```

Get these from: 蓝信客户端 → 通讯录 → 个人机器人 → 创建机器人 → 详情页

## Step 2: Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LANSENGER_API_GATEWAY_URL` | API Gateway URL (default: https://open.e.lanxin.cn/open/apigw) | — |
| `LANSENGER_HOME_CHANNEL` | Default cron delivery chat ID | Auto-detected |
| `LANSENGER_ALLOWED_USERS` | Allowed user IDs (comma-separated) | — |

## Step 3: Enable & Restart

```bash
hermes plugins enable lansenger-platform
hermes plugins enable lansenger-media-tools
hermes gateway restart
```

## Available Agent Tools

After enabling `lansenger-media-tools`, the Agent can call:

- `lansenger_send_file` — send local files/images/videos
- `lansenger_send_image_url` — send images from URLs
- `lansenger_revoke_message` — 撤回已发送的消息
- `lansenger_send_link_card` — 发送链接卡片