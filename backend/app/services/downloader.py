"""下载核心 —— 从 douyin_mp3_downloader.py 迁入,原样复用关键函数。"""
import re
from pathlib import Path

import httpx

from app.config import settings


# 文件名非法字符(跨平台)
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
MULTI_SPACE = re.compile(r"[\s_]+")


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符,限制长度。"""
    name = ILLEGAL_CHARS.sub("_", name).strip()
    name = MULTI_SPACE.sub("_", name).strip("_")
    return (name or "untitled")[:max_len]


def build_mp3_filename(desc: str, music_title: str, aweme_id: str) -> str:
    """构造与原脚本一致的 MP3 文件名: 描述 [aweme_id].mp3"""
    base = sanitize_filename(desc or music_title or "untitled", max_len=80)
    return f"{base} [{aweme_id}].mp3"


# ============================================================
# f2: 获取用户视频列表(含 MP3 直链)
# ============================================================

async def fetch_user_videos(
    sec_user_id: str,
    cookie: str,
    max_videos: int = 0,
) -> list[dict]:
    """用 f2 获取用户视频列表,返回 [{aweme_id, desc, music_url, music_title}, ...]"""
    from f2.apps.douyin.handler import DouyinHandler

    kwargs = {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
        "cookie": cookie,
        "proxies": {"http://": None, "https://": None},
        "timeout": 2,
    }

    handler = DouyinHandler(kwargs)
    videos: list[dict] = []

    async for page in handler.fetch_user_post_videos(
        sec_user_id=sec_user_id,
        max_cursor=0,
        page_counts=20,
        max_counts=max_videos if max_videos > 0 else None,
    ):
        if not page.has_aweme:
            break

        aweme_ids = page.aweme_id or []
        descs = page.desc or []
        music_urls = page.music_play_url or []
        music_titles = page.music_title or []

        for i, aid in enumerate(aweme_ids):
            desc = descs[i] if i < len(descs) else ""
            music_url = music_urls[i] if i < len(music_urls) else ""
            music_title = music_titles[i] if i < len(music_titles) else ""
            videos.append({
                "aweme_id": aid,
                "desc": desc,
                "music_url": music_url,
                "music_title": music_title,
            })

    return videos


# ============================================================
# HTTP 下载 MP3
# ============================================================

async def download_mp3(music_url: str, output_path: Path, cookie: str) -> dict:
    """直接 HTTP 下载 MP3 文件。返回 {ok, msg, size_kb}。"""
    if not music_url:
        return {"ok": False, "msg": "无音频 URL", "size_kb": 0}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(settings.download_timeout_seconds, connect=10.0),
        ) as client:
            resp = await client.get(music_url)
            resp.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.content)
            size_kb = int(len(resp.content) / 1024)
            return {"ok": True, "msg": f"成功 ({size_kb} KB)", "size_kb": size_kb}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "msg": f"HTTP {e.response.status_code}", "size_kb": 0}
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}", "size_kb": 0}
