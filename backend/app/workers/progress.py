"""Redis 进度读写 —— arq 任务写,SSE 端点读。"""
import json
from typing import Optional

import redis

from app.config import settings


def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def progress_key(task_id: int) -> str:
    return f"task:{task_id}:progress"


def set_progress(task_id: int, data: dict) -> None:
    """写进度快照。带 24h 过期,避免残留。"""
    _client().setex(progress_key(task_id), 86400, json.dumps(data, ensure_ascii=False))


def get_progress(task_id: int) -> Optional[dict]:
    raw = _client().get(progress_key(task_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
