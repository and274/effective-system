import json
import logging
import time

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from config import Config
from scenes.registry import scene_registry
from services.history_store import history_store
from services.orchestrator import orchestrator
from services.session_store import session_store
from services.player_store import player_store
from utils.helpers import now_iso

# 启动前校验配置
Config.validate()

app = Flask(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 限制请求体 2MB

CORS(app, origins=Config.CORS_ORIGINS)
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("zhimei-backend")


def error_response(code: str, message: str, status: int, details: dict | None = None):
    payload = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


def build_dashboard_metrics(state_dict: dict) -> dict:
    credibility = int(state_dict.get("credibility", 0))
    info_rate = int(round(float(state_dict.get("info_completion_rate", 0))))
    reports = int(state_dict.get("reports_published", 0))
    rumors = len(state_dict.get("rumors_active", []) or [])
    total_time = int(state_dict.get("total_time_elapsed", 0))
    game_over = bool(state_dict.get("game_over", False))

    # 持续效果信息
    active_effects = state_dict.get("active_effects", [])
    effects_summary = state_dict.get("active_effects_summary", {})
    cred_drain = effects_summary.get("credibility_drain_per_turn", 0) if isinstance(effects_summary, dict) else 0

    public_sentiment = max(0, min(100, credibility))
    report_impact = max(0, min(100, info_rate))
    public_trust = max(0, min(100, int(credibility - rumors * 10 + reports * 5)))
    spread_index = max(0, min(100, int(reports * 20 + rumors * 8 + total_time * 0.5)))

    watchers = max(0, int(total_time * 18 + reports * 120 - rumors * 25))
    comments = max(0, int(rumors * 12 + total_time * 3))
    shares = max(0, int(reports * 35 + info_rate * 1.2))
    if game_over:
        alert_level = "结束"
    elif credibility < 40 or rumors >= 4:
        alert_level = "高"
    elif credibility < 60 or rumors >= 2:
        alert_level = "中"
    else:
        alert_level = "低"

    return {
        "public_sentiment": public_sentiment,
        "report_impact": report_impact,
        "public_trust": public_trust,
        "spread_index": spread_index,
        "watchers": watchers,
        "comments": comments,
        "shares": shares,
        "alert_level": alert_level,
        "credibility_drain_per_turn": cred_drain,
        "active_effects_count": len(active_effects) if isinstance(active_effects, list) else 0,
    }


def with_dashboard_metrics(state_dict: dict) -> dict:
    enriched = dict(state_dict)
    enriched["dashboard_metrics"] = build_dashboard_metrics(state_dict)
    return enriched


def resolve_player(data: dict) -> tuple[str, dict, bool]:
    """
    解析请求中的玩家身份，返回 (external_user, player, player_id_provided)

    规则：
    - 如果请求同时有 playerId + externalUser → 验证一致性后返回
    - 如果只有 externalUser → 查找或注册玩家（兼容旧逻辑）
    - 如果什么都没有 → 生成游客账号
    - 前端不传 playerId 时用 player_id_provided=False 标记，后端不验证一致性
    """
    player_id_raw = (data.get("playerId") or data.get("player_id") or "").strip()
    external_user_raw = (data.get("external_user") or data.get("externalUser") or "").strip()

    if player_id_raw and external_user_raw:
        # 完整模式：校验 playerId ↔ externalUser 一致性
        player = player_store.get(player_id_raw)
        if not player:
            return None, None, True  # player_not_found
        if player["external_user"] != external_user_raw:
            return None, None, True  # mismatch (caller 处理)
        return external_user_raw, player, True

    if external_user_raw:
        # 兼容模式：有 externalUser 但没有 playerId
        player = player_store.resolve(external_user_raw)
        return player["external_user"], player, False

    # 游客模式
    player = player_store.generate_guest()
    return player["external_user"], player, False


def encode_session_record(record: dict) -> dict:
    scene_id = record["scene_id"]
    scene = scene_registry.get(scene_id)
    return {
        "scene_id": scene_id,
        "external_user": record["external_user"],
        "player_id": record.get("player_id", ""),
        "state": scene.serialize_state(record["state"]),
    }


def decode_session_record(payload: dict) -> dict:
    scene_id = payload["scene_id"]
    scene = scene_registry.get(scene_id)
    return {
        "scene_id": scene_id,
        "external_user": payload.get("external_user", Config.EXTERNAL_USER_DEFAULT),
        "player_id": payload.get("player_id", ""),
        "state": scene.deserialize_state(payload["state"]),
    }


def create_session_record(scene_id: str, external_user: str, player_id: str) -> dict:
    scene = scene_registry.get(scene_id)
    state = scene.create_state()
    record = {"scene_id": scene_id, "external_user": external_user, "player_id": player_id, "state": state}
    session_store.set(state.session_id, encode_session_record(record))
    return record


def get_or_create_session(session_id: str, scene_id: str, external_user: str, player_id: str) -> dict:
    if session_id:
        existing_payload = session_store.get(session_id)
        if existing_payload:
            return decode_session_record(existing_payload)
    return create_session_record(scene_id, external_user, player_id)


def save_session_record(record: dict) -> None:
    session_store.set(record["state"].session_id, encode_session_record(record))


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": now_iso(), "scenes": scene_registry.list_scene_ids()})


@app.route("/api/session", methods=["POST"])
def create_session():
    data = request.get_json(silent=True) or {}
    external_user, player, pid_provided = resolve_player(data)
    if external_user is None:
        if pid_provided:
            return error_response("PLAYER_NOT_FOUND", "playerId 不存在", 404, {"player_id": data.get("playerId") or data.get("player_id", "")})
        return error_response("PLAYER_MISMATCH", "playerId 与 externalUser 不匹配", 403)

    requested_scene_id = (data.get("scene_id") or "").strip()
    route = orchestrator.route(
        "",
        requested_scene_id=requested_scene_id or None,
        external_user=external_user,
        available_scenes=scene_registry.list_scene_ids(),
    )
    scene_id = route["scene_id"]
    try:
        record = create_session_record(scene_id, external_user, player["player_id"])
    except KeyError:
        return error_response("UNKNOWN_SCENE", f"未知场景: {scene_id}", 400, {"scene_id": scene_id})
    state = record["state"]
    state_payload = with_dashboard_metrics(state.to_dict())
    return jsonify(
        {
            "sessionId": state.session_id,
            "sceneId": scene_id,
            "externalUser": record["external_user"],
            "playerId": player["player_id"],
            "state": state_payload,
            "message": "游戏会话已创建",
        }
    )


@app.route("/api/state/<session_id>", methods=["GET"])
def get_state(session_id: str):
    payload = session_store.get(session_id)
    if not payload:
        return error_response("SESSION_NOT_FOUND", "会话不存在", 404, {"session_id": session_id})
    record = decode_session_record(payload)
    state_payload = with_dashboard_metrics(record["state"].to_dict())
    return jsonify(
        {
            "sessionId": record["state"].session_id,
            "sceneId": record["scene_id"],
            "externalUser": record["external_user"],
            "playerId": record.get("player_id", ""),
            "state": state_payload,
        }
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    started = time.perf_counter()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or data.get("sessionId", "")
    external_user, player, pid_provided = resolve_player(data)
    if external_user is None:
        if pid_provided:
            pid = data.get("playerId") or data.get("player_id", "")
            eu = data.get("externalUser") or data.get("external_user", "")
            # playerId 不存在 或 playerId↔externalUser 不匹配
            existing = player_store.get(pid) if pid else None
            if existing and existing["external_user"] != eu:
                return error_response("PLAYER_MISMATCH", "playerId 与 externalUser 不匹配", 403,
                                      {"playerId": pid, "externalUser": eu,
                                       "expected_externalUser": existing["external_user"]})
            return error_response("PLAYER_NOT_FOUND", "playerId 不存在", 404, {"playerId": pid})
        return error_response("PLAYER_MISMATCH", "playerId 与 externalUser 不匹配", 403)
    user_message = data.get("message", "").strip()
    requested_scene_id = (data.get("scene_id") or data.get("sceneId") or "").strip()
    if not user_message:
        return error_response("EMPTY_MESSAGE", "消息不能为空", 400)

    route = orchestrator.route(
        user_message,
        requested_scene_id=requested_scene_id or None,
        external_user=external_user,
        available_scenes=scene_registry.list_scene_ids(),
    )
    scene_id = route["scene_id"]
    try:
        record = get_or_create_session(session_id, scene_id, external_user, player["player_id"])
        scene = scene_registry.get(record["scene_id"])
    except KeyError:
        return error_response("UNKNOWN_SCENE", f"未知场景: {scene_id}", 400, {"scene_id": scene_id})

    # 验证 playerId 与 session 中的 player_id 一致
    if pid_provided and record.get("player_id") and record["player_id"] != player["player_id"]:
        return error_response("PLAYER_MISMATCH", "playerId 与会话中的 playerId 不一致", 403,
                              {"request_playerId": player["player_id"], "session_playerId": record["player_id"]})

    if requested_scene_id and record["scene_id"] != requested_scene_id:
        return error_response(
            "SCENE_MISMATCH",
            "scene_id 与现有会话不一致",
            400,
            {"requested_scene_id": requested_scene_id, "session_scene_id": record["scene_id"]},
        )

    state = record["state"]
    try:
        turn = scene.run_turn(user_message, state)
    except Exception as err:
        logger.exception("chat turn failed", extra={"scene_id": record["scene_id"], "session_id": state.session_id})
        return error_response("CHAT_FAILED", "对话处理失败", 500, {"reason": str(err)})

    save_session_record(record)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("chat ok scene=%s session=%s elapsed_ms=%s", record["scene_id"], state.session_id, elapsed_ms)

    return jsonify(
        {
            "sessionId": state.session_id,
            "sceneId": record["scene_id"],
            "externalUser": record["external_user"],
            "playerId": player["player_id"],
            "role": turn["role"],
            "reply": turn["reply"],
            "state": with_dashboard_metrics(turn["state"]),
            "state_changes": turn["state_changes"],
            "random_event": turn["random_event"],
            "npc_events": turn.get("npc_events", []),
            "resolution_results": turn.get("resolution_results", []),
        }
    )


@app.route("/api/realtime/<session_id>", methods=["GET"])
def realtime(session_id: str):
    """实时数据接口：供前端舆情监控面板轮询"""
    payload = session_store.get(session_id)
    if not payload:
        return error_response("SESSION_NOT_FOUND", "会话不存在", 404, {"session_id": session_id})
    record = decode_session_record(payload)
    state = record["state"]
    state_dict = state.to_dict()

    return jsonify({
        "sessionId": session_id,
        "state": with_dashboard_metrics(state_dict),
        "comments": state_dict.get("netizen_comments", []),
        "active_effects": state_dict.get("active_effects", []),
        "active_effects_summary": state_dict.get("active_effects_summary", {}),
        "npc_actions_log": state_dict.get("npc_actions_log", []),
        "game_over": state.game_over,
    })


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    def generate():
        started = time.perf_counter()
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id") or data.get("sessionId", "")
        external_user, player, pid_provided = resolve_player(data)
        if external_user is None:
            if pid_provided:
                pid = data.get("playerId") or data.get("player_id", "")
                eu = data.get("externalUser") or data.get("external_user", "")
                existing = player_store.get(pid) if pid else None
                if existing and existing["external_user"] != eu:
                    yield f"event: error\ndata: {json.dumps({'code': 'PLAYER_MISMATCH', 'message': 'playerId 与 externalUser 不匹配'}, ensure_ascii=False)}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'code': 'PLAYER_NOT_FOUND', 'message': 'playerId 不存在'}, ensure_ascii=False)}\n\n"
            else:
                yield f"event: error\ndata: {json.dumps({'code': 'PLAYER_MISMATCH', 'message': 'playerId 与 externalUser 不匹配'}, ensure_ascii=False)}\n\n"
            return
        user_message = data.get("message", "").strip()
        requested_scene_id = (data.get("scene_id") or data.get("sceneId") or "").strip()
        if not user_message:
            yield f"event: error\ndata: {json.dumps({'code': 'EMPTY_MESSAGE', 'message': '消息不能为空'}, ensure_ascii=False)}\n\n"
            return

        route = orchestrator.route(
            user_message,
            requested_scene_id=requested_scene_id or None,
            external_user=external_user,
            available_scenes=scene_registry.list_scene_ids(),
        )
        scene_id = route["scene_id"]
        try:
            record = get_or_create_session(session_id, scene_id, external_user, player["player_id"])
            scene = scene_registry.get(record["scene_id"])
        except KeyError:
            yield f"event: error\ndata: {json.dumps({'code': 'UNKNOWN_SCENE', 'message': f'未知场景: {scene_id}'}, ensure_ascii=False)}\n\n"
            return

        if pid_provided and record.get("player_id") and record["player_id"] != player["player_id"]:
            yield f"event: error\ndata: {json.dumps({'code': 'PLAYER_MISMATCH', 'message': 'playerId 与会话中的 playerId 不一致'}, ensure_ascii=False)}\n\n"
            return
        if requested_scene_id and record["scene_id"] != requested_scene_id:
            yield f"event: error\ndata: {json.dumps({'code': 'SCENE_MISMATCH', 'message': 'scene_id 与现有会话不一致'}, ensure_ascii=False)}\n\n"
            return

        state = record["state"]
        meta, token_stream = scene.stream_turn(user_message, state)
        role_info = meta["role"]
        yield f"event: role\ndata: {json.dumps(role_info, ensure_ascii=False)}\n\n"

        full_reply = ""
        try:
            for token in token_stream:
                full_reply += token
                yield f"event: token\ndata: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
        except Exception as err:
            logger.exception(
                "stream token generation failed",
                extra={"scene_id": record["scene_id"], "session_id": state.session_id},
            )
            yield f"event: error\ndata: {json.dumps({'code': 'STREAM_FAILED', 'message': str(err)}, ensure_ascii=False)}\n\n"
            return

        final_data = meta["finalize"](full_reply)
        save_session_record(record)

        state_payload = with_dashboard_metrics(final_data["state"])
        yield f"event: state\ndata: {json.dumps(state_payload, ensure_ascii=False)}\n\n"
        if final_data["state_changes"]:
            yield (
                "event: changes\n"
                f"data: {json.dumps({'changes': final_data['state_changes']}, ensure_ascii=False)}\n\n"
            )
        if final_data["random_event"]:
            yield f"event: random_event\ndata: {json.dumps(final_data['random_event'], ensure_ascii=False)}\n\n"
        if final_data.get("npc_events"):
            yield f"event: npc_events\ndata: {json.dumps({'npc_events': final_data['npc_events']}, ensure_ascii=False)}\n\n"
        if final_data.get("resolution_results"):
            yield f"event: resolution\ndata: {json.dumps({'resolution_results': final_data['resolution_results']}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'message': 'complete', 'sessionId': state.session_id, 'sceneId': record['scene_id'], 'playerId': player['player_id'], 'externalUser': external_user})}\n\n"
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("stream ok scene=%s session=%s elapsed_ms=%s", record["scene_id"], state.session_id, elapsed_ms)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/reset/<session_id>", methods=["POST"])
def reset(session_id: str):
    existing = session_store.get(session_id)
    if existing:
        record = decode_session_record(existing)
        scene_id = record["scene_id"]
        external_user = record["external_user"]
        player_id = record.get("player_id", "")
        session_store.delete(session_id)
    else:
        scene_id = Config.DEFAULT_SCENE_ID
        external_user = Config.EXTERNAL_USER_DEFAULT
        player_id = ""
    try:
        record = create_session_record(scene_id, external_user, player_id)
    except KeyError:
        return error_response("UNKNOWN_SCENE", f"未知场景: {scene_id}", 400, {"scene_id": scene_id})
    state = record["state"]
    state_payload = with_dashboard_metrics(state.to_dict())
    return jsonify(
        {
            "sessionId": state.session_id,
            "sceneId": scene_id,
            "externalUser": record["external_user"],
            "playerId": record.get("player_id", ""),
            "state": state_payload,
            "message": "游戏已重置",
        }
    )


@app.route("/api/history", methods=["POST"])
def save_history():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    scene_id = (data.get("scene_id") or "").strip()
    summary = (data.get("summary") or "").strip()
    username = (data.get("username") or "").strip()
    score_raw = data.get("score", 0)
    state_snapshot = data.get("state_snapshot")

    if not session_id:
        return error_response("INVALID_HISTORY", "session_id 不能为空", 400)
    if not scene_id:
        return error_response("INVALID_HISTORY", "scene_id 不能为空", 400)
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        return error_response("INVALID_HISTORY", "score 必须是整数", 400)

    record = {
        "id": f"{session_id}-{int(time.time() * 1000)}",
        "session_id": session_id,
        "scene_id": scene_id,
        "summary": summary,
        "username": username,
        "score": max(0, min(100, score)),
        "state_snapshot": state_snapshot or {},
        "created_at": now_iso(),
    }
    history_store.add(record)
    return jsonify({"ok": True, "record": record})


@app.route("/api/history", methods=["GET"])
def list_history():
    scene_id = (request.args.get("scene_id") or "").strip() or None
    limit_raw = request.args.get("limit", "20")
    try:
        limit = max(1, min(200, int(limit_raw)))
    except ValueError:
        return error_response("INVALID_LIMIT", "limit 必须是整数", 400)
    records = history_store.list(scene_id=scene_id, limit=limit)
    return jsonify({"records": records, "count": len(records)})


@app.route("/api/players/<player_id>", methods=["GET"])
def get_player(player_id: str):
    player = player_store.get(player_id)
    if not player:
        return error_response("PLAYER_NOT_FOUND", "玩家不存在", 404, {"player_id": player_id})
    return jsonify({"player": player})


@app.route("/api/players/by-external-user/<external_user>", methods=["GET"])
def get_player_by_external_user(external_user: str):
    player = player_store.get_by_external_user(external_user)
    if not player:
        return error_response("PLAYER_NOT_FOUND", "玩家不存在", 404, {"external_user": external_user})
    return jsonify({"player": player})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
