"""arq worker 配置。

启动:
  uv run arq app.workers.arq_app.WorkerSettings
"""
from arq.connections import RedisSettings

from app.config import settings
from app.workers.tasks import download_user_task, pipeline_task


class WorkerSettings:
    """arq WorkerSettings。"""
    functions = [download_user_task, pipeline_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1  # 顺序下载,避免被风控
    job_timeout = 3600
