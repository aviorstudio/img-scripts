#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

AUTO_THRESHOLDS = (12, 16, 24, 32, 48, 64, 96, 128)
AUTO_MAX_COMPONENT_RATIO = 0.35
AUTO_MIN_COMPONENTS = 2


@dataclass
class Component:
    left: int
    top: int
    right: int
    bottom: int
    pixel_count: int

    def expanded(self, amount: int, width: int, height: int) -> "Component":
        return Component(
            left=max(0, self.left - amount),
            top=max(0, self.top - amount),
            right=min(width, self.right + amount),
            bottom=min(height, self.bottom + amount),
            pixel_count=self.pixel_count,
        )

    def overlaps(self, other: "Component") -> bool:
        return not (
            self.right <= other.left
            or other.right <= self.left
            or self.bottom <= other.top
            or other.bottom <= self.top
        )

    def merged(self, other: "Component") -> "Component":
        return Component(
            left=min(self.left, other.left),
            top=min(self.top, other.top),
            right=max(self.right, other.right),
            bottom=max(self.bottom, other.bottom),
            pixel_count=self.pixel_count + other.pixel_count,
        )

    def to_bbox(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut transparent sprite sheets into tightly cropped PNG assets."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Input sprite sheets. Defaults to transparent sheets under godot_client/src/assets/sheets.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project repository root for default inputs and relative output paths.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("godot_client/src/assets/cut_sheets"),
        help="Root directory for per-sheet output folders.",
    )
    parser.add_argument(
        "--alpha-threshold",
        default="auto",
        help=(
            "Minimum alpha value considered opaque enough to belong to a sprite. "
            "Pass an integer or 'auto' to detect a threshold that avoids faint alpha bridges."
        ),
    )
    parser.add_argument(
        "--min-pixels",
        type=int,
        default=64,
        help="Discard connected components smaller than this many pixels.",
    )
    parser.add_argument(
        "--merge-gap",
        type=int,
        default=8,
        help="Merge nearby components whose expanded bounds overlap by this gap.",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="Extra transparent padding to keep around each cropped sprite.",
    )
    return parser.parse_args()


def default_inputs(project_root: Path) -> list[Path]:
    return sorted((project_root / "godot_client/src/assets/sheets").glob("*transparent.png"))


def resolve_output_root(output_root: Path, project_root: Path) -> Path:
    if output_root.is_absolute():
        return output_root
    return project_root / output_root


def load_mask(path: Path, alpha_threshold: int) -> tuple[Image.Image, list[list[bool]]]:
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    width, height = image.size
    mask = [[False] * width for _ in range(height)]
    for y in range(height):
        row = mask[y]
        for x in range(width):
            row[x] = alpha.getpixel((x, y)) >= alpha_threshold
    return image, mask


def resolve_alpha_threshold(value: str) -> str | int:
    if value == "auto":
        return value
    try:
        resolved = int(value)
    except ValueError as exc:
        raise SystemExit("--alpha-threshold must be an integer or 'auto'.") from exc
    if resolved < 0 or resolved > 255:
        raise SystemExit("--alpha-threshold must be between 0 and 255.")
    return resolved


def find_components(mask: list[list[bool]], min_pixels: int) -> list[Component]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    visited = [[False] * width for _ in range(height)]
    components: list[Component] = []
    neighbors = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )

    for y in range(height):
        for x in range(width):
            if visited[y][x] or not mask[y][x]:
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y][x] = True
            left = right = x
            top = bottom = y
            pixels = 0

            while queue:
                cx, cy = queue.popleft()
                pixels += 1
                left = min(left, cx)
                right = max(right, cx)
                top = min(top, cy)
                bottom = max(bottom, cy)

                for dx, dy in neighbors:
                    nx = cx + dx
                    ny = cy + dy
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    if visited[ny][nx] or not mask[ny][nx]:
                        continue
                    visited[ny][nx] = True
                    queue.append((nx, ny))

            if pixels < min_pixels:
                continue

            components.append(
                Component(
                    left=left,
                    top=top,
                    right=right + 1,
                    bottom=bottom + 1,
                    pixel_count=pixels,
                )
            )

    return components


