#!/usr/bin/env python3
"""
本地媒体文件切段 + 转写 + 合并文本。

工作流(与 douyin_mp3_downloader.py / merge_texts.py 串联):
  # 1. 先下载某用户的 MP3(见 douyin_mp3_downloader.py)
  #    产生: 脚本/douyin_mp3_output/<user_dir>/*.mp3

  # 2. 转写该用户文件夹(传 user_dir 即可,input/output 自动指向该文件夹)
  python3 local_segment_transcribe.py douyin_mp3_output/001_高源性格心理学_gaoyuan2049
  # 读取: <user_dir>/*.mp3 等媒体文件
  # 产生: <user_dir>/texts_local/*.txt + *.json + summary.txt + _segments/ + _segment_texts/

  # 3. 合并该用户文件夹(见 merge_texts.py)
  #    读取: <user_dir>/texts_local/*.txt
  #    产生: <user_dir>/all_texts_merged.txt

user_dir 解析规则:
  - 相对路径按脚本所在目录(脚本/)解析;绝对路径直接使用。
  - 不传 user_dir 时: input 默认为脚本目录, output 默认为脚本目录/texts_local。
  - 传 user_dir 时:   input 默认为 <user_dir>,    output 默认为 <user_dir>/texts_local。
  - 可用 --input-dir / --output-dir 显式覆盖默认值。
"""
import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import torch
import whisper

try:
    import mlx_whisper
except Exception:  # noqa: BLE001
    mlx_whisper = None


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_EXTS = {".mp3", ".mp4", ".m4a", ".wav"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Segment local media files, transcribe each segment, and merge the text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "user_dir",
        nargs="?",
        default=None,
        help="用户文件夹路径(相对路径按脚本目录解析)。传了之后 input 默认=<user_dir>, "
             "output 默认=<user_dir>/texts_local,方便和下载/合并脚本串联。不传则用脚本目录。",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="媒体文件目录(默认: user_dir 或脚本目录;可用此项覆盖)。",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录(默认: <user_dir>/texts_local 或 脚本目录/texts_local;可用此项覆盖)。",
    )
    parser.add_argument("--model", default="base", help="Whisper model name, e.g. tiny/base/small.")
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "mlx", "openai-whisper"],
        help="Transcription backend. auto prefers MLX on Apple Silicon when available.",
    )
    parser.add_argument("--language", default="zh", help="Language code passed to Whisper.")
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda", "mps", "auto"],
        help="Execution device. Default uses cpu for better compatibility on macOS.",
    )
    parser.add_argument("--segment-seconds", type=int, default=120, help="Length of each segment in seconds.")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N files. 0 means no limit.")
    parser.add_argument("--force", action="store_true", help="Rebuild outputs even if text already exists.")
    parser.add_argument(
        "--keep-segments",
        action="store_true",
        help="Keep generated segment audio files. By default they are removed after each file completes.",
    )
    return parser.parse_args()


def detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def detect_backend(requested_backend: str) -> str:
    if requested_backend != "auto":
        return requested_backend
    if platform.machine() == "arm64" and mlx_whisper is not None:
        return "mlx"
    return "openai-whisper"


def resolve_model_name(backend: str, requested_model: str) -> str:
    if backend == "mlx":
        if requested_model == "base":
            return "mlx-community/whisper-base-mlx-8bit"
        if requested_model == "small":
            return "mlx-community/whisper-small-mlx-8bit"
        if requested_model == "tiny":
            return "mlx-community/whisper-tiny"
        return requested_model
    return requested_model


def iter_media_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            yield path


