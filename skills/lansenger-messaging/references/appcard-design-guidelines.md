# appCard Design Guidelines

## div-style Field-by-Field Support (per API Spec)

Not all appCard fields support the same div-style properties. Per Lansenger API spec:

| Field | color | font-size | text-align | text-indent |
|-------|-------|-----------|------------|-------------|
| bodyTitle | ✓ | ✓ (pt only) | ✓ | ✗ |
| bodySubTitle | ✓ | ✓ (pt only) | ✓ | ✗ |
| bodyContent | ✓ | ✓ (pt only) | ✓ | ✓ (0em only) |
| signature | ✓ | ✗ | ✗ | ✗ |
| fields key/value | ✓ | ✗ | ✗ | ✗ |
| links.title | ✓ | ✗ | ✓ | ✗ |
| headStatusInfo.description | ✓ | ✗ | ✗ | ✗ |

**font-size**: Enterprise Lansenger API rejects `px` unit. Only bodyTitle, bodySubTitle, bodyContent support font-size. lansenger-tools auto-converts `px→pt` (1px ≈ 0.75pt) in these three fields. Use `pt` directly for predictable results.

**text-indent**: Only bodyContent supports text-indent. Must include unit — `text-indent:0em` works; bare `text-indent:0` causes API empty response. lansenger-tools auto-converts bare `0` → `0em` in bodyContent.

## headStatusInfo

headStatusInfo = status dot + text. Two independent parts:

- **description** = the text label. Supports single `<div style="color:...">` for coloring the text. Must be <30 bytes. No nested divs — API rejects nested div structure.
  - Examples: `<div style="color:#FFB116">待审批</div>`, `<div style="color:#198754">已批准</div>`, `Active`
- **colour** = the status dot color. Independent from description text color.
  - Examples: "#FFB116" (amber/pending), "#198754" (green/approved), "red" (rejected)
- **iconLink** = optional icon URL for the status indicator

## Approval Card Template

Dynamic approval cards use isDynamic=True + headStatusInfo:

**Chinese template:**
```
headTitle: "⚠️ 命令审批"
bodyTitle: <div style="color:#000;font-size:15pt;text-align:left">命令审批请求</div>
bodyContent: <div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{content}</div>
headStatusInfo: {description: "待审批", colour: "#FFB116"}
fields: [{key: "批准", value: "/approve"}, {key: "拒绝", value: "/deny"}]
```

**English template:**
```
headTitle: "⚠️ Command Approval"
bodyTitle: <div style="color:#000;font-size:15pt;text-align:left">Command Approval Request</div>
bodyContent: <div style="color:#000;font-size:13pt;text-align:left;text-indent:0em">{content}</div>
headStatusInfo: {description: "Pending", colour: "#FFB116"}
```

## Dynamic Card Status Update

After approval/rejection, update via `lansenger_update_dynamic_card`:
- is_last_update=True → final state, card becomes static
- Approved: headStatusInfo={description: "已批准"/"Approved", colour: "#198754"}
- Rejected: headStatusInfo={description: "已拒绝"/"Rejected", colour: "red"}

## appCard vs i18nAppCard

| | appCard | i18nAppCard |
|---|---|---|
| Languages | 1 (auto-detected) | 5 (zhHans/zhHant/zhHantHK/en/fr) |
| Dynamic updates | ✓ (isDynamic + headStatusInfo) | ✗ |
| Status | Production-ready | Reserved, not implemented |

## Group Chat Limitation

⚠️ Group chat may degrade appCard to plain text depending on API support. For group approval workflows, use `lansenger_send_text` with /approve /deny text pattern instead.