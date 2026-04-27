# -*- coding: utf-8 -*-
"""玩家账号存储 — 自动生成并绑定 externalUser"""

import threading
import uuid

from config import Config


class PlayerStore:
    """内存中的玩家账号存储"""

    def __init__(self):
        # external_user → player_id 映射
        self._by_external: dict[str, dict] = {}
        # player_id → player 数据
        self._by_player_id: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._counter = 0

    # ------------------------------------------------------------------ #
    # 公开接口                                                             #
    # ------------------------------------------------------------------ #

    def resolve(self, external_user: str) -> dict:
        """根据 externalUser 查找或注册玩家，返回玩家信息"""
        if not external_user:
            return self._register_new()

        with self._lock:
            if external_user in self._by_external:
                return self._by_external[external_user]
            # 新用户，自动注册
            return self._do_register(external_user)

    def generate_guest(self) -> dict:
        """为游客/匿名玩家生成新账号（不绑定 externalUser）"""
        return self._register_new()

    def get(self, player_id: str) -> dict | None:
        with self._lock:
            return self._by_player_id.get(player_id)

    def get_by_external_user(self, external_user: str) -> dict | None:
        with self._lock:
            return self._by_external.get(external_user)

    # ------------------------------------------------------------------ #
    # 内部方法                                                             #
    # ------------------------------------------------------------------ #

    def _register_new(self) -> dict:
        with self._lock:
            return self._do_register()

    def _do_register(self, external_user: str = "") -> dict:
        self._counter += 1
        player_id = f"player_{self._counter:05d}"

        # 生成 external_user（全局唯一）
        if not external_user:
            external_user = f"guest_{uuid.uuid4().hex[:12]}"

        player = {
            "player_id": player_id,
            "external_user": external_user,
            "created_at": "",  # 由调用方填入
            "total_games": 0,
            "total_score": 0,
            "last_session_id": "",
            "last_scene_id": "",
        }
        self._by_player_id[player_id] = player
        self._by_external[external_user] = player
        return player

    def update_stats(self, player_id: str, session_id: str, scene_id: str, score: int = 0) -> None:
        """游戏结束后更新玩家统计"""
        with self._lock:
            player = self._by_player_id.get(player_id)
            if not player:
                return
            player["total_games"] = player.get("total_games", 0) + 1
            player["total_score"] = player.get("total_score", 0) + score
            player["last_session_id"] = session_id
            player["last_scene_id"] = scene_id


# 全局单例
player_store = PlayerStore()