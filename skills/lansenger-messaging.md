---
name: lansenger-messaging
version: 2.1.0
category: mlops
description: Lansenger (蓝信) 消息发送策略 — 理解 text/formatText 能力边界，正确选择工具
trigger: When you need to send any message, file, image, or notification via Lansenger (蓝信), or when you see a lansenger_* tool in the available tools list.
---

# Lansenger Messaging Strategy

蓝信 (Lansenger) 有两种消息类型，能力边界不同。选错类型会导致功能丢失（如附件发不出来、Markdown 渲染失败）。

## 消息类型能力矩阵

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  msgType     │  Markdown    │  @mention    │  Attachments │
├──────────────┼──────────────┼──────────────┼──────────────┤
│  text        │  ✗           │  ✓           │  ✓           │
│  formatText  │  ✓           │  ✗           │  ✗           │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

## 工具选择决策树

### 1. 只发纯文本（不需要格式）
→ 用 `lansenger_send_text`
- content 写纯文本
- 不填 file_path、at_user_ids
- 例：通知、简单回复

### 2. 发 Markdown 格式文本（代码、表格、列表等）
→ 用 `lansenger_send_markdown`
- content 写 Markdown 内容
- 注意：不支持 @人、不支持附件
- 例：代码输出、结构化报告、步骤说明

### 3. 发文本 + 附件（文件/图片/视频）
→ 用 `lansenger_send_text`
- content 写纯文本说明（caption）
- file_path 填附件路径
- media_type 自动检测，也可手动指定（1=视频, 2=图片, 3=文件）
- 例："这是本周的报告" + PDF 文件

### 4. 需要同时发 Markdown + 附件
→ **发两条消息：**
1. 先用 `lansenger_send_markdown` 发格式化文本
2. 再用 `lansenger_send_file` 发附件（caption 可简写文件名）
- 原因：formatText 不支持附件，一条消息做不到
- 例：发一段 Markdown 分析 + 配图

### 5. 只发纯附件（不需要文本说明）
→ 用 `lansenger_send_file`
- file_path 填路径
- caption 可留空或简写文件名
- 例：发一张截图、发一个数据文件

### 6. 发图片 URL（网上图片）
→ 用 `lansenger_send_image_url`
- image_url 填图片链接
- caption 可留空或简写描述
- 例：发一张网上的图表链接

### 7. 发链接卡片
→ 用 `lansenger_send_link_card`
- title + link 必填
- description, icon_link, from_name 可选
- 例：分享文章链接、推荐工具

### 8. 撤回消息
→ 用 `lansenger_revoke_message`
- message_ids 必填（之前发送返回的 message_id）
- chat_type 默认 bot
- staff/group 类型需要 sender_id

## 常见错误

| 错误做法 | 正确做法 |
|---------|---------|
| 用 `lansenger_send_text` 发 Markdown | 用 `lansenger_send_markdown` |
| 用 `lansenger_send_markdown` 带 file_path | 改用两条消息：markdown + send_file |
| 用 `lansenger_send_file` 但想要格式化 caption | caption 只支持纯文本；需要格式化就拆成两条 |
| 忘记填 chat_id | chat_id 是所有发送工具的必填参数 |

## 技巧

- 如果不确定对方是否能看 Markdown，优先用 `lansenger_send_text`（纯文本最安全）
- 发大段 Markdown 分析时，考虑拆成多条 formatText（蓝信长消息阅读体验差）
- 撤回时 sys_msg_content 可自定义撤回提示文字（默认"该消息已撤回"）
- 文件大小上限 2MB，超过需提醒用户