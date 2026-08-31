#!/usr/bin/env python3.12
# -*- coding: utf-8 -*-
"""
抖音用户主页批量 MP3 下载器
- 解析 markdown 表格(序号|昵称|抖音号|获赞|粉丝|主页链接)
- 用 f2 库获取用户主页视频列表(含 music_play_url 音频直链)
- 直接 HTTP 下载 MP3(无需 yt-dlp / ffmpeg)
- 按用户创建子文件夹分类存放

依赖:
  pip install f2 httpx

注意:
  必须用 Python 3.12 运行,本机 f2 装在 3.12 环境下:
    /opt/anaconda3/bin/python3.12 douyin_mp3_downloader.py ...
  系统默认 python3 是 3.9,会找不到 f2。

用法:
  # 默认路径: 表格=脚本目录/users_table.txt, cookie=脚本目录/cookies.txt
  # 1. 先预览要处理的用户(不需要 cookie)
  python3 douyin_mp3_downloader.py --dry-run

  # 2. 试跑:前 2 个用户,每人最多 3 个视频
  python3 douyin_mp3_downloader.py --user-range 1-2 --max-videos-per-user 3

  # 3. 全量下载(使用默认 cookie 文件)
  python3 douyin_mp3_downloader.py

  # 4. 显式指定表格/cookie 文件
  python3 douyin_mp3_downloader.py users_table.txt --cookie-file cookies.txt

获取 cookie 方法:
  方式 A(推荐,导出 JSON):
  1. Chrome 安装 "Cookie-Editor" 或 "EditThisCookie" 扩展
  2. 打开 https://www.douyin.com 并登录
  3. 点击扩展图标 → 导出(Export)→ 得到 JSON 数组
  4. 保存到 cookies.txt 文件

  方式 B(手动复制字符串):
  1. Chrome 打开 https://www.douyin.com 并登录
  2. F12 → Network → 刷新页面 → 点击任意请求
  3. 在 Request Headers 中复制 Cookie 字段完整值
  4. 用 --cookie "粘贴cookie" 传入

  cookie 文件支持两种格式(自动识别):
  - JSON 数组(Cookie-Editor 导出):[{"name":"ttwid","value":"xxx"},...]
  - 原始字符串:ttwid=xxx; msToken=yyy; ...
"""

import argparse
import asyncio
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx


# 脚本所在目录: 所有默认路径都以此为基准,无论从哪里调用都能正常工作
SCRIPT_DIR = Path(__file__).resolve().parent


