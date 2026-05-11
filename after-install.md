# 💠 Lansenger Adapter — Post-Install Setup

Two plugins were installed:

1. **lansenger-platform** — Gateway channel adapter
2. **lansenger-media-tools** — Agent tools for sending files/images/videos

## Next Steps

1. **Add credentials** to `~/.hermes/.env`:
   ```
   LANSENGER_APP_ID=your-app-id
   LANSENGER_APP_SECRET=your-app-secret
   ```

   Get these from: 蓝信客户端 → 通讯录 → 个人机器人 → 创建机器人 → 详情页

2. **Optional: set API Gateway** (if using Qianxin internal network):
   ```
   LANSENGER_API_GATEWAY_URL=https://apigw.lx.qianxin.com
   ```

   | Environment | Gateway URL |
   |-------------|-------------|
   | Default (public) | `https://open.e.lanxin.cn/open/apigw` |
   | Qianxin internal | `https://apigw.lx.qianxin.com` |

3. **Enable both plugins**:
   ```bash
   hermes plugins enable lansenger-platform
   hermes plugins enable lansenger-media-tools
   ```

4. **Restart gateway**:
   ```bash
   hermes gateway restart
   ```

## Available Tools

| Tool | Plugin | Description |
|------|--------|-------------|
| `lansenger_revoke_message` | platform | 撤回已发送的蓝信消息 🗑️ |
| `lansenger_send_link_card` | platform | 发送蓝信 linkCard 卡片消息 🔗 |
| `lansenger_send_file` | media-tools | Send local file/image/video to a user or group |
| `lansenger_send_image_url` | media-tools | Send image from URL to a user or group |