#!/usr/bin/env python3
"""Cut sprite sheets into individual PNG assets."""
from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


AUTO_THRESHOLDS = (8, 12, 16, 24, 32, 48, 64, 96, 128)
AUTO_MAX_COMPONENT_RATIO = 0.35
AUTO_MIN_COMPONENTS = 2
Image = None
ImageFilter = None


@dataclass(frozen=True)
class Component:
    box: tuple[int, int, int, int]
    alpha_area: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cut sprite sheets into tightly cropped PNG assets.")
    parser.add_argument("inputs", nargs="*", type=Path, help="Input sprite sheet PNGs.")
    parser.add_argument("--input", action="append", type=Path, default=[], help="Additional input sprite sheet PNG.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project repository root for default inputs and relative output paths.",
    )
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for a single input.")
    parser.add_argument("--output-root", type=Path, default=None, help="Root directory for per-sheet output folders.")
    parser.add_argument(
        "--default-inputs-glob",
        default="godot_client/src/assets/sheets/*transparent.png",
        help="Project-root-relative glob used when no inputs are provided.",
    )
    parser.add_argument("--prefix", default="sprite", help="Filename prefix when --names is omitted.")
    parser.add_argument("--names", default="", help="Optional comma-separated output names in output order.")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional manifest JSON path for a single input.")
    parser.add_argument(
        "--alpha-threshold",
        default="8",
        help="Minimum alpha treated as foreground, or 'auto' to choose a threshold.",
    )
    parser.add_argument(
        "--background",
        choices=("auto", "alpha", "corner", "color"),
        default="auto",
        help="How to decide which pixels are background.",
    )
    parser.add_argument("--background-color", default="", help="RGB background key as R,G,B or #RRGGBB.")
    parser.add_argument(
        "--background-tolerance",
        type=int,
        default=80,
        help="Maximum RGB distance from the background key treated as transparent.",
    )
    parser.add_argument("--min-area", "--min-pixels", dest="min_area", type=int, default=64)
    parser.add_argument("--padding", type=int, default=0, help="Transparent padding around each crop.")
    parser.add_argument(
        "--group-radius",
        type=int,
        default=0,
        help="Pixels to dilate the mask before connected-component grouping.",
    )
    parser.add_argument(
        "--merge-distance",
        "--merge-gap",
        dest="merge_distance",
        type=int,
        default=0,
        help="Merge detected components whose boxes are within this many pixels.",
    )
    parser.add_argument("--connectivity", type=int, choices=(4, 8), default=8)
    parser.add_argument("--grid", default="", help="Optional grid spec like 4x3.")
    parser.add_argument("--grid-cols", type=int, default=0, help="Optional fixed sheet column count.")
    parser.add_argument("--grid-rows", type=int, default=0, help="Optional fixed sheet row count.")
    parser.add_argument(
        "--grid-expand",
        type=int,
        default=0,
        help="Expand grid cell search boxes by this many pixels before cropping foreground.",
    )
    parser.add_argument(
        "--sort",
        choices=("reading", "x", "y", "area"),
        default="reading",
        help="Output order for detected components.",
    )
    parser.add_argument(
        "--crop-mode",
        choices=("tight", "square"),
        default="tight",
        help="Save tight crops or centered square transparent crops.",
    )
    return parser.parse_args()


def load_pillow() -> None:
    global Image, ImageFilter
    try:
        from PIL import Image as pillow_image
        from PIL import ImageFilter as pillow_image_filter
    except ImportError as exc:
        raise SystemExit("Pillow is required: install img-scripts dependencies with `python -m pip install -e .`.") from exc
    Image = pillow_image
    ImageFilter = pillow_image_filter


def parse_threshold(value: str) -> str | int:
    if value == "auto":
        return value
    try:
        threshold = int(value)
    except ValueError as exc:
        raise SystemExit("--alpha-threshold must be an integer or 'auto'.") from exc
    if threshold < 0 or threshold > 255:
        raise SystemExit("--alpha-threshold must be between 0 and 255.")
    return threshold


