"""用户相关路由:解析表格、列表、详情、删除。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import User, Video, VideoStatus, Transcription
from app.schemas import (
    ParseTableRequest,
    ParseTableResponse,
    UserOut,
    ImportUrlRequest,
    ImportUrlResponse,
    TranscriptionOut,
    MergedTextOut,
)
from app.services.table_parser import parse_users_table, extract_sec_user_id

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/parse-table", response_model=ParseTableResponse)
def parse_table(payload: ParseTableRequest, db: Session = Depends(get_session)) -> ParseTableResponse:
    parsed = parse_users_table(payload.content)
    inserted = updated = 0
    for p in parsed:
        existing = db.scalar(select(User).where(User.seq == p["seq"]))
        if existing:
            existing.nickname = p["nickname"]
            existing.douyin_id = p["douyin_id"]
            existing.likes = p["likes"]
            existing.followers = p["followers"]
            existing.url = p["url"]
            existing.sec_user_id = p["sec_user_id"]
            updated += 1
        else:
            db.add(User(**p))
            inserted += 1
    db.commit()
    return ParseTableResponse(inserted=inserted, updated=updated, total=inserted + updated)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_session)) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.seq)).all()
    out: list[UserOut] = []
    for u in users:
        video_count = db.scalar(select(func.count(Video.id)).where(Video.user_id == u.id)) or 0
        downloaded = db.scalar(
            select(func.count(Video.id)).where(
                Video.user_id == u.id, Video.status == VideoStatus.downloaded.value
            )
        ) or 0
        out.append(UserOut(
            id=u.id, seq=u.seq, nickname=u.nickname, douyin_id=u.douyin_id,
            likes=u.likes, followers=u.followers, url=u.url, sec_user_id=u.sec_user_id,
            created_at=u.created_at, video_count=video_count, downloaded_count=downloaded,
        ))
    return out


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_session)) -> UserOut:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    video_count = db.scalar(select(func.count(Video.id)).where(Video.user_id == u.id)) or 0
    downloaded = db.scalar(
        select(func.count(Video.id)).where(
            Video.user_id == u.id, Video.status == VideoStatus.downloaded.value
        )
    ) or 0
    return UserOut(
        id=u.id, seq=u.seq, nickname=u.nickname, douyin_id=u.douyin_id,
        likes=u.likes, followers=u.followers, url=u.url, sec_user_id=u.sec_user_id,
        created_at=u.created_at, video_count=video_count, downloaded_count=downloaded,
    )


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_session)) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ============================================================
# URL 导入 + Pipeline
# ============================================================

@router.post("/import-url", response_model=ImportUrlResponse)
async def import_url(
    payload: ImportUrlRequest, db: Session = Depends(get_session)
) -> ImportUrlResponse:
    """从抖音用户主页 URL 提取 sec_user_id,创建/更新用户,可选自动启动 pipeline。"""
    sec_user_id = extract_sec_user_id(payload.url)
    if not sec_user_id:
        raise HTTPException(400, "无法从 URL 提取 sec_user_id,请检查链接格式")

    # 查找已有用户
    user = db.scalar(select(User).where(User.sec_user_id == sec_user_id))
    nickname = payload.nickname or f"用户_{sec_user_id[:8]}"
    if user:
        user.url = payload.url
        if payload.nickname:
            user.nickname = nickname
    else:
        # seq 取最大值+1
        max_seq = db.scalar(select(func.max(User.seq))) or 0
        user = User(
            seq=max_seq + 1,
            nickname=nickname,
            douyin_id="",
            likes="",
            followers="",
            url=payload.url,
            sec_user_id=sec_user_id,
        )
        db.add(user)
    db.commit()
    db.refresh(user)

    task_id = None
    enqueued = False
    if payload.auto_start:
        from app.models import DownloadTask, TaskStatus, TaskType
        from app.workers.arq_client import enqueue_pipeline
        task = DownloadTask(
            type=TaskType.single_user.value,
            user_id=user.id,
            status=TaskStatus.pending.value,
            max_videos_per_user=payload.max_videos_per_user,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        job_id = await enqueue_pipeline(
            task.id, user.id, payload.max_videos_per_user,
            delete_mp3=payload.delete_mp3,
        )
        task_id = task.id
        enqueued = bool(job_id)

    return ImportUrlResponse(user_id=user.id, task_id=task_id, enqueued=enqueued)


# ============================================================
# 转写文本
# ============================================================

@router.get("/{user_id}/transcriptions", response_model=list[TranscriptionOut])
def list_transcriptions(user_id: int, db: Session = Depends(get_session)) -> list[TranscriptionOut]:
    """获取用户的所有转写文本。"""
    rows = db.scalars(
        select(Transcription).where(Transcription.user_id == user_id).order_by(Transcription.id)
    ).all()
    out: list[TranscriptionOut] = []
    for tx in rows:
        v = db.get(Video, tx.video_id)
        out.append(TranscriptionOut(
            id=tx.id, video_id=tx.video_id, user_id=tx.user_id,
            text=tx.text, status=tx.status, error_msg=tx.error_msg,
            desc=v.desc if v else "", created_at=tx.created_at,
        ))
    return out


@router.get("/{user_id}/merged-text", response_model=MergedTextOut)
def get_merged_text(user_id: int, db: Session = Depends(get_session)) -> MergedTextOut:
    """获取用户合并后的完整文本。"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    merged_path = settings.output_dir / user.folder_name() / "all_texts_merged.txt"
    content = ""
    if merged_path.exists():
        content = merged_path.read_text(encoding="utf-8")
    return MergedTextOut(content=content, path=str(merged_path))
