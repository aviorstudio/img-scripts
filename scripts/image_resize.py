#!/usr/bin/env python3
"""Resize an image to exactly 512x512 pixels."""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required: install img-scripts dependencies with `python -m pip install -e .`.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resize an image to exactly 512x512 pixels.")
    parser.add_argument("--verbose", action="store_true", help="Print the full input and output paths.")
    parser.add_argument("image_file", type=Path, help="Image to resize.")
    parser.add_argument("output_suffix", nargs="?", default="-512x512", help="Suffix before the file extension.")
    return parser.parse_args()


def output_path(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(f"{input_path.stem}{suffix}{input_path.suffix}")


def save_resized(input_path: Path, out_path: Path) -> None:
    with Image.open(input_path) as image:
        resized = image.resize((512, 512), Image.Resampling.LANCZOS)
        if out_path.suffix.lower() in {".jpg", ".jpeg"} and resized.mode in {"RGBA", "LA", "P"}:
            resized = resized.convert("RGB")
        resized.save(out_path)


def main() -> int:
    args = parse_args()
    input_path = args.image_file.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Error: File '{args.image_file}' not found")

    out_path = output_path(input_path, args.output_suffix)
    save_resized(input_path, out_path)
    if args.verbose:
        print(f"Resized: {input_path} -> {out_path}")
    else:
        print("Image resized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
