#!/usr/bin/env python3
"""Cut transparent sprite sheets into tightly cropped asset PNGs.

The cutter treats every non-transparent pixel as source art, expands the alpha
mask by a configurable grouping radius, finds connected islands, then crops each
island back to the tight bounds of the original alpha pixels.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageFilter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut a transparent sprite sheet into individual PNG assets.",
    )
    parser.add_argument("--input", required=True, type=Path, help="RGBA sprite sheet PNG.")
    parser.add_argument("--out-dir", required=True, type=Path, help="Directory for cut PNGs.")
    parser.add_argument("--prefix", default="", help="Filename prefix for generated assets.")
    parser.add_argument("--padding", type=int, default=4, help="Transparent padding around each crop.")
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=8,
        help="Minimum alpha value considered part of an asset.",
    )
    parser.add_argument(
        "--group-radius",
        type=int,
        default=24,
        help="Pixels to dilate alpha before connected-component grouping.",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=64,
        help="Minimum original alpha-pixel area for a saved asset.",
    )
    parser.add_argument(
        "--names",
        default="",
        help="Optional comma-separated output names in top-to-bottom, left-to-right order.",
    )
    parser.add_argument("--grid-cols", type=int, default=0, help="Optional fixed grid column count.")
    parser.add_argument("--grid-rows", type=int, default=0, help="Optional fixed grid row count.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional manifest JSON path. Defaults to <out-dir>/manifest.json.",
    )
    return parser.parse_args()


def threshold_alpha(image: Image.Image, alpha_threshold: int) -> Image.Image:
    alpha = image.getchannel("A")
    return alpha.point(lambda value: 255 if value >= alpha_threshold else 0, mode="1")


def dilate(mask: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return mask.convert("L")
    kernel_size = radius * 2 + 1
    return mask.convert("L").filter(ImageFilter.MaxFilter(kernel_size))


def connected_components(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    width, height = mask.size
    pixels = mask.load()
    visited = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []

    def offset(x: int, y: int) -> int:
        return y * width + x

    for y in range(height):
        for x in range(width):
            start_offset = offset(x, y)
            if visited[start_offset] or pixels[x, y] == 0:
                continue

            min_x = max_x = x
            min_y = max_y = y
            visited[start_offset] = 1
            queue: deque[tuple[int, int]] = deque([(x, y)])

            while queue:
                cx, cy = queue.popleft()
                if cx < min_x:
                    min_x = cx
                elif cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                elif cy > max_y:
                    max_y = cy

                for ny in range(max(0, cy - 1), min(height, cy + 2)):
                    for nx in range(max(0, cx - 1), min(width, cx + 2)):
                        next_offset = offset(nx, ny)
                        if visited[next_offset] or pixels[nx, ny] == 0:
                            continue
                        visited[next_offset] = 1
                        queue.append((nx, ny))

            boxes.append((min_x, min_y, max_x + 1, max_y + 1))

    return boxes


def tight_original_box(
    original_mask: Image.Image,
    search_box: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int] | None, int]:
    crop = original_mask.crop(search_box).convert("L")
    bbox = crop.getbbox()
    if bbox is None:
        return None, 0

    alpha_area = sum(crop.histogram()[1:])
    left, top, right, bottom = bbox
    search_left, search_top, _, _ = search_box
    return (
        search_left + left,
        search_top + top,
        search_left + right,
        search_top + bottom,
    ), alpha_area


def padded_box(
    box: tuple[int, int, int, int],
    padding: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def sort_boxes_reading_order(
    boxes: Iterable[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    sorted_boxes = sorted(boxes, key=lambda box: (box[1], box[0]))
    if not sorted_boxes:
        return []

    heights = sorted((box[3] - box[1]) for box in sorted_boxes)
    median_height = heights[len(heights) // 2]
    row_tolerance = max(24, median_height // 2)
    rows: list[list[tuple[int, int, int, int]]] = []

    for box in sorted_boxes:
        center_y = (box[1] + box[3]) // 2
        for row in rows:
            row_center = sum((item[1] + item[3]) // 2 for item in row) // len(row)
            if abs(center_y - row_center) <= row_tolerance:
                row.append(box)
                break
        else:
            rows.append([box])

    ordered: list[tuple[int, int, int, int]] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda box: box[0]))
    return ordered


def grid_boxes(width: int, height: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            left: int = int(round(float(col) * float(width) / float(cols)))
            top: int = int(round(float(row) * float(height) / float(rows)))
            right: int = int(round(float(col + 1) * float(width) / float(cols)))
            bottom: int = int(round(float(row + 1) * float(height) / float(rows)))
            boxes.append((left, top, right, bottom))
    return boxes


def safe_name(raw: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in raw.strip())
    return "_".join(part for part in cleaned.split("_") if part)


def main() -> int:
    args = parse_args()
    source = Image.open(args.input).convert("RGBA")
    width, height = source.size
    original_mask = threshold_alpha(source, args.alpha_threshold).convert("L")
    asset_boxes: list[tuple[tuple[int, int, int, int], int]] = []
    source_boxes: list[tuple[int, int, int, int]]
    use_grid: bool = args.grid_cols > 0 or args.grid_rows > 0
    if use_grid:
        if args.grid_cols <= 0 or args.grid_rows <= 0:
            raise ValueError("--grid-cols and --grid-rows must be used together")
        source_boxes = grid_boxes(width, height, args.grid_cols, args.grid_rows)
    else:
        grouped_mask = dilate(original_mask, args.group_radius)
        source_boxes = connected_components(grouped_mask)

    for grouped_box in source_boxes:
        original_box, alpha_area = tight_original_box(original_mask, grouped_box)
        if original_box is None or alpha_area < args.min_area:
            continue
        asset_boxes.append((original_box, alpha_area))

    ordered = [box for box, _area in asset_boxes] if use_grid else sort_boxes_reading_order(box for box, _area in asset_boxes)
    area_by_box = {box: area for box, area in asset_boxes}
    requested_names = [safe_name(name) for name in args.names.split(",") if safe_name(name)]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest if args.manifest is not None else args.out_dir / "manifest.json"
    prefix = safe_name(args.prefix)
    manifest = {
        "source": str(args.input),
        "source_size": [width, height],
        "alpha_threshold": args.alpha_threshold,
        "group_radius": args.group_radius,
        "padding": args.padding,
        "assets": [],
    }

    for index, box in enumerate(ordered, start=1):
        name = requested_names[index - 1] if index <= len(requested_names) else f"{prefix}_{index:03d}"
        if not name:
            name = f"asset_{index:03d}"
        padded = padded_box(box, args.padding, width, height)
        output_name = f"{name}.png"
        output_path = args.out_dir / output_name
        source.crop(padded).save(output_path)
        manifest["assets"].append(
            {
                "name": name,
                "file": output_name,
                "box": list(box),
                "padded_box": list(padded),
                "size": [padded[2] - padded[0], padded[3] - padded[1]],
                "alpha_area": area_by_box.get(box, 0),
            }
        )

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(ordered)} assets to {args.out_dir}")
    print(f"Wrote manifest to {manifest_path}")
    if requested_names and len(requested_names) != len(ordered):
        print(f"Warning: got {len(requested_names)} names for {len(ordered)} detected assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
