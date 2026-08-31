#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并指定用户文件夹下 texts_local/ 中的全部 txt 文件。

用法:
  # 合并 脚本目录下某个用户子文件夹(常用)
  python3 merge_texts.py 001_高源性格心理学_gaoyuan2049

  # 也可以传绝对路径
  python3 merge_texts.py /path/to/user_dir

  # 自定义输出文件名(默认 all_texts_merged.txt)
  python3 merge_texts.py 001_高源性格心理学_gaoyuan2049 --output merged.txt

路径解析规则:
  - user_dir 若为相对路径,按脚本所在目录(脚本/)解析;若为绝对路径,直接使用。
  - 默认读取 <user_dir>/texts_local/*.txt,输出到 <user_dir>/<output_name>。
"""

import argparse
import sys
from glob import glob
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_user_dir(user_dir_arg: str) -> Path:
    """user_dir 为相对路径时,按脚本目录解析;为绝对路径时直接使用。"""
    p = Path(user_dir_arg).expanduser()
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    return p.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="合并用户文件夹下 texts_local/ 中的全部 txt 文件。"
    )
    parser.add_argument(
        "user_dir",
        help="用户文件夹路径(相对路径按脚本目录解析,也可用绝对路径)。",
    )
    parser.add_argument(
        "--texts-subdir",
        default="texts_local",
        help="存放 txt 文件的子目录名(默认: texts_local)。",
    )
    parser.add_argument(
        "--output",
        default="all_texts_merged.txt",
        help="合并后的输出文件名(默认: all_texts_merged.txt),写在 user_dir 下。",
    )
    args = parser.parse_args()

    user_dir = resolve_user_dir(args.user_dir)
    if not user_dir.exists() or not user_dir.is_dir():
        print(f"错误: 用户文件夹不存在或不是目录: {user_dir}", file=sys.stderr)
        return 1

    texts_dir = user_dir / args.texts_subdir
    output_file = user_dir / args.output

    # 收集 texts_subdir 下直接的 txt 文件(排除子目录)
    txt_files = sorted(glob(str(texts_dir / "*.txt")))

    print(f"用户文件夹: {user_dir}")
    print(f"文本目录:   {texts_dir}")
    print(f"找到 {len(txt_files)} 个 txt 文件")

    if not txt_files:
        print(f"警告: 未在 {texts_dir} 下找到任何 txt 文件", file=sys.stderr)
        return 1

    with open(output_file, "w", encoding="utf-8") as out:
        for filepath in txt_files:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            out.write(content)
            out.write("\n\n")

    print(f"已合并到: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
