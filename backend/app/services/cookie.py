"""Cookie 处理 —— 从 douyin_mp3_downloader.py 迁入,原样复用。"""
import json
import sys
from pathlib import Path

from app.config import settings


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


def cookie_to_string(raw: str) -> str:
    """将原始 cookie(JSON 数组或字符串)转为字符串格式。"""
    if not raw:
        return ""
    if raw.startswith("["):
        try:
            return json_cookies_to_string(raw)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"警告: JSON cookie 解析失败,退回原始字符串: {e}", file=sys.stderr)
            return raw
    return raw


def load_cookie_string() -> str:
    """从配置的 cookie 文件加载并转为字符串;不存在返回空。"""
    p = settings.cookie_file
    if not p.exists():
        return ""
    raw = p.read_text(encoding="utf-8").strip()
    return cookie_to_string(raw)


def save_cookie(content: str) -> str:
    """保存 cookie 原文到文件,返回归一化后的字符串。"""
    settings.cookie_file.parent.mkdir(parents=True, exist_ok=True)
    settings.cookie_file.write_text(content.strip(), encoding="utf-8")
    return cookie_to_string(content.strip())


def cookie_status() -> dict:
    """返回 cookie 当前状态。"""
    p = settings.cookie_file
    if not p.exists():
        return {"loaded": False, "format": "", "length": 0, "preview": ""}
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return {"loaded": False, "format": "", "length": 0, "preview": ""}
    fmt = "JSON" if raw.startswith("[") else "字符串"
    s = cookie_to_string(raw)
    return {
        "loaded": True,
        "format": fmt,
        "length": len(s),
        "preview": s[:60] + ("..." if len(s) > 60 else ""),
    }
