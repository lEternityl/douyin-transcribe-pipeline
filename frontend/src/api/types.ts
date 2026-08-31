// 后端响应类型(与 backend/app/schemas.py 对应)

export interface UserOut {
  id: number;
  seq: number;
  nickname: string;
  douyin_id: string;
  likes: string;
  followers: string;
  url: string;
  sec_user_id: string;
  created_at: string;
  video_count: number;
  downloaded_count: number;
}

export interface VideoOut {
  id: number;
  user_id: number;
  aweme_id: string;
  desc: string;
  music_title: string;
  status: "pending" | "downloaded" | "failed" | "skipped";
  size_kb: number;
  error_msg: string;
  created_at: string;
  has_file: boolean;
}

export interface FileOut {
  video_id: number;
  aweme_id: string;
  desc: string;
  filename: string;
  size_kb: number;
}

export interface DownloadTaskOut {
  id: number;
  type: string;
  user_id: number | null;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  total_videos: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  max_videos_per_user: number;
  error_msg: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ProgressEvent {
  task_id: number;
  status: string;
  progress: number;
  current: number;
  total: number;
  current_desc: string;
  success: number;
  failed: number;
  skipped: number;
}

export interface CookieStatus {
  loaded: boolean;
  format: string;
  length: number;
  preview: string;
}

export interface TranscriptionOut {
  id: number;
  video_id: number;
  user_id: number;
  text: string;
  status: string;
  error_msg: string;
  desc: string;
  created_at: string;
}

export interface MergedTextOut {
  content: string;
  path: string;
}

export interface ImportUrlResponse {
  user_id: number;
  task_id: number | null;
  enqueued: boolean;
}
