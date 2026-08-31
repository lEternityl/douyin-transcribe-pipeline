"""arq 任务定义 —— 下载任务主逻辑(从原 process_user 重写)。

把原脚本的 print 改为:
  - DB 写入(Video 行状态)
  - Redis 进度快照
  - DownloadTask 状态字段更新
"""
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import DownloadTask, TaskStatus, User, Video, VideoStatus
from app.services.cookie import load_cookie_string
from app.services.downloader import (
    build_mp3_filename,
    download_mp3,
    fetch_user_videos,
)
from app.workers.progress import set_progress

logger = logging.getLogger(__name__)


def _publish_progress(
    task_id: int,
    status: str,
    current: int,
    total: int,
    current_desc: str,
    success: int,
    failed: int,
    skipped: int,
) -> None:
    progress = int(current / total * 100) if total else 0
    set_progress(task_id, {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "current": current,
        "total": total,
        "current_desc": current_desc,
        "success": success,
        "failed": failed,
        "skipped": skipped,
    })


async def download_user_task(
    ctx: dict,
    task_id: int,
    user_id: int,
    max_videos_per_user: int,
) -> dict:
    """下载单个用户全部视频的 arq 任务。"""
    cookie = load_cookie_string()
    if not cookie:
        msg = "cookie 未加载"
        _fail_task(task_id, msg)
        _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
        return {"ok": False, "msg": msg}

    with SessionLocal() as db:
        task = db.get(DownloadTask, task_id)
        user = db.get(User, user_id)
        if not task or not user:
            return {"ok": False, "msg": "task 或 user 不存在"}

        task.status = TaskStatus.running.value
        task.started_at = datetime.utcnow()
        db.commit()

        sec_user_id = user.sec_user_id
        try:
            videos = await fetch_user_videos(sec_user_id, cookie, max_videos_per_user)
        except Exception as e:
            msg = f"获取视频列表失败: {type(e).__name__}: {e}"
            _fail_task(task_id, msg)
            _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
            return {"ok": False, "msg": msg}

        if not videos:
            msg = "未获取到任何视频(cookie 可能已过期)"
            _fail_task(task_id, msg)
            _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
            return {"ok": False, "msg": msg}

        # 本地强制限制(f2 的 max_counts 第一页全返回)
        if max_videos_per_user > 0 and len(videos) > max_videos_per_user:
            videos = videos[:max_videos_per_user]

        # upsert Video 行(判重)
        existing = {
            v.aweme_id: v
            for v in db.scalars(select(Video).where(Video.user_id == user_id)).all()
        }
        video_rows: list[Video] = []
        for v in videos:
            row = existing.get(v["aweme_id"])
            if row is None:
                row = Video(
                    user_id=user_id,
                    aweme_id=v["aweme_id"],
                    desc=v.get("desc", ""),
                    music_title=v.get("music_title", ""),
                    music_url=v.get("music_url", ""),
                    status=VideoStatus.pending.value,
                )
                db.add(row)
                video_rows.append(row)
            else:
                video_rows.append(row)
        db.commit()

        total = len(video_rows)
        task.total_videos = total
        db.commit()

        user_dir = settings.output_dir / user.folder_name()
        success = failed = skipped = 0

        for i, (vinfo, vrow) in enumerate(zip(videos, video_rows), start=1):
            desc_preview = (vinfo["desc"] or vinfo.get("music_title") or "").replace("\n", " ")[:50]
            music_url = vinfo["music_url"]

            if not music_url:
                vrow.status = VideoStatus.skipped.value
                skipped += 1
                _publish_progress(task_id, TaskStatus.running.value, i, total, desc_preview, success, failed, skipped)
                db.commit()
                continue

            filename = build_mp3_filename(vinfo["desc"], vinfo.get("music_title", ""), vinfo["aweme_id"])
            output_path = user_dir / filename

            # 断点续传: 已存在且文件非空
            if output_path.exists() and output_path.stat().st_size > 0:
                vrow.status = VideoStatus.downloaded.value
                vrow.mp3_path = str(output_path.relative_to(settings.output_dir))
                vrow.size_kb = int(output_path.stat().st_size / 1024)
                success += 1
                _publish_progress(task_id, TaskStatus.running.value, i, total, desc_preview, success, failed, skipped)
                db.commit()
                continue

            result = await download_mp3(music_url, output_path, cookie)
            if result["ok"]:
                vrow.status = VideoStatus.downloaded.value
                vrow.mp3_path = str(output_path.relative_to(settings.output_dir))
                vrow.size_kb = result.get("size_kb", 0)
                success += 1
            else:
                vrow.status = VideoStatus.failed.value
                vrow.error_msg = result["msg"]
                failed += 1

            _publish_progress(task_id, TaskStatus.running.value, i, total, desc_preview, success, failed, skipped)
            db.commit()

        task.status = TaskStatus.done.value
        task.progress = 100
        task.success_count = success
        task.failed_count = failed
        task.skipped_count = skipped
        task.finished_at = datetime.utcnow()
        db.commit()

        _publish_progress(task_id, TaskStatus.done.value, total, total, "", success, failed, skipped)
        return {"ok": True, "success": success, "failed": failed, "skipped": skipped, "total": total}


