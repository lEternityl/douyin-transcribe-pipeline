// 简易 API client(走 vite proxy,同源 /api)
import type {
  CookieStatus,
  DownloadTaskOut,
  FileOut,
  UserOut,
  TranscriptionOut,
  MergedTextOut,
  ImportUrlResponse,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

// ===== Users =====
export const api = {
  listUsers: () => request<UserOut[]>("/users"),
  getUser: (id: number) => request<UserOut>(`/users/${id}`),
  deleteUser: (id: number) =>
    request<{ ok: boolean }>(`/users/${id}`, { method: "DELETE" }),
  parseTable: (content: string) =>
    request<{ inserted: number; updated: number; total: number }>(
      "/users/parse-table",
      { method: "POST", body: JSON.stringify({ content }) }
    ),
  listFiles: (userId: number) =>
    request<FileOut[]>(`/users/${userId}/files`),

  // ===== Cookie =====
  cookieStatus: () => request<CookieStatus>("/cookie/status"),
  setCookie: (content: string) =>
    request<CookieStatus>("/cookie", { method: "POST", body: JSON.stringify({ content }) }),

  // ===== Tasks =====
  createDownload: (userIds: number[], maxVideosPerUser: number) =>
    request<{ task_id: number; enqueued: boolean }[]>("/tasks/download", {
      method: "POST",
      body: JSON.stringify({ user_ids: userIds, max_videos_per_user: maxVideosPerUser }),
    }),
  listTasks: () => request<DownloadTaskOut[]>("/tasks"),
  getTask: (id: number) => request<DownloadTaskOut>(`/tasks/${id}`),
  cancelTask: (id: number) =>
    request<DownloadTaskOut>(`/tasks/${id}/cancel`, { method: "POST" }),
  deleteTask: (id: number) =>
    request<{ ok: boolean }>(`/tasks/${id}`, { method: "DELETE" }),

  // ===== Files =====
  fileUrl: (videoId: number) => `${BASE}/files/${videoId}`,
  deleteFile: (videoId: number) =>
    request<{ ok: boolean }>(`/files/${videoId}`, { method: "DELETE" }),

  // ===== Pipeline / 转写 =====
  importUrl: (url: string, opts?: { nickname?: string; maxVideosPerUser?: number; deleteMp3?: boolean; autoStart?: boolean }) =>
    request<ImportUrlResponse>("/users/import-url", {
      method: "POST",
      body: JSON.stringify({
        url,
        nickname: opts?.nickname ?? "",
        max_videos_per_user: opts?.maxVideosPerUser ?? 0,
        delete_mp3: opts?.deleteMp3 ?? true,
        auto_start: opts?.autoStart ?? true,
      }),
    }),
  createPipeline: (userId: number, maxVideosPerUser: number, deleteMp3: boolean) =>
    request<{ task_id: number; enqueued: boolean }>("/tasks/pipeline", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, max_videos_per_user: maxVideosPerUser, delete_mp3: deleteMp3 }),
    }),
  listTranscriptions: (userId: number) =>
    request<TranscriptionOut[]>(`/users/${userId}/transcriptions`),
  getMergedText: (userId: number) =>
    request<MergedTextOut>(`/users/${userId}/merged-text`),
};