def merge_components(
    components: list[Component], width: int, height: int, merge_gap: int
) -> list[Component]:
    if merge_gap <= 0:
        return components

    merged = components[:]
    changed = True
    while changed:
        changed = False
        next_components: list[Component] = []
        while merged:
            current = merged.pop()
            current_gap = current.expanded(merge_gap, width, height)
            keep_searching = True
            while keep_searching:
                keep_searching = False
                for index in range(len(merged) - 1, -1, -1):
                    other = merged[index]
                    if current_gap.overlaps(other.expanded(merge_gap, width, height)):
                        current = current.merged(other)
                        current_gap = current.expanded(merge_gap, width, height)
                        merged.pop(index)
                        changed = True
                        keep_searching = True
            next_components.append(current)
        merged = next_components

    return sorted(merged, key=lambda c: (c.top, c.left))


def choose_auto_threshold(sheet_path: Path, min_pixels: int, merge_gap: int) -> int:
    selected = AUTO_THRESHOLDS[-1]
    fallback_count = -1

    for threshold in AUTO_THRESHOLDS:
        image, mask = load_mask(sheet_path, threshold)
        components = find_components(mask, min_pixels)
        components = merge_components(components, image.size[0], image.size[1], merge_gap)
        if not components:
            continue

        total_pixels = sum(component.pixel_count for component in components)
        largest_pixels = max(component.pixel_count for component in components)
        largest_ratio = largest_pixels / total_pixels if total_pixels else 1.0

        if len(components) > fallback_count:
            fallback_count = len(components)
            selected = threshold

        if len(components) >= AUTO_MIN_COMPONENTS and largest_ratio <= AUTO_MAX_COMPONENT_RATIO:
            return threshold

    return selected


def write_outputs(
    image: Image.Image,
    sheet_path: Path,
    output_root: Path,
    components: list[Component],
    padding: int,
    alpha_threshold: int,
    min_pixels: int,
    merge_gap: int,
) -> None:
    width, height = image.size
    sheet_name = sheet_path.stem
    output_dir = output_root / sheet_name
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("sprite_*.png"):
        old_file.unlink()
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    manifest = {
        "source_sheet": str(sheet_path),
        "sheet_size": [width, height],
        "settings": {
            "alpha_threshold": alpha_threshold,
            "min_pixels": min_pixels,
            "merge_gap": merge_gap,
            "padding": padding,
        },
        "sprites": [],
    }

    for index, component in enumerate(components, start=1):
        padded = component.expanded(padding, width, height)
        cropped = image.crop(padded.to_bbox())
        filename = f"sprite_{index:03d}.png"
        cropped.save(output_dir / filename)
        manifest["sprites"].append(
            {
                "file": filename,
                "bbox": list(component.to_bbox()),
                "padded_bbox": list(padded.to_bbox()),
                "size": [cropped.size[0], cropped.size[1]],
                "pixel_count": component.pixel_count,
            }
        )

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{sheet_path} -> {output_dir} ({len(components)} sprites)")


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    inputs = args.inputs or default_inputs(project_root)
    if not inputs:
        raise SystemExit("No input sprite sheets found.")
    output_root = resolve_output_root(args.output_root, project_root)
    alpha_threshold = resolve_alpha_threshold(args.alpha_threshold)

    for sheet_path in inputs:
        threshold = (
            choose_auto_threshold(sheet_path, args.min_pixels, args.merge_gap)
            if alpha_threshold == "auto"
            else alpha_threshold
        )
        image, mask = load_mask(sheet_path, threshold)
        components = find_components(mask, args.min_pixels)
        components = merge_components(
            components, image.size[0], image.size[1], args.merge_gap
        )
        write_outputs(
            image=image,
            sheet_path=sheet_path,
            output_root=output_root,
            components=components,
            padding=args.padding,
            alpha_threshold=threshold,
            min_pixels=args.min_pixels,
            merge_gap=args.merge_gap,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
