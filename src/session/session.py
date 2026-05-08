import asyncio
import time
from typing import Dict

#In memory stores
_sessions: Dict[str, Dict]= {}
_locks: Dict[str,asyncio.Lock]={}
_lock_timestamps: Dict[str, float]= {}

SESSION_TTL = 3600 #1 hour
LOCK_TIMEOUT = 30

def _get_lock(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


async def get_session(api_key: str) -> Dict:
    entry = _sessions.get(api_key)

    if not entry:
        return {}

    if time.time() - entry["timestamp"] > SESSION_TTL:
        del _sessions[api_key]
        return {}
    return entry


async def set_session(api_key: str, data: dict):
    _sessions[api_key] = {**data, "_created_at": time.time()}

async def clear_session(api_key: str):
    _sessions.pop(api_key, None)

async def acquire_lock(api_key:str, lock_name:str) -> bool:
    key = f"{api_key}:{lock_name}"
    lock = _get_lock(key)

    #If already locked, check if it is stale
    if lock.locked():
        acquired_at = _lock_timestamps.get(key, 0)
        if time.time() - acquired_at > LOCK_TIMEOUT:
            try:
                lock.release()
            except RuntimeError:
                pass
        else:
            return False
    await lock.acquire()
    _lock_timestamps[key] = time.time()
    return True

async def release_lock(api_key: str, lock_name: str):
    key = f"{api_key}:{lock_name}"
    lock = _get_lock(key)
    if lock.locked():
        lock.release()


