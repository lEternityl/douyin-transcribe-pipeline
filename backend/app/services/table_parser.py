"""表格解析 —— 从 douyin_mp3_downloader.py 迁入,原样复用。"""
import html
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def clean_url(url: str) -> str:
    """剥离 URL 中的追踪参数,只保留 scheme+host+path。"""
    url = html.unescape(url).strip()
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def extract_sec_user_id(url: str) -> str:
    """从用户主页 URL 中提取 sec_user_id。"""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "user":
        return parts[1]
    return ""


def parse_users_table(table_text: str) -> list[dict]:
    """解析 markdown 表格文本,提取用户信息。
    表格列: | 序号 | 昵称 | 抖音号 | 获赞 | 粉丝 | 主页链接 |
    """
    users: list[dict] = []
    for line in table_text.splitlines():
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
        url = clean_url(parts[5])
        if "douyin.com/user/" not in url:
            continue
        users.append({
            "seq": seq,
            "nickname": parts[1],
            "douyin_id": parts[2],
            "likes": parts[3],
            "followers": parts[4],
            "url": url,
            "sec_user_id": extract_sec_user_id(url),
        })
    return users


def parse_users_table_file(table_file: Path) -> list[dict]:
    return parse_users_table(table_file.read_text(encoding="utf-8"))
