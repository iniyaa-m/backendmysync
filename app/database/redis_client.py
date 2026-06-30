import json
from typing import Any, Optional

# In-memory cache fallback — no Redis required
_store: dict = {}


async def get_redis():
    return None


async def close_redis():
    pass


class RedisCache:
    def __init__(self, prefix: str = "mindsync"):
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        return _store.get(self._key(key))

    async def set(self, key: str, value: Any, ttl: int = 300):
        _store[self._key(key)] = value

    async def delete(self, key: str):
        _store.pop(self._key(key), None)

    async def delete_pattern(self, pattern: str):
        keys = [k for k in _store if k.startswith(f"{self.prefix}:{pattern.rstrip('*')}")]
        for k in keys:
            _store.pop(k, None)

    async def increment(self, key: str, ttl: int = 86400) -> int:
        full_key = self._key(key)
        _store[full_key] = _store.get(full_key, 0) + 1
        return _store[full_key]

    async def exists(self, key: str) -> bool:
        return self._key(key) in _store

    async def publish(self, channel: str, message: str):
        pass


cache = RedisCache()