# 文件名非法字符(跨平台)
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
MULTI_SPACE = re.compile(r"[\s_]+")


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符,限制长度。"""
    name = ILLEGAL_CHARS.sub("_", name).strip()
    name = MULTI_SPACE.sub("_", name).strip("_")
    return (name or "untitled")[:max_len]


def clean_url(url: str) -> str:
    """剥离 URL 中的追踪参数,只保留 scheme+host+path。"""
    url = html.unescape(url).strip()
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def parse_users_table(table_file: Path) -> list[dict]:
    """解析 markdown 表格,提取用户信息。
    表格列: | 序号 | 昵称 | 抖音号 | 获赞 | 粉丝 | 主页链接 |
    """
    users = []
    with table_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p != ""]
            if len(parts) < 6:
                continue
            if parts[0] == "序号":
                continue
            if re.match(r"^[-:\s]+$", parts[0]):
                continue
            try:
                seq = int(parts[0])
            except ValueError:
                continue
            nickname = parts[1]
            douyin_id = parts[2]
            likes = parts[3]
            followers = parts[4]
            url = clean_url(parts[5])
            if "douyin.com/user/" not in url:
                continue
            users.append({
                "seq": seq,
                "nickname": nickname,
                "douyin_id": douyin_id,
                "likes": likes,
                "followers": followers,
                "url": url,
            })
    return users


def extract_sec_user_id(url: str) -> str:
    """从用户主页 URL 中提取 sec_user_id。"""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "user":
        return parts[1]
    return ""


def parse_user_range(range_str: str) -> tuple[int, int] | None:
    """解析范围字符串,如 '1-5' 或 '3'。"""
    if not range_str:
        return None
    range_str = range_str.strip()
    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    n = int(range_str)
    return n, n


# ============================================================
# Cookie 处理
# ============================================================

def json_cookies_to_string(json_text: str) -> str:
    """JSON cookie 数组 → 字符串格式。"""
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("JSON cookie 格式错误:期望数组")
    pairs = []
    for item in data:
        name = item.get("name", "")
        value = item.get("value", "")
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def load_cookie_raw(cookie_arg: str | None, cookie_file_arg: str | None) -> str:
    """加载原始 cookie 数据。"""
    if cookie_arg:
        return cookie_arg.strip()
    if cookie_file_arg:
        p = Path(cookie_file_arg).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"cookie 文件不存在: {p}")
        return p.read_text(encoding="utf-8").strip()
    return ""


def cookie_to_string(raw: str) -> str:
    """将原始 cookie 转为字符串格式。"""
    if not raw:
        return ""
    if raw.startswith("["):
        try:
            return json_cookies_to_string(raw)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"警告: JSON cookie 解析失败,退回原始字符串: {e}", file=sys.stderr)
            return raw
    return raw


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
    videos = []

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

async def download_mp3(
    music_url: str,
    output_path: Path,
    cookie: str,
) -> dict:
    """直接 HTTP 下载 MP3 文件。"""
    if not music_url:
        return {"ok": False, "msg": "无音频 URL"}

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
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            resp = await client.get(music_url)
            resp.raise_for_status()

            # 写入文件
            output_path.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            return {"ok": True, "msg": f"成功 ({size_kb:.0f} KB)"}

    except httpx.HTTPStatusError as e:
        return {"ok": False, "msg": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"}


# ============================================================
# 主流程
# ============================================================

async def process_user(
    user: dict,
    output_dir: Path,
    cookie: str,
    max_videos: int,
    idx: int,
    total: int,
) -> dict:
    """处理单个用户:获取视频列表 + 下载 MP3。"""
    nickname = user["nickname"]
    douyin_id = user["douyin_id"]
    sec_user_id = extract_sec_user_id(user["url"])

    print(f"\n[{idx}/{total}] 用户: {nickname} (抖音号: {douyin_id}, 粉丝: {user['followers']})")
    print(f"  sec_user_id: {sec_user_id[:40]}...")

    if not sec_user_id:
        return {"user": user, "ok": False, "msg": "无法从 URL 提取 sec_user_id"}

    # 创建用户子文件夹
    folder_name = sanitize_filename(f"{user['seq']:03d}_{nickname}_{douyin_id}", max_len=120)
    user_dir = output_dir / folder_name
    user_dir.mkdir(parents=True, exist_ok=True)

    # 1. 用 f2 获取视频列表(含 MP3 直链)
    try:
        videos = await fetch_user_videos(sec_user_id, cookie, max_videos)
    except Exception as e:
        return {"user": user, "ok": False, "msg": f"获取视频列表失败: {type(e).__name__}: {e}"}

    if not videos:
        return {"user": user, "ok": False, "msg": "未获取到任何视频(cookie 可能已过期)"}

    # 本地强制限制 max_videos(f2 的 max_counts 在第一页就全返回,不会真限制)
    if max_videos > 0 and len(videos) > max_videos:
        videos = videos[:max_videos]

    limit_msg = f"(限制前 {max_videos} 个)" if max_videos > 0 else "(全部)"
    print(f"  视频数: {len(videos)} {limit_msg}")

    # 2. 逐个下载 MP3
    success = 0
    failed = []
    skipped = 0
    for vi, v in enumerate(videos, 1):
        desc_preview = (v["desc"] or v.get("music_title") or "").replace("\n", " ")[:50]
        music_url = v["music_url"]

        if not music_url:
            print(f"  [{vi}/{len(videos)}] {desc_preview}... ⏭ 无音频")
            skipped += 1
            continue

        # 文件名: 视频描述 [aweme_id].mp3
        filename = sanitize_filename(v["desc"] or v.get("music_title") or "untitled", max_len=80)
        filename = f"{filename} [{v['aweme_id']}].mp3"
        output_path = user_dir / filename

        # 跳过已存在的文件
        if output_path.exists():
            print(f"  [{vi}/{len(videos)}] {desc_preview}... ✓ 已存在")
            success += 1
            continue

        print(f"  [{vi}/{len(videos)}] {desc_preview}... 下载中")
        result = await download_mp3(music_url, output_path, cookie)
        if result["ok"]:
            success += 1
            print(f"       → {result['msg']}")
        else:
            failed.append({"aweme_id": v["aweme_id"], "desc": desc_preview, "msg": result["msg"]})
            print(f"       → ✗ {result['msg']}")

    msg = f"成功 {success}/{len(videos)}"
    if skipped:
        msg += f", 跳过 {skipped}"
    return {
        "user": user,
        "ok": True,
        "video_count": len(videos),
        "success_count": success,
        "failed": failed,
        "output_dir": str(user_dir),
        "msg": msg,
    }


async def run(args):
    # 输出目录
    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
    else:
        output_dir = SCRIPT_DIR / "douyin_mp3_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 解析表格
    table_file = Path(args.table_file).expanduser().resolve()
    if not table_file.exists():
        print(f"错误: 表格文件不存在: {table_file}", file=sys.stderr)
        return 1

    users = parse_users_table(table_file)
    if not users:
        print(f"未从表格中解析到任何用户: {table_file}", file=sys.stderr)
        return 1

    # 按序号范围筛选
    user_range = parse_user_range(args.user_range) if args.user_range else None
    if user_range:
        start, end = user_range
        users = [u for u in users if start <= u["seq"] <= end]

    total = len(users)
    print(f"输出目录: {output_dir}")
    print(f"共解析到 {total} 个用户")
    if args.max_videos_per_user > 0:
        print(f"每用户最多下载: {args.max_videos_per_user} 个视频")

    # 预览模式
    if args.dry_run:
        print("\n--- DRY RUN (预览模式,不会下载) ---")
        for u in users:
            sec_uid = extract_sec_user_id(u["url"])
            print(f"  [{u['seq']:3d}] {u['nickname']:<20s} 抖音号:{u['douyin_id']:<25s} 粉丝:{u['followers']}")
            print(f"        sec_user_id: {sec_uid[:50]}...")
        print(f"\n共 {total} 个用户")
        return 0

    # 加载 cookie
    raw_cookie = load_cookie_raw(args.cookie, args.cookie_file)
    if not raw_cookie:
        print(
            "错误: 需要 cookie 才能获取抖音用户视频列表。\n"
            "获取方法:\n"
            "  方式 A(推荐):用 Cookie-Editor 扩展导出 JSON,保存到 cookies.txt\n"
            "  方式 B:F12 → Network → 复制 Cookie 字符串,用 --cookie 传入\n",
            file=sys.stderr,
        )
        return 1

    cookie_str = cookie_to_string(raw_cookie)
    fmt = "JSON" if raw_cookie.startswith("[") else "字符串"
    print(f"cookie 已加载 ({fmt} 格式, {len(cookie_str)} 字符)")

    # 逐个用户处理
    results = []
    for idx, user in enumerate(users, 1):
        result = await process_user(
            user, output_dir, cookie_str, args.max_videos_per_user, idx, total,
        )
        results.append(result)
        status = "✓ " + result["msg"] if result["ok"] else "✗ " + result["msg"]
        print(f"  -> {status}")

    # 汇总
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = total - ok_count
    total_videos = sum(r.get("video_count", 0) for r in results if r["ok"])
    total_success = sum(r.get("success_count", 0) for r in results if r["ok"])

    print("\n" + "=" * 60)
    print(f"下载完成: 成功 {ok_count}/{total} 个用户,失败 {fail_count}")
    print(f"视频总计: {total_videos} 个,MP3 成功: {total_success} 个")
    if fail_count:
        print("\n失败用户列表:")
        for r in results:
            if not r["ok"]:
                u = r["user"]
                print(f"  - [{u['seq']}] {u['nickname']} ({u['douyin_id']}): {r['msg']}")
    print("=" * 60)
    return 0 if fail_count == 0 else 2


def main():
    parser = argparse.ArgumentParser(
        description="抖音用户主页批量 MP3 下载器(f2 + httpx,无需 yt-dlp/ffmpeg)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览用户列表(不需要 cookie,使用默认表格)
  python3 douyin_mp3_downloader.py --dry-run

  # 试跑:前 2 个用户,每人最多 3 个视频
  python3 douyin_mp3_downloader.py --user-range 1-2 --max-videos-per-user 3

  # 全量下载(使用默认表格/cookie 文件)
  python3 douyin_mp3_downloader.py

  # 显式指定表格/cookie 文件
  python3 douyin_mp3_downloader.py users_table.txt --cookie-file cookies.txt
        """.strip(),
    )
    parser.add_argument("table_file", nargs="?", default=str(SCRIPT_DIR / "users_table.txt"),
                        help="抖音用户信息 markdown 表格文件路径(默认: 脚本所在目录下的 users_table.txt)")
    parser.add_argument("-o", "--output", default=None,
                        help="MP3 输出根目录(默认: 脚本所在目录下的 douyin_mp3_output)")
    parser.add_argument("--max-videos-per-user", type=int, default=0,
                        help="每个用户最多下载的视频数(0=全部)")
    parser.add_argument("--user-range", default=None,
                        help="只处理指定序号范围的用户,如 '1-5' 或 '3'")
    parser.add_argument("--cookie", default=None,
                        help="抖音 cookie 字符串(与 --cookie-file 二选一)")
    parser.add_argument("--cookie-file", default=str(SCRIPT_DIR / "cookies.txt"),
                        help="cookie 文件路径(默认: 脚本所在目录下的 cookies.txt;支持 JSON 数组格式或原始字符串格式)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析并显示将处理的用户列表,不下载")
    args = parser.parse_args()

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
