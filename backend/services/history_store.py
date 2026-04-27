import json
from typing import Dict, List, Optional

from config import Config

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class HistoryStore:
    def add(self, record: Dict) -> None:
        raise NotImplementedError

    def list(self, scene_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        raise NotImplementedError


class InMemoryHistoryStore(HistoryStore):
    def __init__(self, max_items: int = 200):
        self._records: List[Dict] = []
        self._max_items = max(1, int(max_items))

    def add(self, record: Dict) -> None:
        self._records.insert(0, record)
        if len(self._records) > self._max_items:
            self._records = self._records[: self._max_items]

    def list(self, scene_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        cap = max(1, int(limit))
        if not scene_id:
            return self._records[:cap]
        return [x for x in self._records if x.get("scene_id") == scene_id][:cap]


class RedisHistoryStore(HistoryStore):
    def __init__(self, redis_url: str, key: str, max_items: int = 200):
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._key = key
        self._max_items = max(1, int(max_items))

    def add(self, record: Dict) -> None:
        self._client.lpush(self._key, json.dumps(record, ensure_ascii=False))
        self._client.ltrim(self._key, 0, self._max_items - 1)

    def list(self, scene_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        cap = max(1, int(limit))
        items = self._client.lrange(self._key, 0, self._max_items - 1)
        parsed = []
        for item in items:
            try:
                parsed.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        if scene_id:
            parsed = [x for x in parsed if x.get("scene_id") == scene_id]
        return parsed[:cap]


def build_history_store() -> HistoryStore:
    backend = Config.HISTORY_STORE.lower()
    if backend == "redis":
        try:
            return RedisHistoryStore(
                redis_url=Config.REDIS_URL,
                key=Config.HISTORY_KEY,
                max_items=Config.HISTORY_MAX_ITEMS,
            )
        except Exception:
            return InMemoryHistoryStore(max_items=Config.HISTORY_MAX_ITEMS)
    return InMemoryHistoryStore(max_items=Config.HISTORY_MAX_ITEMS)


history_store = build_history_store()
