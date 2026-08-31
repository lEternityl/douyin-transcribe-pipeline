"""arq 客户端:从 FastAPI 入队任务。"""
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings


async def enqueue_download_user(task_id: int, user_id: int, max_videos_per_user: int) -> str:
    """入队下载任务,返回 job_id。"""
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await pool.enqueue_job(
        "download_user_task",
        task_id=task_id,
        user_id=user_id,
        max_videos_per_user=max_videos_per_user,
    )
    return job.job_id if job else ""


async def enqueue_pipeline(
    task_id: int, user_id: int, max_videos_per_user: int,
    delete_mp3: bool = True, language: str = "zh", model_name: str = "base",
) -> str:
    """入队 pipeline 任务(下载→转写→合并→删MP3),返回 job_id。"""
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await pool.enqueue_job(
        "pipeline_task",
        task_id=task_id,
        user_id=user_id,
        max_videos_per_user=max_videos_per_user,
        delete_mp3=delete_mp3,
        language=language,
        model_name=model_name,
    )
    return job.job_id if job else ""
