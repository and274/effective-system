import json
import logging
import time
from collections import OrderedDict
from typing import Dict, Optional

from config import Config

logger = logging.getLogger("zhimei-backend.session_store")

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class SessionStore:
    def get(self, session_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def set(self, session_id: str, payload: Dict) -> None:
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """内存会话存储，支持 TTL 淘汰和最大容量限制（LRU）。"""

    def __init__(self, ttl_seconds: int = 86400, max_size: int = 10000):
        self._data: Dict[str, Dict] = {}
        self._expires: Dict[str, float] = {}
        self._access_order = OrderedDict()
        self._ttl_seconds = max(0, ttl_seconds)
        self._max_size = max(100, max_size)

    def _is_expired(self, session_id: str) -> bool:
        if self._ttl_seconds <= 0:
            return False
        expire_at = self._expires.get(session_id)
        return expire_at is not None and time.time() > expire_at

    def _evict_if_needed(self) -> None:
        """LRU 淘汰：超出容量时移除最久未访问的条目。"""
        while len(self._data) >= self._max_size:
            try:
                oldest_id, _ = self._access_order.popitem(last=False)
                self._data.pop(oldest_id, None)
                self._expires.pop(oldest_id, None)
                logger.debug("LRU 淘汰会话: %s", oldest_id)
            except KeyError:
                break

    def _cleanup_expired(self) -> None:
        """清理已过期条目（惰性清理，每次访问时触发）。"""
        now = time.time()
        expired = [sid for sid, exp in self._expires.items() if now > exp]
        for sid in expired:
            self._data.pop(sid, None)
            self._expires.pop(sid, None)
            self._access_order.pop(sid, None)

    def get(self, session_id: str) -> Optional[Dict]:
        self._cleanup_expired()
        if self._is_expired(session_id):
            self.delete(session_id)
            return None
        payload = self._data.get(session_id)
        if payload is not None:
            # 更新访问顺序（LRU）
            self._access_order.move_to_end(session_id, last=True)
        return payload

    def set(self, session_id: str, payload: Dict) -> None:
        self._evict_if_needed()
        self._data[session_id] = payload
        if self._ttl_seconds > 0:
            self._expires[session_id] = time.time() + self._ttl_seconds
        self._access_order[session_id] = True
        self._access_order.move_to_end(session_id, last=True)

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)
        self._expires.pop(session_id, None)
        self._access_order.pop(session_id, None)


class RedisSessionStore(SessionStore):
    def __init__(self, redis_url: str, prefix: str, ttl_seconds: int = 0):
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._ttl_seconds = max(0, int(ttl_seconds))

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def get(self, session_id: str) -> Optional[Dict]:
        raw = self._client.get(self._key(session_id))
        if not raw:
            return None
        # 刷新 TTL（滑动过期）
        if self._ttl_seconds > 0:
            self._client.expire(self._key(session_id), self._ttl_seconds)
        return json.loads(raw)

    def set(self, session_id: str, payload: Dict) -> None:
        kwargs = {}
        if self._ttl_seconds > 0:
            kwargs["ex"] = self._ttl_seconds
        self._client.set(self._key(session_id), json.dumps(payload, ensure_ascii=False), **kwargs)

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))


def build_session_store() -> SessionStore:
    if Config.SESSION_STORE.lower() == "redis":
        try:
            return RedisSessionStore(
                Config.REDIS_URL,
                Config.SESSION_PREFIX,
                ttl_seconds=Config.SESSION_TTL_SECONDS,
            )
        except Exception:
            logger.warning("Redis 连接失败，回退到内存存储", exc_info=True)
            return InMemorySessionStore(
                ttl_seconds=Config.SESSION_TTL_SECONDS,
                max_size=10000,
            )
    return InMemorySessionStore(
        ttl_seconds=Config.SESSION_TTL_SECONDS,
        max_size=10000,
    )


session_store = build_session_store()
