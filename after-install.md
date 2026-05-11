# 💠 Lansenger Adapter — Post-Install Setup

Your Lansenger (蓝信) adapter plugin is now installed!

## Next Steps

1. **Add credentials** to `~/.hermes/.env`:
   ```
   LANSENGER_APP_ID=your-app-id
   LANSENGER_APP_SECRET=your-app-secret
   ```
   Get these from: 蓝信客户端 → 通讯录 → 个人机器人 → 创建机器人 → 详情页

2. **Enable the plugin** (if not already):
   ```bash
   hermes plugins enable lansenger-platform
   ```

3. **Restart the gateway**:
   ```bash
   hermes gateway restart
   ```

4. **Verify** — send a test message to your bot in Lansenger!

## Available Tools

- `lansenger_revoke_message` 🗑️ — 撤回已发送的蓝信消息
- `lansenger_send_link_card` 🔗 — 发送蓝信 linkCard 卡片消息

## Optional Config

| Env Var | Description |
|---------|-------------|
| `LANSENGER_API_GATEWAY_URL` | API Gateway URL (default: https://open.e.lanxin.cn/open/apigw) |
| `LANSENGER_ALLOWED_USERS` | Comma-separated user IDs allowed to talk to bot |
| `LANSENGER_ALLOW_ALL_USERS` | Allow any user (dev only, set to "true") |
| `LANSENGER_HOME_CHANNEL` | Default cron delivery chat ID (auto-detected) |