def parse_rgb(raw: str) -> tuple[int, int, int]:
    value = raw.strip()
    if value.startswith("#") and len(value) == 7:
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise SystemExit("--background-color must be R,G,B or #RRGGBB")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def parse_grid(args: argparse.Namespace) -> tuple[int, int] | None:
    cols = args.grid_cols
    rows = args.grid_rows
    if args.grid:
        parts = args.grid.lower().split("x")
        if len(parts) != 2:
            raise SystemExit("--grid must be formatted like 4x3")
        cols, rows = int(parts[0]), int(parts[1])
    if cols == 0 and rows == 0:
        return None
    if cols <= 0 or rows <= 0:
        raise SystemExit("--grid-cols and --grid-rows must be positive and used together")
    return cols, rows


def safe_name(raw: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in raw.strip())
    return "_".join(part for part in cleaned.split("_") if part)


def rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]), abs(left[2] - right[2]))


def corner_background_color(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    corners = (
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    )
    return (
        sum(pixel[0] for pixel in corners) // len(corners),
        sum(pixel[1] for pixel in corners) // len(corners),
        sum(pixel[2] for pixel in corners) // len(corners),
    )


def foreground_mask_and_source(
    image: Image.Image,
    background_mode: str,
    background_color: str,
    background_tolerance: int,
    alpha_threshold: int,
) -> tuple[Image.Image, Image.Image, str, tuple[int, int, int] | None]:
    width, height = image.size
    source = image.copy()
    source_pixels = source.load()
    mask = Image.new("L", source.size, 0)
    mask_pixels = mask.load()
    mode = background_mode
    key: tuple[int, int, int] | None = None

    if mode == "auto":
        alpha = image.getchannel("A")
        mode = "alpha" if alpha.getextrema()[0] < 255 else "corner"
    if mode == "color":
        key = parse_rgb(background_color)
    elif mode == "corner":
        key = corner_background_color(image)

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = source_pixels[x, y]
            foreground = alpha >= alpha_threshold
            if key is not None:
                foreground = foreground and rgb_distance((red, green, blue), key) > background_tolerance
            if foreground:
                mask_pixels[x, y] = 255
            else:
                source_pixels[x, y] = (red, green, blue, 0)

    return mask, source, mode, key


def neighbor_offsets(connectivity: int) -> tuple[tuple[int, int], ...]:
    offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
    if connectivity == 4:
        return offsets
    return offsets + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def find_components(mask: Image.Image, connectivity: int) -> list[Component]:
    width, height = mask.size
    pixels = mask.load()
    visited = bytearray(width * height)
    offsets = neighbor_offsets(connectivity)
    components: list[Component] = []

    def index(x: int, y: int) -> int:
        return y * width + x

    for y in range(height):
        for x in range(width):
            start_index = index(x, y)
            if visited[start_index] or pixels[x, y] == 0:
                continue

            min_x = max_x = x
            min_y = max_y = y
            alpha_area = 0
            visited[start_index] = 1
            queue: deque[tuple[int, int]] = deque([(x, y)])

            while queue:
                cx, cy = queue.popleft()
                alpha_area += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)

                for dx, dy in offsets:
                    nx = cx + dx
                    ny = cy + dy
                    if nx < 0 or nx >= width or ny < 0 or ny >= height:
                        continue
                    next_index = index(nx, ny)
                    if visited[next_index] or pixels[nx, ny] == 0:
                        continue
                    visited[next_index] = 1
                    queue.append((nx, ny))

            components.append(Component((min_x, min_y, max_x + 1, max_y + 1), alpha_area))

    return components


