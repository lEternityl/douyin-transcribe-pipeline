"""转写服务 —— 从 local_segment_transcribe.py 迁入核心函数。

负责: ffmpeg 切段 → Whisper/MLX 转写 → 合并文本
"""
import logging
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".mp3", ".mp4", ".m4a", ".wav"}


def detect_device() -> str:
    """检测可用设备: cuda > mps > cpu"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def detect_backend(requested_backend: str = "auto") -> str:
    """自动检测转写后端: Apple Silicon 优先 MLX"""
    if requested_backend != "auto":
        return requested_backend
    if platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            pass
    return "openai-whisper"


def resolve_model_name(backend: str, requested_model: str = "base") -> str:
    """根据后端解析模型名"""
    if backend == "mlx":
        mapping = {
            "base": "mlx-community/whisper-base-mlx-8bit",
            "small": "mlx-community/whisper-small-mlx-8bit",
            "tiny": "mlx-community/whisper-tiny",
        }
        return mapping.get(requested_model, requested_model)
    return requested_model


def _run_ffmpeg(command: List[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


def segment_media(media_path: Path, segments_dir: Path, segment_seconds: int = 120) -> List[Path]:
    """用 ffmpeg 把音频切成 N 秒一段的 WAV(16kHz 单声道 PCM)"""
    segments_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(segments_dir / "segment_%04d.wav")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(media_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "segment", "-segment_time", str(segment_seconds),
        "-c:a", "pcm_s16le", pattern,
    ]
    _run_ffmpeg(command)
    segments = sorted(segments_dir.glob("segment_*.wav"))
    if not segments:
        raise RuntimeError("未生成任何音频片段")
    return segments


def transcribe_segments(
    backend: str,
    model,  # whisper.Whisper | None
    model_name: str,
    segments: List[Path],
    language: str = "zh",
) -> Tuple[str, List[dict]]:
    """逐段转写,返回 (合并文本, 段落详情列表)"""
    merged_parts: List[str] = []
    segment_results: List[dict] = []

    for index, segment_path in enumerate(segments, start=1):
        start = time.time()
        if backend == "mlx":
            import mlx_whisper
            result = mlx_whisper.transcribe(
                str(segment_path),
                path_or_hf_repo=model_name,
                language=language,
                verbose=False,
            )
        else:
            result = model.transcribe(
                str(segment_path),
                language=language,
                fp16=False,
                verbose=False,
                task="transcribe",
            )
        text = (result.get("text") or "").strip()
        elapsed = round(time.time() - start, 2)
        merged_parts.append(text)
        segment_results.append({
            "index": index,
            "segment_file": segment_path.name,
            "text": text,
            "elapsed_seconds": elapsed,
        })
        logger.info(f"  segment {index}/{len(segments)} done ({elapsed}s)")

    merged_text = "\n".join(p for p in merged_parts if p).strip()
    return merged_text, segment_results


def transcribe_file(
    media_path: Path,
    output_dir: Path,
    model_name: str = "base",
    backend: str = "auto",
    language: str = "zh",
    segment_seconds: int = 120,
    keep_segments: bool = False,
) -> dict:
    """转写单个音频文件,返回 {text, segment_results, elapsed}。

    输出:
      <output_dir>/<stem>.txt  —— 合并后的完整文本
      <output_dir>/<stem>.json —— 段落详情
    """
    backend = detect_backend(backend)
    resolved_model = resolve_model_name(backend, model_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 已存在则跳过
    txt_path = output_dir / f"{media_path.stem}.txt"
    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8").strip()
        if text:
            return {"text": text, "segment_results": [], "skipped": True}

    # 切段
    segments_dir = output_dir / "_segments" / media_path.stem
    if segments_dir.exists():
        shutil.rmtree(segments_dir)
    segments = segment_media(media_path, segments_dir, segment_seconds)

    # 加载模型(openai-whisper 后端需要)
    model = None
    if backend != "mlx":
        import whisper
        device = detect_device()
        logger.info(f"Loading Whisper model '{resolved_model}' on {device}...")
        model = whisper.load_model(resolved_model, device=device)

    # 转写
    merged_text, segment_results = transcribe_segments(
        backend, model, resolved_model, segments, language
    )

    # 写出
    txt_path.write_text(merged_text + ("\n" if merged_text else ""), encoding="utf-8")
    json_path = output_dir / f"{media_path.stem}.json"
    import json
    json_path.write_text(json.dumps(segment_results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 清理片段
    if not keep_segments:
        shutil.rmtree(segments_dir, ignore_errors=True)

    return {"text": merged_text, "segment_results": segment_results, "skipped": False}