def run_ffmpeg(command: List[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg failed")


def segment_media(media_path: Path, segments_dir: Path, segment_seconds: int) -> List[Path]:
    segments_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(segments_dir / "segment_%04d.wav")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-c:a",
        "pcm_s16le",
        pattern,
    ]
    run_ffmpeg(command)
    segments = sorted(segments_dir.glob("segment_*.wav"))
    if not segments:
        raise RuntimeError("No audio segments were generated.")
    return segments


def safe_stem(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\n\r\t%]', "_", name)
    sanitized = sanitized.strip().strip(".")
    return sanitized or "unnamed"


def transcribe_segments(
    backend: str,
    model: Optional[whisper.Whisper],
    model_name: str,
    segments: List[Path],
    language: str,
    segments_txt_dir: Path,
) -> Tuple[str, List[dict]]:
    segments_txt_dir.mkdir(parents=True, exist_ok=True)
    merged_parts: List[str] = []
    segment_results: List[dict] = []

    for index, segment_path in enumerate(segments, start=1):
        start = time.time()
        if backend == "mlx":
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
        item = {
            "index": index,
            "segment_file": segment_path.name,
            "text": text,
            "elapsed_seconds": elapsed,
        }
        segment_results.append(item)
        (segments_txt_dir / f"{segment_path.stem}.txt").write_text(
            text + ("\n" if text else ""),
            encoding="utf-8",
        )
        print(f"    segment {index}/{len(segments)} done: {segment_path.name} ({elapsed}s)", flush=True)

    merged_text = "\n".join(part for part in merged_parts if part).strip()
    return merged_text, segment_results


def write_outputs(
    output_dir: Path,
    media_path: Path,
    merged_text: str,
    segment_results: List[dict],
) -> None:
    stem = media_path.stem
    txt_path = output_dir / f"{stem}.txt"
    json_path = output_dir / f"{stem}.json"
    txt_path.write_text(merged_text + ("\n" if merged_text else ""), encoding="utf-8")
    json_path.write_text(json.dumps(segment_results, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_user_dir(user_dir_arg: Optional[str]) -> Path:
    """user_dir 为相对路径时按脚本目录解析;为绝对路径直接使用;为 None 时返回脚本目录。"""
    if not user_dir_arg:
        return SCRIPT_DIR
    p = Path(user_dir_arg).expanduser()
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    return p.resolve()


def main() -> int:
    args = parse_args()
    user_dir = resolve_user_dir(args.user_dir)
    input_dir = Path(args.input_dir).expanduser().resolve() if args.input_dir else user_dir
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else user_dir / "texts_local"
    )
    # 传了 user_dir 时检查存在性(拼错文件夹名时给清晰报错,而不是静默创建空目录)
    if args.user_dir and not user_dir.exists():
        print(f"错误: 用户文件夹不存在: {user_dir}", file=sys.stderr)
        return 1
    if not input_dir.exists():
        print(f"错误: input-dir 不存在: {input_dir}", file=sys.stderr)
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"user_dir:   {user_dir}")
    print(f"input_dir:  {input_dir}")
    print(f"output_dir: {output_dir}")

    media_files = list(iter_media_files(input_dir))
    if args.limit > 0:
        media_files = media_files[: args.limit]
    if not media_files:
        print("No supported media files found.", file=sys.stderr)
        return 1

    backend = detect_backend(args.backend)
    model_name = resolve_model_name(backend, args.model)
    device = detect_device() if args.device == "auto" else args.device

    model: Optional[whisper.Whisper] = None
    if backend == "mlx":
        print(f"Using MLX Whisper model '{model_name}'...", flush=True)
    else:
        print(f"Loading Whisper model '{model_name}' on {device}...", flush=True)
        model = whisper.load_model(model_name, device=device)

    success = 0
    failed = 0
    failures: List[Tuple[str, str]] = []

    segments_root = output_dir / "_segments"
    transcripts_root = output_dir / "_segment_texts"
    segments_root.mkdir(parents=True, exist_ok=True)
    transcripts_root.mkdir(parents=True, exist_ok=True)

    for index, media_path in enumerate(media_files, start=1):
        txt_path = output_dir / f"{media_path.stem}.txt"
        if txt_path.exists() and not args.force:
            print(f"[{index}/{len(media_files)}] skip existing: {media_path.name}", flush=True)
            continue

        print(f"[{index}/{len(media_files)}] processing: {media_path.name}", flush=True)
        stem_key = safe_stem(media_path.stem)
        media_segments_dir = segments_root / stem_key
        media_segment_text_dir = transcripts_root / stem_key

        try:
            if media_segments_dir.exists():
                shutil.rmtree(media_segments_dir)
            if media_segment_text_dir.exists():
                shutil.rmtree(media_segment_text_dir)

            segments = segment_media(media_path, media_segments_dir, args.segment_seconds)
            print(f"    generated {len(segments)} segments", flush=True)
            merged_text, segment_results = transcribe_segments(
                backend,
                model,
                model_name,
                segments,
                args.language,
                media_segment_text_dir,
            )
            write_outputs(output_dir, media_path, merged_text, segment_results)

            if not args.keep_segments:
                shutil.rmtree(media_segments_dir, ignore_errors=True)

            success += 1
            print(f"    merged text length: {len(merged_text)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            failures.append((media_path.name, str(exc)))
            print(f"    failed: {exc}", flush=True)

    summary_lines = [
        "本地切段转写结果汇总",
        f"成功: {success}, 失败: {failed}, 总计: {len(media_files)}",
        f"后端: {backend}, 模型: {model_name}, 语言: {args.language}, 分段秒数: {args.segment_seconds}, 设备: {device}",
        "=" * 60,
    ]
    if failures:
        summary_lines.append("失败详情:")
        for name, message in failures:
            summary_lines.append(f"- {name}: {message}")
    else:
        summary_lines.append("全部处理成功。")

    (output_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