def _fail_task(task_id: int, msg: str) -> None:
    with SessionLocal() as db:
        task = db.get(DownloadTask, task_id)
        if task:
            task.status = TaskStatus.failed.value
            task.error_msg = msg
            task.finished_at = datetime.utcnow()
            db.commit()


# ============================================================
# Pipeline 任务: 下载 → 转写 → 合并 → 删 MP3
# ============================================================

async def pipeline_task(
    ctx: dict,
    task_id: int,
    user_id: int,
    max_videos_per_user: int,
    delete_mp3: bool = True,
    language: str = "zh",
    model_name: str = "base",
) -> dict:
    """一条龙: 下载 → 转写 → 合并文本 → 删除 MP3"""
    from app.models import Transcription
    from app.services.transcriber import transcribe_file

    cookie = load_cookie_string()
    if not cookie:
        msg = "cookie 未加载"
        _fail_task(task_id, msg)
        _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
        return {"ok": False, "msg": msg}

    with SessionLocal() as db:
        task = db.get(DownloadTask, task_id)
        user = db.get(User, user_id)
        if not task or not user:
            return {"ok": False, "msg": "task 或 user 不存在"}

        task.status = TaskStatus.running.value
        task.started_at = datetime.utcnow()
        db.commit()

        user_dir = settings.output_dir / user.folder_name()
        texts_dir = user_dir / "texts_local"

        # ===== 阶段 1: 下载 =====
        _publish_progress(task_id, TaskStatus.running.value, 0, 0, "正在获取视频列表...", 0, 0, 0)

        try:
            videos = await fetch_user_videos(user.sec_user_id, cookie, max_videos_per_user)
        except Exception as e:
            msg = f"获取视频列表失败: {type(e).__name__}: {e}"
            _fail_task(task_id, msg)
            _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
            return {"ok": False, "msg": msg}

        if not videos:
            msg = "未获取到任何视频(cookie 可能已过期)"
            _fail_task(task_id, msg)
            _publish_progress(task_id, TaskStatus.failed.value, 0, 0, "", 0, 0, 0)
            return {"ok": False, "msg": msg}

        if max_videos_per_user > 0 and len(videos) > max_videos_per_user:
            videos = videos[:max_videos_per_user]

        # upsert Video 行
        existing = {
            v.aweme_id: v
            for v in db.scalars(select(Video).where(Video.user_id == user_id)).all()
        }
        video_rows: list[tuple[dict, Video]] = []
        for v in videos:
            row = existing.get(v["aweme_id"])
            if row is None:
                row = Video(
                    user_id=user_id, aweme_id=v["aweme_id"],
                    desc=v.get("desc", ""), music_title=v.get("music_title", ""),
                    music_url=v.get("music_url", ""), status=VideoStatus.pending.value,
                )
                db.add(row)
            video_rows.append((v, row))
        db.commit()

        total = len(video_rows)
        task.total_videos = total
        db.commit()

        # 下载
        success = failed = skipped = 0
        for i, (vinfo, vrow) in enumerate(video_rows, start=1):
            desc_preview = (vinfo["desc"] or "").replace("\n", " ")[:50]
            music_url = vinfo["music_url"]
            filename = build_mp3_filename(vinfo["desc"], vinfo.get("music_title", ""), vinfo["aweme_id"])
            output_path = user_dir / filename

            if output_path.exists() and output_path.stat().st_size > 0:
                vrow.status = VideoStatus.downloaded.value
                vrow.mp3_path = str(output_path.relative_to(settings.output_dir))
                vrow.size_kb = int(output_path.stat().st_size / 1024)
                success += 1
            elif not music_url:
                vrow.status = VideoStatus.skipped.value
                skipped += 1
            else:
                result = await download_mp3(music_url, output_path, cookie)
                if result["ok"]:
                    vrow.status = VideoStatus.downloaded.value
                    vrow.mp3_path = str(output_path.relative_to(settings.output_dir))
                    vrow.size_kb = result.get("size_kb", 0)
                    success += 1
                else:
                    vrow.status = VideoStatus.failed.value
                    vrow.error_msg = result["msg"]
                    failed += 1

            _publish_progress(task_id, TaskStatus.running.value, i, total, f"下载: {desc_preview}", success, failed, skipped)
            db.commit()

        downloaded_videos = [(v, r) for v, r in video_rows if r.status == VideoStatus.downloaded.value and r.mp3_path]

        # ===== 阶段 2: 转写 =====
        transcribe_total = len(downloaded_videos)
        transcribe_done = 0
        all_texts: list[str] = []

        for vinfo, vrow in downloaded_videos:
            mp3_path = settings.output_dir / vrow.mp3_path
            desc_preview = (vrow.desc or "").replace("\n", " ")[:50]
            _publish_progress(
                task_id, TaskStatus.running.value,
                transcribe_done, transcribe_total,
                f"转写: {desc_preview}", success, failed, skipped,
            )

            # 已有转写则跳过
            existing_tx = db.scalar(select(Transcription).where(Transcription.video_id == vrow.id))
            if existing_tx and existing_tx.status == "done" and existing_tx.text:
                all_texts.append(existing_tx.text)
                transcribe_done += 1
                continue

            try:
                result = transcribe_file(
                    mp3_path, texts_dir, model_name=model_name, language=language
                )
                text = result["text"]
                if existing_tx:
                    existing_tx.text = text
                    existing_tx.status = "done"
                    existing_tx.error_msg = ""
                else:
                    db.add(Transcription(
                        video_id=vrow.id, user_id=user_id, text=text, status="done"
                    ))
                all_texts.append(text)
            except Exception as e:
                logger.error(f"转写失败 {mp3_path.name}: {e}")
                if existing_tx:
                    existing_tx.status = "failed"
                    existing_tx.error_msg = str(e)
                else:
                    db.add(Transcription(
                        video_id=vrow.id, user_id=user_id, status="failed", error_msg=str(e)
                    ))
            transcribe_done += 1
            _publish_progress(
                task_id, TaskStatus.running.value,
                transcribe_done, transcribe_total,
                f"转写: {desc_preview}", success, failed, skipped,
            )
            db.commit()

        # ===== 阶段 3: 合并文本 =====
        _publish_progress(task_id, TaskStatus.running.value, transcribe_total, transcribe_total, "合并文本...", success, failed, skipped)
        merged_path = user_dir / "all_texts_merged.txt"
        merged_path.write_text("\n\n".join(all_texts) + "\n", encoding="utf-8")

        # ===== 阶段 4: 删除 MP3 =====
        if delete_mp3:
            _publish_progress(task_id, TaskStatus.running.value, transcribe_total, transcribe_total, "清理 MP3...", success, failed, skipped)
            for vinfo, vrow in downloaded_videos:
                if vrow.mp3_path:
                    mp3_path = settings.output_dir / vrow.mp3_path
                    if mp3_path.exists():
                        mp3_path.unlink()
                    vrow.mp3_path = ""
                    vrow.status = VideoStatus.skipped.value  # 标记为已清理
            db.commit()

        task.status = TaskStatus.done.value
        task.progress = 100
        task.success_count = success
        task.failed_count = failed
        task.skipped_count = skipped
        task.finished_at = datetime.utcnow()
        db.commit()

        _publish_progress(task_id, TaskStatus.done.value, total, total, "完成", success, failed, skipped)
        return {"ok": True, "success": success, "failed": failed, "skipped": skipped, "total": total, "transcribed": transcribe_done}
