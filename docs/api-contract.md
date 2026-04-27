# 智媒后端 API 契约（多场景版）

本文档描述当前后端的统一接口契约。所有场景共用同一组 API，通过 `scene_id` 区分业务场景。

## 1. 基本约定

- `scene_id` 可选，不传时由后端调度器回退到默认场景（当前为 `zhimei`）。
- 同一 `session_id` 在生命周期内绑定单一 `scene_id`。
- 如果请求携带 `scene_id` 且与已存在会话不一致，接口返回 400。

## 2. 健康检查

### `GET /api/health`

响应示例：

```json
{
  "status": "ok",
  "timestamp": "2026-04-25T20:55:00.000000",
  "scenes": ["zhimei"]
}
```

## 3. 创建会话

### `POST /api/session`

请求体（可选）：

```json
{
  "scene_id": "zhimei"
}
```

响应示例：

```json
{
  "session_id": "a1b2c3d4",
  "scene_id": "zhimei",
  "state": {},
  "message": "游戏会话已创建"
}
```

## 4. 查询状态

### `GET /api/state/<session_id>`

响应示例：

```json
{
  "scene_id": "zhimei",
  "state": {}
}
```

## 5. 非流式对话

### `POST /api/chat`

请求体：

```json
{
  "session_id": "a1b2c3d4",
  "scene_id": "zhimei",
  "message": "采访消防队长"
}
```

响应示例：

```json
{
  "session_id": "a1b2c3d4",
  "scene_id": "zhimei",
  "role": {
    "name": "消防队长老张",
    "color": "#F97316",
    "avatar": "🔥"
  },
  "reply": "......",
  "state": {},
  "state_changes": [],
  "random_event": null
}
```

## 6. 流式对话（SSE）

### `POST /api/chat/stream`

请求体：

```json
{
  "session_id": "a1b2c3d4",
  "scene_id": "zhimei",
  "message": "采访消防队长"
}
```

事件顺序：

1. `role`
2. `token`（多次）
3. `state`
4. `changes`（可选）
5. `random_event`（可选）
6. `done`

错误事件：`error`

## 7. 重置会话

### `POST /api/reset/<session_id>`

行为：

- 若会话存在，则保留原 `scene_id` 重建会话；
- 若会话不存在，则使用默认场景创建新会话。

响应示例：

```json
{
  "session_id": "new12345",
  "scene_id": "zhimei",
  "state": {},
  "message": "游戏已重置"
}
```

## 8. 常见错误

- `400 {"error": "消息不能为空"}`
- `400 {"error": "未知场景: xxx"}`
- `400 {"error": "scene_id 与现有会话不一致"}`
- `404 {"error": "会话不存在"}`
