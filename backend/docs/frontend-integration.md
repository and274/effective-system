# 前后端对接清单

## 1. 字段命名规范

前端发请求和收响应用 camelCase，对照：

| 文档字段 | 前端实际用 | 用途 |
|----------|-----------|------|
| externalUser | externalUser | ✅ 一致 |
| playerId | playerId | ✅ 一致 |
| sessionId | sessionId | ✅ 一致 |
| sceneId | sceneId | ✅ 一致 |
| scene_id | scene_id | ✅ 一致（创建会话请求） |
| message | message | ✅ 一致 |

---

## 2. 三个接口的具体要求

### POST /api/session（创建会话）

**请求：**
```json
{ "externalUser": "前端用户ID", "scene_id": "zhimei" }
```

**期望响应：**
```json
{
  "sessionId": "sess_xxx",
  "playerId": "player_00001",
  "externalUser": "前端用户ID",
  "sceneId": "zhimei",
  "state": { ... },
  "message": "..."
}
```

> ⚠️ 注意：前端把 sessionId / playerId / sceneId 全都存在 `localStorage["app_session"]`，后续所有请求必须带 playerId，否则 403。

---

### POST /api/chat/stream（流式对话，SSE）

**请求：**
```json
{
  "sessionId": "sess_xxx",
  "playerId": "player_00001",
  "externalUser": "前端用户ID",
  "message": "用户消息"
}
```

**前端解析 SSE 事件类型：**

| 事件类型 | data 格式 | 说明 |
|----------|-----------|------|
| `role` | `{ ...角色信息 }` | 角色信息 |
| `token` | `{ "content": "逐字内容" }` | 逐字输出，前端从 `.content` 取文本 |
| `state` | `{ ...state对象 }` | 状态更新 |
| `changes` | `{ "changes": ["变化1", "变化2"] }` | 状态变化 |
| `random_event` | `{ "title": "事件名" }` | 随机事件 |
| `done` | `{ "playerId": "...", "externalUser": "..." }` | 结束 |

> ⚠️ token 事件的 data 格式必须是 `{ "content": "xxx" }`，前端直接从 `data.content` 取文本。

---

### POST /api/history（保存历史记录）

**请求：**
```json
{
  "session_id": "sess_xxx",
  "scene_id": "zhimei",
  "summary": "场景名",
  "username": "用户名",
  "score": 85,
  "state_snapshot": { ... }
}
```

> ⚠️ 这个接口用 `session_id`（下划线），与 chat 的 `sessionId`（驼峰）不一致。接口独立，历史记录前端也有 localStorage 兜底。

---

## 3. 错误码处理

前端对所有非 2xx 响应统一用 Toast 显示 `data.error.message`，不区分具体错误码。

| 情况 | 后端行为 |
|------|---------|
| 403 PLAYER_MISMATCH | `data.error.message` 显示给用户 |
| 404 PLAYER_NOT_FOUND | 同上 |
| 400 EMPTY_MESSAGE | 前端已做非空校验，不应触发 |
| 后端挂了/超时 | 显示 "❌ 无法连接后端" |

---

## 4. state 对象字段（前端面板展示）

前端 `applyStateToPanel(state)` 读取这些字段：

| state 字段 | 面板展示 |
|-----------|---------|
| `dashboard_metrics.public_sentiment` | 舆论热度 |
| `dashboard_metrics.report_impact` | 报道影响 |
| `dashboard_metrics.public_trust` | 公众信心 |
| `dashboard_metrics.spread_index` | 传播指数 |
| `dashboard_metrics.watchers` | 在线观看 |
| `dashboard_metrics.comments` | 评论数 |
| `dashboard_metrics.shares` | 转发数 |
| `dashboard_metrics.alert_level` | 警报级别 |
| `credibility` | 可信度 |
| `info_completion_rate` | 信息完成率 |
| `rumors_active.length` | 谣言数量 |
| `reports_published` | 报道数 |

> ⚠️ 如果后端 state 结构不同，前端面板显示为 0 或 null，不会报错。

---

## 5. 已完成的前端工作

- ✅ 前端生成 externalUser（用 user.id，注册后固定不变）
- ✅ 首次创建会话后存 playerId 到 localStorage
- ✅ 后续每次请求自动带 playerId + externalUser
- ✅ SSE 流式解析完成
- ✅ 登录状态校验（未登录跳转 login.html）

---

## 6. 后端确认事项

1. ✅ `POST /api/session` 响应里 `externalUser` 原样返回（前端用它确认值对不对）
2. ✅ token 事件 data 用 `{ content: string }` 格式
3. ✅ 前端文件在 `E:\Front-end\`，对照 `main.html` 里的 `sendDecision()` 和 `createBackendSession()` 函数

---

## 状态：可以对接 ✅
