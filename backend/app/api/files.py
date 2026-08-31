"""文件路由:用户文件列表、MP3 流式播放(支持 Range)。"""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import User, Video, VideoStatus
from app.schemas import FileOut

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/users/{user_id}/files", response_model=list[FileOut])
def list_files(user_id: int, db: Session = Depends(get_session)) -> list[FileOut]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    videos = db.scalars(
        select(Video).where(
            Video.user_id == user_id,
            Video.status == VideoStatus.downloaded.value,
            Video.mp3_path != "",
        ).order_by(Video.id)
    ).all()
    out: list[FileOut] = []
    for v in videos:
        out.append(FileOut(
            video_id=v.id,
            aweme_id=v.aweme_id,
            desc=v.desc,
            filename=Path(v.mp3_path).name,
            size_kb=v.size_kb,
        ))
    return out


@router.get("/files/{video_id}")
def get_file(video_id: int, db: Session = Depends(get_session)) -> FileResponse:
    v = db.get(Video, video_id)
    if not v or v.status != VideoStatus.downloaded.value or not v.mp3_path:
        raise HTTPException(404, "文件不存在或未下载")
    path = settings.output_dir / v.mp3_path
    if not path.exists():
        raise HTTPException(404, "文件已被移除")
    media_type, _ = mimetypes.guess_type(path)
    return FileResponse(
        path,
        media_type=media_type or "audio/mpeg",
        filename=path.name,
    )


@router.delete("/files/{video_id}")
def delete_file(video_id: int, db: Session = Depends(get_session)) -> dict:
    """删除指定视频的 MP3 文件(磁盘 + DB 记录)。"""
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "视频不存在")
    if v.mp3_path:
        path = settings.output_dir / v.mp3_path
        if path.exists():
            path.unlink()
        v.mp3_path = ""
    v.status = VideoStatus.skipped.value
    db.commit()
    return {"ok": True}
