"""SQLAlchemy 数据模型。"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class VideoStatus(str, Enum):
    pending = "pending"
    downloaded = "downloaded"
    failed = "failed"
    skipped = "skipped"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class TaskType(str, Enum):
    single_user = "single_user"
    batch = "batch"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)  # 表格里的序号
    nickname: Mapped[str] = mapped_column(String(120))
    douyin_id: Mapped[str] = mapped_column(String(120), index=True)
    likes: Mapped[str] = mapped_column(String(40), default="")
    followers: Mapped[str] = mapped_column(String(40), default="")
    url: Mapped[str] = mapped_column(Text)
    sec_user_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    videos: Mapped[list["Video"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def folder_name(self) -> str:
        """与原脚本一致的子文件夹命名: 001_昵称_抖音号"""
        from app.services.downloader import sanitize_filename

        return sanitize_filename(f"{self.seq:03d}_{self.nickname}_{self.douyin_id}", max_len=120)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("user_id", "aweme_id", name="uq_user_aweme"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    aweme_id: Mapped[str] = mapped_column(String(40), index=True)
    desc: Mapped[str] = mapped_column(Text, default="")
    music_title: Mapped[str] = mapped_column(Text, default="")
    music_url: Mapped[str] = mapped_column(Text, default="")
    mp3_path: Mapped[str] = mapped_column(Text, default="")  # 相对 output_dir
    status: Mapped[str] = mapped_column(String(20), default=VideoStatus.pending.value, index=True)
    size_kb: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="videos")


class DownloadTask(Base):
    __tablename__ = "download_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(20), default=TaskType.batch.value)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.pending.value, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    total_videos: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    max_videos_per_user: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/done/failed
    error_msg: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
