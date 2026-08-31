"""应用配置：路径、Redis、cookie 等。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/ 根目录
BACKEND_DIR = Path(__file__).resolve().parent.parent
# backend/data/ —— sqlite.db + douyin_mp3_output/ + cookies.txt
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOUYIN_", env_file=".env", extra="ignore")

    # 数据库
    db_path: Path = DATA_DIR / "douyin.db"
    # Redis（arq 任务队列 + 进度缓存）
    redis_url: str = "redis://127.0.0.1:6379/0"
    # MP3 输出根目录
    output_dir: Path = DATA_DIR / "douyin_mp3_output"
    # cookie 文件
    cookie_file: Path = DATA_DIR / "cookies.txt"
    # 前端开发地址（CORS）
    frontend_origin: str = "http://localhost:5173"
    # 单用户最大并发下载视频数（顺序下载,此项预留）
    download_timeout_seconds: float = 30.0

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
