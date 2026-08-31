import { useEffect, useRef, useState } from "react";
import type { ProgressEvent } from "../api/types";

/**
 * 订阅任务 SSE 进度流。
 * - 连接 /api/tasks/{id}/events
 * - data 事件 → 更新 progress
 * - done 事件 → 标记 finished
 */
export function useTaskProgress(taskId: number | null) {
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (taskId == null) return;
    setProgress(null);
    setFinished(false);
    setError(null);

    const es = new EventSource(`/api/tasks/${taskId}/events`);
    esRef.current = es;

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as ProgressEvent;
        setProgress(data);
      } catch {
        /* ignore parse error */
      }
    };
    es.addEventListener("done", (ev) => {
      try {
        setProgress(JSON.parse((ev as MessageEvent).data) as ProgressEvent);
      } catch {
        /* ignore */
      }
      setFinished(true);
      es.close();
    });
    es.onerror = () => {
      setError("连接中断");
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId]);

  return { progress, finished, error };
}
