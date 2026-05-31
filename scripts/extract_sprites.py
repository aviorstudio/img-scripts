#!/usr/bin/env python3
"""Extract individual sprites from a sheet by detecting transparent gaps."""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required: install img-scripts dependencies with `python -m pip install -e .`.") from exc

BoundingBox = tuple[int, int, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a sprite sheet into individual PNGs by finding opaque regions separated by transparency.",
    )
    parser.add_argument("input", type=Path, help="Path to the sprite sheet.")
    parser.add_argument("output", type=Path, help="Directory to write the extracted sprites.")
    parser.add_argument("--prefix", default="sprite", help="Filename prefix for generated PNGs.")
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=8,
        help="Minimum alpha value treated as opaque.",
    )
    parser.add_argument("--padding", type=int, default=0, help="Pixels of padding around each sprite.")
    parser.add_argument("--min-area", type=int, default=64, help="Ignore blobs smaller than this many pixels.")
    parser.add_argument(
        "--connectivity",
        type=int,
        choices=(4, 8),
        default=8,
        help="Adjacency rule for grouping pixels.",
    )
    parser.add_argument(
        "--grid",
        default="",
        help="Optional grid spec like 4x3. Sorts components by row band then x.",
    )
    return parser.parse_args()


def neighbors(connectivity: int) -> Iterable[tuple[int, int]]:
    base = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        base.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])
    return base


def find_components(img: Image.Image, alpha_threshold: int, connectivity: int, min_area: int) -> list[BoundingBox]:
    width, height = img.size
    pixels = img.load()
    visited = bytearray(width * height)
    offsets = list(neighbors(connectivity))
    components: list[BoundingBox] = []

    def idx(x: int, y: int) -> int:
        return y * width + x

    for y in range(height):
        for x in range(width):
            start = idx(x, y)
            if visited[start]:
                continue
            if pixels[x, y][3] <= alpha_threshold:
                visited[start] = 1
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[start] = 1
            min_x = max_x = x
            min_y = max_y = y
            area = 0

            while queue:
                cx, cy = queue.popleft()
                area += 1

                for dx, dy in offsets:
                    nx, ny = cx + dx, cy + dy
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    next_index = idx(nx, ny)
                    if visited[next_index]:
                        continue
                    if pixels[nx, ny][3] <= alpha_threshold:
                        visited[next_index] = 1
                        continue

                    visited[next_index] = 1
                    queue.append((nx, ny))
                    min_x = min(min_x, nx)
                    min_y = min(min_y, ny)
                    max_x = max(max_x, nx)
                    max_y = max(max_y, ny)

            if area >= min_area:
                components.append((min_x, min_y, max_x, max_y))

    return components


def parse_grid(raw: str) -> tuple[int, int] | None:
    if not raw:
        return None
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise SystemExit("--grid must be formatted like 4x3")
    cols, rows = int(parts[0]), int(parts[1])
    if cols <= 0 or rows <= 0:
        raise SystemExit("--grid dimensions must be positive")
    return cols, rows


def sorted_bboxes(bboxes: list[BoundingBox], image_height: int, grid: tuple[int, int] | None) -> list[BoundingBox]:
    if grid is None:
        return sorted(bboxes, key=lambda box: (box[1], box[0]))

    _cols, rows = grid
    row_height = image_height / rows

    def key(box: BoundingBox) -> tuple[int, float]:
        center_y = (box[1] + box[3]) / 2.0
        center_x = (box[0] + box[2]) / 2.0
        row = min(rows - 1, int(center_y // row_height))
        return row, center_x

    return sorted(bboxes, key=key)


def save_components(
    img: Image.Image,
    bboxes: list[BoundingBox],
    output_dir: Path,
    prefix: str,
    padding: int,
    grid: tuple[int, int] | None,
) -> None:
    width, height = img.size
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        display_path = output_dir.relative_to(Path.cwd())
    except ValueError:
        display_path = output_dir

    for index, bbox in enumerate(sorted_bboxes(bboxes, height, grid)):
        min_x, min_y, max_x, max_y = bbox
        left = max(0, min_x - padding)
        top = max(0, min_y - padding)
        right = min(width, max_x + padding + 1)
        bottom = min(height, max_y + padding + 1)

        sprite = img.crop((left, top, right, bottom))
        sprite.save(output_dir / f"{prefix}_{index:02d}.png")

    print(f"Wrote {len(bboxes)} sprites to {display_path}")


def extract(input_path: Path, output_dir: Path, **options: object) -> None:
    input_path = input_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()

    if not input_path.exists():
        raise SystemExit(f"Sprite sheet not found: {input_path}")

    with Image.open(input_path) as img:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        bboxes = find_components(
            img,
            alpha_threshold=int(options["alpha_threshold"]),
            connectivity=int(options["connectivity"]),
            min_area=int(options["min_area"]),
        )
        if not bboxes:
            raise SystemExit("No sprites found; check the alpha threshold or input image.")
        save_components(
            img,
            bboxes,
            output_dir,
            str(options["prefix"]),
            int(options["padding"]),
            parse_grid(str(options["grid"])),
        )


def main() -> None:
    args = parse_args()
    extract(
        args.input,
        args.output,
        prefix=args.prefix,
        alpha_threshold=args.alpha_threshold,
        padding=args.padding,
        min_area=args.min_area,
        connectivity=args.connectivity,
        grid=args.grid,
    )


if __name__ == "__main__":
    main()