def dilate(mask: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return mask
    return mask.filter(ImageFilter.MaxFilter(radius * 2 + 1))


def tight_mask_box(mask: Image.Image, search_box: tuple[int, int, int, int]) -> Component | None:
    crop = mask.crop(search_box).convert("L")
    bbox = crop.getbbox()
    if bbox is None:
        return None
    alpha_area = sum(crop.histogram()[1:])
    left, top, right, bottom = bbox
    search_left, search_top, _, _ = search_box
    return Component((search_left + left, search_top + top, search_left + right, search_top + bottom), alpha_area)


def expanded_box(box: tuple[int, int, int, int], amount: int, width: int, height: int) -> tuple[int, int, int, int]:
    if amount <= 0:
        return box
    left, top, right, bottom = box
    return (max(0, left - amount), max(0, top - amount), min(width, right + amount), min(height, bottom + amount))


def grid_boxes(width: int, height: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            left = int(round(float(col) * float(width) / float(cols)))
            top = int(round(float(row) * float(height) / float(rows)))
            right = int(round(float(col + 1) * float(width) / float(cols)))
            bottom = int(round(float(row + 1) * float(height) / float(rows)))
            boxes.append((left, top, right, bottom))
    return boxes


def box_intersection_area(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> int:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def boxes_within_distance(left: tuple[int, int, int, int], right: tuple[int, int, int, int], distance: int) -> bool:
    return not (
        left[2] + distance < right[0]
        or right[2] + distance < left[0]
        or left[3] + distance < right[1]
        or right[3] + distance < left[1]
    )


def merge_components(components: list[Component], distance: int) -> list[Component]:
    if distance <= 0 or len(components) <= 1:
        return components

    remaining = components[:]
    changed = True
    while changed:
        changed = False
        merged: list[Component] = []
        while remaining:
            current = remaining.pop()
            consumed = True
            while consumed:
                consumed = False
                for index in range(len(remaining) - 1, -1, -1):
                    other = remaining[index]
                    if boxes_within_distance(current.box, other.box, distance):
                        current = Component(
                            (
                                min(current.box[0], other.box[0]),
                                min(current.box[1], other.box[1]),
                                max(current.box[2], other.box[2]),
                                max(current.box[3], other.box[3]),
                            ),
                            current.alpha_area + other.alpha_area,
                        )
                        remaining.pop(index)
                        changed = True
                        consumed = True
            merged.append(current)
        remaining = merged
    return remaining


def sort_components(components: Iterable[Component], sort_mode: str) -> list[Component]:
    items = list(components)
    if sort_mode == "x":
        return sorted(items, key=lambda component: (component.box[0], component.box[1]))
    if sort_mode == "y":
        return sorted(items, key=lambda component: (component.box[1], component.box[0]))
    if sort_mode == "area":
        return sorted(items, key=lambda component: component.alpha_area, reverse=True)
    return sort_components_reading_order(items)


def sort_components_reading_order(components: list[Component]) -> list[Component]:
    sorted_items = sorted(components, key=lambda component: (component.box[1], component.box[0]))
    if not sorted_items:
        return []

    heights = sorted(component.box[3] - component.box[1] for component in sorted_items)
    median_height = heights[len(heights) // 2]
    row_tolerance = max(8, median_height // 2)
    rows: list[list[Component]] = []

    for component in sorted_items:
        center_y = (component.box[1] + component.box[3]) // 2
        for row in rows:
            row_center = sum((item.box[1] + item.box[3]) // 2 for item in row) // len(row)
            if abs(center_y - row_center) <= row_tolerance:
                row.append(component)
                break
        else:
            rows.append([component])

    ordered: list[Component] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda component: component.box[0]))
    return ordered


def choose_auto_threshold(image: Image.Image, args: argparse.Namespace) -> int:
    selected = AUTO_THRESHOLDS[-1]
    fallback_count = -1
    for threshold in AUTO_THRESHOLDS:
        mask, _source, _mode, _key = foreground_mask_and_source(
            image,
            args.background,
            args.background_color,
            args.background_tolerance,
            threshold,
        )
        components = components_from_mask(mask, args, parse_grid(args))
        if not components:
            continue
        total_pixels = sum(component.alpha_area for component in components)
        largest_pixels = max(component.alpha_area for component in components)
        largest_ratio = largest_pixels / total_pixels if total_pixels else 1.0
        if len(components) > fallback_count:
            fallback_count = len(components)
            selected = threshold
        if len(components) >= AUTO_MIN_COMPONENTS and largest_ratio <= AUTO_MAX_COMPONENT_RATIO:
            return threshold
    return selected


def components_from_mask(mask: Image.Image, args: argparse.Namespace, grid: tuple[int, int] | None) -> list[Component]:
    width, height = mask.size
    if grid is not None:
        cols, rows = grid
        components = []
        for box in grid_boxes(width, height, cols, rows):
            component = tight_mask_box(mask, expanded_box(box, args.grid_expand, width, height))
            if component is not None and component.alpha_area >= args.min_area:
                components.append(component)
        return components

    grouped_mask = dilate(mask, args.group_radius)
    grouped = [component for component in find_components(grouped_mask, args.connectivity) if component.alpha_area >= args.min_area]
    if args.group_radius <= 0:
        components = grouped
    else:
        components = []
        for component in grouped:
            tight = tight_mask_box(mask, component.box)
            if tight is not None and tight.alpha_area >= args.min_area:
                components.append(tight)
    return merge_components(components, args.merge_distance)


def crop_image(source: Image.Image, box: tuple[int, int, int, int], padding: int, crop_mode: str) -> Image.Image:
    width, height = source.size
    padded = expanded_box(box, padding, width, height)
    crop = source.crop(padded)
    if crop_mode == "tight":
        return crop
    side = max(crop.size) + padding * 2
    output = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    output.alpha_composite(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
    return output


def resolve_inputs(args: argparse.Namespace, project_root: Path) -> list[Path]:
    inputs = [*args.inputs, *args.input]
    if inputs:
        return inputs
    return sorted(project_root.glob(args.default_inputs_glob))


def resolve_output_dir(input_path: Path, input_count: int, args: argparse.Namespace, project_root: Path) -> Path:
    if args.out_dir is not None:
        if input_count != 1:
            raise SystemExit("--out-dir can only be used with one input. Use --output-root for multiple inputs.")
        return args.out_dir if args.out_dir.is_absolute() else project_root / args.out_dir
    if args.output_root is not None:
        root = args.output_root if args.output_root.is_absolute() else project_root / args.output_root
        return root / input_path.stem
    if input_count == 1:
        return input_path.parent / f"{input_path.stem}_cut"
    return project_root / "cut_sheets" / input_path.stem


def write_outputs(input_path: Path, out_dir: Path, args: argparse.Namespace, input_count: int) -> None:
    image = Image.open(input_path).convert("RGBA")
    threshold_value = parse_threshold(args.alpha_threshold)
    threshold = choose_auto_threshold(image, args) if threshold_value == "auto" else threshold_value
    mask, source, resolved_background, background_key = foreground_mask_and_source(
        image,
        args.background,
        args.background_color,
        args.background_tolerance,
        threshold,
    )
    grid = parse_grid(args)
    components = sort_components(components_from_mask(mask, args, grid), args.sort)
    names = [safe_name(name) for name in args.names.split(",") if safe_name(name)]
    prefix = safe_name(args.prefix) or "sprite"

    out_dir.mkdir(parents=True, exist_ok=True)
    if args.manifest is not None and input_count != 1:
        raise SystemExit("--manifest can only be used with one input.")
    manifest_path = args.manifest if args.manifest is not None else out_dir / "manifest.json"
    manifest = {
        "source": str(input_path),
        "source_size": [image.size[0], image.size[1]],
        "alpha_threshold": threshold,
        "background": resolved_background,
        "background_color": list(background_key) if background_key is not None else None,
        "min_area": args.min_area,
        "padding": args.padding,
        "crop_mode": args.crop_mode,
        "group_radius": args.group_radius,
        "merge_distance": args.merge_distance,
        "connectivity": args.connectivity,
        "grid": list(grid) if grid is not None else None,
        "assets": [],
    }

    for index, component in enumerate(components, start=1):
        name = names[index - 1] if index <= len(names) else f"{prefix}_{index:03d}"
        output_name = f"{name}.png"
        output = crop_image(source, component.box, args.padding, args.crop_mode)
        output.save(out_dir / output_name)
        manifest["assets"].append(
            {
                "name": name,
                "file": output_name,
                "box": list(component.box),
                "size": list(output.size),
                "alpha_area": component.alpha_area,
            }
        )

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{input_path} -> {out_dir} ({len(components)} assets)")
    if names and len(names) != len(components):
        print(f"Warning: got {len(names)} names for {len(components)} detected assets")


def main() -> int:
    args = parse_args()
    load_pillow()
    project_root = args.project_root.expanduser().resolve()
    inputs = resolve_inputs(args, project_root)
    if not inputs:
        raise SystemExit("No input sprite sheets found.")
    for input_path in inputs:
        out_dir = resolve_output_dir(input_path, len(inputs), args, project_root)
        write_outputs(input_path, out_dir, args, len(inputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
