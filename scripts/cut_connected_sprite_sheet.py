#!/usr/bin/env python3
"""Cut transparent sprite sheets by connected alpha islands.

Each saved asset is one connected component of non-transparent pixels. The
component is cropped to its exact alpha bounds, then centered on a square
transparent canvas whose edges fit the larger crop dimension plus optional
padding.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


@dataclass(frozen=True)
class Component:
    box: tuple[int, int, int, int]
    alpha_area: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut a transparent sheet into square PNGs using connected alpha pixels.",
    )
    parser.add_argument("--input", required=True, type=Path, help="RGBA sprite sheet PNG.")
    parser.add_argument("--out-dir", required=True, type=Path, help="Directory for cut PNGs.")
    parser.add_argument("--prefix", default="asset", help="Filename prefix when --names is omitted.")
    parser.add_argument("--names", default="", help="Optional comma-separated output names in reading order.")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional manifest JSON path.")
    parser.add_argument("--grid-cols", type=int, default=0, help="Optional fixed sheet column count.")
    parser.add_argument("--grid-rows", type=int, default=0, help="Optional fixed sheet row count.")
    parser.add_argument(
        "--grid-pick",
        choices=("cell_centered", "largest_global", "largest", "all"),
        default="cell_centered",
        help="In grid mode, save cell-assigned components, full largest sheet component, largest cell-local component, or all cell foreground.",
    )
    parser.add_argument(
        "--grid-expand",
        type=int,
        default=0,
        help="In grid mode, expand each cell search window by this many pixels before selecting the component.",
    )
    parser.add_argument(
        "--grid-expand-x",
        type=int,
        default=None,
        help="Horizontal grid expansion override. Defaults to --grid-expand.",
    )
    parser.add_argument(
        "--grid-expand-y",
        type=int,
        default=None,
        help="Vertical grid expansion override. Defaults to --grid-expand.",
    )
    parser.add_argument("--alpha-threshold", type=int, default=8, help="Minimum alpha counted as art.")
    parser.add_argument(
        "--background",
        choices=("auto", "alpha", "corner", "color"),
        default="auto",
        help="How to decide which pixels are background.",
    )
    parser.add_argument(
        "--background-color",
        default="",
        help="RGB background key for --background color, formatted as R,G,B or #RRGGBB.",
    )
    parser.add_argument(
        "--background-tolerance",
        type=int,
        default=80,
        help="Maximum RGB distance from the background key treated as transparent.",
    )
    parser.add_argument("--min-area", type=int, default=64, help="Smallest alpha pixel count to save.")
    parser.add_argument("--padding", type=int, default=0, help="Transparent padding around the tight crop.")
    parser.add_argument(
        "--merge-distance",
        type=int,
        default=0,
        help="Merge detected components whose bounding boxes are within this many pixels.",
    )
    parser.add_argument(
        "--connectivity",
        type=int,
        choices=(4, 8),
        default=8,
        help="Neighbor rule for connected pixels.",
    )
    parser.add_argument(
        "--sort",
        choices=("reading", "x", "y", "area"),
        default="reading",
        help="Output order for detected components.",
    )
    return parser.parse_args()


def safe_name(raw: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in raw.strip())
    return "_".join(part for part in cleaned.split("_") if part)


def neighbor_offsets(connectivity: int) -> tuple[tuple[int, int], ...]:
    if connectivity == 4:
        return ((1, 0), (-1, 0), (0, 1), (0, -1))
    return (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )


def parse_rgb(raw: str) -> tuple[int, int, int]:
    value = raw.strip()
    if value.startswith("#") and len(value) == 7:
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("--background-color must be R,G,B or #RRGGBB")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


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
        has_transparency = alpha.getextrema()[0] < 255
        mode = "alpha" if has_transparency else "corner"
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


def components_from_grid(
    mask: Image.Image,
    cols: int,
    rows: int,
    min_area: int,
    connectivity: int,
    grid_pick: str,
    grid_expand_x: int,
    grid_expand_y: int,
) -> list[Component]:
    width, height = mask.size
    if grid_pick == "largest_global":
        return global_components_from_grid(mask, cols, rows, min_area, connectivity)

    components: list[Component] = []
    for cell_box in grid_boxes(width, height, cols, rows):
        search_box = expanded_box(cell_box, grid_expand_x, grid_expand_y, width, height)
        cell_mask = mask.crop(search_box)
        component = component_from_cell(cell_mask, cell_box, search_box, min_area, connectivity, grid_pick)
        if component is None:
            continue
        cell_left, cell_top, _, _ = search_box
        left, top, right, bottom = component.box
        components.append(
            Component(
                (cell_left + left, cell_top + top, cell_left + right, cell_top + bottom),
                component.alpha_area,
            )
        )
    return components


def expanded_box(
    box: tuple[int, int, int, int],
    amount_x: int,
    amount_y: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if amount_x <= 0 and amount_y <= 0:
        return box
    left, top, right, bottom = box
    return (
        max(0, left - amount_x),
        max(0, top - amount_y),
        min(width, right + amount_x),
        min(height, bottom + amount_y),
    )


def global_components_from_grid(
    mask: Image.Image,
    cols: int,
    rows: int,
    min_area: int,
    connectivity: int,
) -> list[Component]:
    global_components = [
        component
        for component in find_components(mask, connectivity)
        if component.alpha_area >= min_area
    ]
    cell_boxes = grid_boxes(mask.size[0], mask.size[1], cols, rows)
    selected: list[Component] = []
    used_indexes: set[int] = set()

    for cell_box in cell_boxes:
        best_index = -1
        best_score = 0
        for index, component in enumerate(global_components):
            if index in used_indexes:
                continue
            score = box_intersection_area(component.box, cell_box)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index == -1:
            continue
        used_indexes.add(best_index)
        selected.append(global_components[best_index])

    return selected


def box_intersection_area(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> int:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def component_from_cell(
    cell_mask: Image.Image,
    cell_box: tuple[int, int, int, int],
    search_box: tuple[int, int, int, int],
    min_area: int,
    connectivity: int,
    grid_pick: str,
) -> Component | None:
    if grid_pick == "all":
        bbox = cell_mask.getbbox()
        if bbox is None:
            return None
        alpha_area = sum(cell_mask.histogram()[1:])
        if alpha_area < min_area:
            return None
        return Component(bbox, alpha_area)

    components = [
        component
        for component in find_components(cell_mask, connectivity)
        if component.alpha_area >= min_area
    ]
    if not components:
        return None
    if grid_pick == "cell_centered":
        assigned = [
            component
            for component in components
            if component_belongs_to_cell(component, cell_box, search_box)
        ]
        if not assigned:
            assigned = [max(components, key=lambda component: component.alpha_area)]
        return merge_component_boxes(assigned)
    return max(components, key=lambda component: component.alpha_area)


def component_belongs_to_cell(
    component: Component,
    cell_box: tuple[int, int, int, int],
    search_box: tuple[int, int, int, int],
) -> bool:
    search_left, search_top, _, _ = search_box
    local_cell = (
        cell_box[0] - search_left,
        cell_box[1] - search_top,
        cell_box[2] - search_left,
        cell_box[3] - search_top,
    )
    center_x = (component.box[0] + component.box[2]) // 2
    center_y = (component.box[1] + component.box[3]) // 2
    if local_cell[0] <= center_x < local_cell[2] and local_cell[1] <= center_y < local_cell[3]:
        return True

    overlap = box_intersection_area(component.box, local_cell)
    component_area = (component.box[2] - component.box[0]) * (component.box[3] - component.box[1])
    return component_area > 0 and float(overlap) / float(component_area) >= 0.45


def merge_component_boxes(components: list[Component]) -> Component:
    left = min(component.box[0] for component in components)
    top = min(component.box[1] for component in components)
    right = max(component.box[2] for component in components)
    bottom = max(component.box[3] for component in components)
    alpha_area = sum(component.alpha_area for component in components)
    return Component((left, top, right, bottom), alpha_area)


def sort_components(components: Iterable[Component], sort_mode: str) -> list[Component]:
    items = list(components)
    if sort_mode == "x":
        return sorted(items, key=lambda component: (component.box[0], component.box[1]))
    if sort_mode == "y":
        return sorted(items, key=lambda component: (component.box[1], component.box[0]))
    if sort_mode == "area":
        return sorted(items, key=lambda component: component.alpha_area, reverse=True)
    return sort_components_reading_order(items)


def merge_components(components: list[Component], distance: int) -> list[Component]:
    if distance <= 0 or len(components) <= 1:
        return components

    parent = list(range(len(components)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(components):
        for right_index in range(left_index + 1, len(components)):
            right = components[right_index]
            if boxes_within_distance(left.box, right.box, distance):
                union(left_index, right_index)

    grouped: dict[int, list[Component]] = {}
    for index, component in enumerate(components):
        grouped.setdefault(find(index), []).append(component)

    merged: list[Component] = []
    for group in grouped.values():
        left = min(component.box[0] for component in group)
        top = min(component.box[1] for component in group)
        right = max(component.box[2] for component in group)
        bottom = max(component.box[3] for component in group)
        alpha_area = sum(component.alpha_area for component in group)
        merged.append(Component((left, top, right, bottom), alpha_area))
    return merged


def boxes_within_distance(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    distance: int,
) -> bool:
    left_x0, left_y0, left_x1, left_y1 = left
    right_x0, right_y0, right_x1, right_y1 = right
    return not (
        left_x1 + distance < right_x0
        or right_x1 + distance < left_x0
        or left_y1 + distance < right_y0
        or right_y1 + distance < left_y0
    )


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


def square_crop(source: Image.Image, box: tuple[int, int, int, int], padding: int) -> Image.Image:
    crop = source.crop(box)
    crop_width, crop_height = crop.size
    side = max(crop_width, crop_height) + padding * 2
    output = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    paste_x = (side - crop_width) // 2
    paste_y = (side - crop_height) // 2
    output.alpha_composite(crop, (paste_x, paste_y))
    return output


def main() -> int:
    args = parse_args()
    source = Image.open(args.input).convert("RGBA")
    width, height = source.size
    mask, transparent_source, resolved_background, background_key = foreground_mask_and_source(
        source,
        args.background,
        args.background_color,
        args.background_tolerance,
        args.alpha_threshold,
    )

    use_grid = args.grid_cols > 0 or args.grid_rows > 0
    if use_grid:
        if args.grid_cols <= 0 or args.grid_rows <= 0:
            raise ValueError("--grid-cols and --grid-rows must be used together")
        grid_expand_x = args.grid_expand if args.grid_expand_x is None else args.grid_expand_x
        grid_expand_y = args.grid_expand if args.grid_expand_y is None else args.grid_expand_y
        components = components_from_grid(
            mask,
            args.grid_cols,
            args.grid_rows,
            args.min_area,
            args.connectivity,
            args.grid_pick,
            grid_expand_x,
            grid_expand_y,
        )
    else:
        grid_expand_x = 0
        grid_expand_y = 0
        components = [
            component
            for component in find_components(mask, args.connectivity)
            if component.alpha_area >= args.min_area
        ]
        components = merge_components(components, args.merge_distance)
    ordered = sort_components(components, args.sort)
    names = [safe_name(name) for name in args.names.split(",") if safe_name(name)]
    prefix = safe_name(args.prefix) or "asset"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest if args.manifest is not None else args.out_dir / "manifest.json"
    manifest = {
        "source": str(args.input),
        "source_size": [width, height],
        "alpha_threshold": args.alpha_threshold,
        "background": resolved_background,
        "background_color": list(background_key) if background_key is not None else None,
        "background_tolerance": args.background_tolerance,
        "grid_cols": args.grid_cols,
        "grid_rows": args.grid_rows,
        "grid_pick": args.grid_pick,
        "grid_expand_x": grid_expand_x,
        "grid_expand_y": grid_expand_y,
        "connectivity": args.connectivity,
        "merge_distance": args.merge_distance,
        "min_area": args.min_area,
        "padding": args.padding,
        "sort": args.sort,
        "assets": [],
    }

    for index, component in enumerate(ordered, start=1):
        name = names[index - 1] if index <= len(names) else f"{prefix}_{index:03d}"
        output_name = f"{name}.png"
        output_path = args.out_dir / output_name
        output = square_crop(transparent_source, component.box, args.padding)
        output.save(output_path)
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
    print(f"Wrote {len(ordered)} assets to {args.out_dir}")
    print(f"Wrote manifest to {manifest_path}")
    if names and len(names) != len(ordered):
        print(f"Warning: got {len(names)} names for {len(ordered)} detected assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
