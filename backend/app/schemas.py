"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# User
# ============================================================

class UserOut(BaseModel):
    id: int
    seq: int
    nickname: str
    douyin_id: str
    likes: str
    followers: str
    url: str
    sec_user_id: str
    created_at: datetime
    video_count: int = 0
    downloaded_count: int = 0

    model_config = {"from_attributes": True}


class ParseTableRequest(BaseModel):
    content: str = Field(..., description="markdown 表格原文")


class ParseTableResponse(BaseModel):
    inserted: int
    updated: int
    total: int


# ============================================================
# Cookie
# ============================================================

class CookieRequest(BaseModel):
    content: str = Field(..., description="JSON 数组或原始 cookie 字符串")


class CookieStatus(BaseModel):
    loaded: bool
    format: str = ""  # "JSON" | "字符串" | ""
    length: int = 0
    preview: str = ""


# ============================================================
# Video / File
# ============================================================

class VideoOut(BaseModel):
    id: int
    user_id: int
    aweme_id: str
    desc: str
    music_title: str
    status: str
    size_kb: int
    error_msg: str
    created_at: datetime
    has_file: bool = False

    model_config = {"from_attributes": True}


class FileOut(BaseModel):
    video_id: int
    aweme_id: str
    desc: str
    filename: str
    size_kb: int


# ============================================================
# Task
# ============================================================

class DownloadRequest(BaseModel):
    user_ids: list[int] = Field(..., min_length=1)
    max_videos_per_user: int = Field(0, ge=0, description="0=全部")


class DownloadTaskOut(BaseModel):
    id: int
    type: str
    user_id: Optional[int] = None
    status: str
    progress: int
    total_videos: int
    success_count: int
    failed_count: int
    skipped_count: int
    max_videos_per_user: int
    error_msg: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCreatedResponse(BaseModel):
    task_id: int
    enqueued: bool


class ProgressEvent(BaseModel):
    """SSE 推送的进度事件 payload。"""
    task_id: int
    status: str
    progress: int
    current: int
    total: int
    current_desc: str = ""
    success: int
    failed: int
    skipped: int


# ============================================================
# Pipeline / 转写
# ============================================================

class PipelineRequest(BaseModel):
    user_id: int
    max_videos_per_user: int = Field(0, ge=0, description="0=全部")
    delete_mp3: bool = Field(True, description="转写后删除 MP3")
    language: str = Field("zh")
    model_name: str = Field("base")


class ImportUrlRequest(BaseModel):
    url: str = Field(..., description="抖音用户主页 URL")
    nickname: str = Field("", description="可选昵称,留空则从 URL 推断")
    max_videos_per_user: int = Field(0, ge=0)
    delete_mp3: bool = Field(True)
    auto_start: bool = Field(True, description="导入后自动启动 pipeline")


class ImportUrlResponse(BaseModel):
    user_id: int
    task_id: Optional[int] = None
    enqueued: bool = False


class TranscriptionOut(BaseModel):
    id: int
    video_id: int
    user_id: int
    text: str
    status: str
    error_msg: str
    desc: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class MergedTextOut(BaseModel):
    content: str
    path: str
