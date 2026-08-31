"""任务路由:创建下载任务、列表、详情、SSE 进度流。"""
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DownloadTask, TaskStatus, TaskType
from app.schemas import DownloadRequest, DownloadTaskOut, TaskCreatedResponse, PipelineRequest
from app.workers.arq_client import enqueue_download_user, enqueue_pipeline
from app.workers.progress import get_progress

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/download")
async def create_download(
    payload: DownloadRequest, db: Session = Depends(get_session)
) -> list[TaskCreatedResponse]:
    """为每个选中的用户创建一个下载任务并入队。"""
    results: list[TaskCreatedResponse] = []
    for uid in payload.user_ids:
        task = DownloadTask(
            type=TaskType.single_user.value,
            user_id=uid,
            status=TaskStatus.pending.value,
            max_videos_per_user=payload.max_videos_per_user,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        job_id = await enqueue_download_user(task.id, uid, payload.max_videos_per_user)
        results.append(TaskCreatedResponse(task_id=task.id, enqueued=bool(job_id)))
    return results


@router.post("/pipeline")
async def create_pipeline(
    payload: PipelineRequest, db: Session = Depends(get_session)
) -> TaskCreatedResponse:
    """创建 pipeline 任务(下载→转写→合并→删MP3)。"""
    task = DownloadTask(
        type=TaskType.single_user.value,
        user_id=payload.user_id,
        status=TaskStatus.pending.value,
        max_videos_per_user=payload.max_videos_per_user,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    job_id = await enqueue_pipeline(
        task.id, payload.user_id, payload.max_videos_per_user,
        delete_mp3=payload.delete_mp3,
        language=payload.language,
        model_name=payload.model_name,
    )
    return TaskCreatedResponse(task_id=task.id, enqueued=bool(job_id))


@router.get("", response_model=list[DownloadTaskOut])
def list_tasks(db: Session = Depends(get_session)) -> list[DownloadTaskOut]:
    tasks = db.scalars(select(DownloadTask).order_by(DownloadTask.id.desc())).all()
    return [DownloadTaskOut.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=DownloadTaskOut)
def get_task(task_id: int, db: Session = Depends(get_session)) -> DownloadTaskOut:
    t = db.get(DownloadTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return DownloadTaskOut.model_validate(t)


@router.post("/{task_id}/cancel", response_model=DownloadTaskOut)
def cancel_task(task_id: int, db: Session = Depends(get_session)) -> DownloadTaskOut:
    """取消未完成的任务(running/pending 标记为 cancelled)。
    注意:无法真正中断 arq worker 中正在执行的任务,只是把 DB 状态置为 cancelled,
    SSE 会收到终止信号;worker 的 finally 块也会以 DB 状态为准而提前退出。
    """
    t = db.get(DownloadTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in (TaskStatus.done.value, TaskStatus.failed.value, TaskStatus.cancelled.value):
        raise HTTPException(400, f"任务已结束({t.status}),无法取消")
    t.status = TaskStatus.cancelled.value
    t.error_msg = "用户手动取消"
    t.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    return DownloadTaskOut.model_validate(t)


@router.delete("/{task_id}", response_model=dict)
def delete_task(task_id: int, db: Session = Depends(get_session)) -> dict:
    """删除任务记录(仅允许删除已结束的任务)。"""
    t = db.get(DownloadTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in (TaskStatus.pending.value, TaskStatus.running.value):
        raise HTTPException(400, "任务进行中,请先取消再删除")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.get("/{task_id}/events")
async def task_events(task_id: int, db: Session = Depends(get_session)):
    """SSE:每秒读 Redis 进度快照,变化则推送;任务结束推 done 后关闭。"""
    t = db.get(DownloadTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")

    async def event_stream():
        last_payload = None
        # 先发一个 retry 指令 + 初始事件
        yield ": connected\n\n"
        while True:
            progress = get_progress(task_id)
            # 以 DB 状态为准判断终止
            db.expire_all()
            task = db.get(DownloadTask, task_id)
            terminal = task and task.status in (TaskStatus.done.value, TaskStatus.failed.value, TaskStatus.cancelled.value)

            payload = progress
            if payload is None and task is not None:
                # 没有进度快照时,从 DB 兜底构造
                payload = {
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "current": task.success_count + task.failed_count + task.skipped_count,
                    "total": task.total_videos,
                    "current_desc": "",
                    "success": task.success_count,
                    "failed": task.failed_count,
                    "skipped": task.skipped_count,
                }

            if payload and payload != last_payload:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last_payload = payload

            if terminal:
                yield f"event: done\ndata: {json.dumps(payload or {}, ensure_ascii=False)}\n\n"
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
