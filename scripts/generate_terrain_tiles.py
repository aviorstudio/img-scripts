#!/usr/bin/env python3
"""Generate per-hex tile textures so adjacent tiles share a continuous pattern."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - toolchain guard
    raise SystemExit("Pillow is required: pip install pillow") from exc


BOARD_COLS = 9
BOARD_ROWS = 9
ODD_COLUMN_ROWS = 8
CORE_HEX_H_SPACING = 45.0
CORE_HEX_V_SPACING = 52.0
CORE_HEX_HEIGHT = 52.0
CLIENT_HEX_H_SPACING = 60.0
CLIENT_HEX_V_SPACING = 69.0


@dataclass(frozen=True)
class TileVariant:
    name: str
    base_path: Path
    mask_path: Path
    output_dir: Path
    res_prefix: str


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Revik per-hex board tile textures.")
    parser.add_argument("variants", nargs="*", help="Tile variants to generate. Defaults to all variants.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Revik repository root. Defaults to the current working directory.",
    )
    return parser.parse_args(argv)


def build_variants(repo_root: Path) -> Dict[str, TileVariant]:
    project_root = repo_root / "godot_client"
    return {
        "grass": TileVariant(
            name="grass",
            base_path=project_root / "src" / "assets" / "board" / "tiles" / "dough" / "grass-dough.png",
            mask_path=project_root / "src" / "assets" / "board" / "tiles_simple" / "grass-80x69.png",
            output_dir=project_root / "src" / "assets" / "board" / "tiles" / "grass",
            res_prefix="res://src/assets/board/tiles/grass",
        ),
        "forest": TileVariant(
            name="forest",
            base_path=project_root / "src" / "assets" / "board" / "tiles" / "dough" / "forest-dough.png",
            mask_path=project_root / "src" / "assets" / "board" / "tiles_simple" / "forest-80x80.png",
            output_dir=project_root / "src" / "assets" / "board" / "tiles" / "forest",
            res_prefix="res://src/assets/board/tiles/forest",
        ),
        "mountain": TileVariant(
            name="mountain",
            base_path=project_root / "src" / "assets" / "board" / "tiles" / "dough" / "mountain-dough.png",
            mask_path=project_root / "src" / "assets" / "board" / "tiles_simple" / "volcanic-80x90.png",
            output_dir=project_root / "src" / "assets" / "board" / "tiles" / "mountain",
            res_prefix="res://src/assets/board/tiles/mountain",
        ),
        "ocean": TileVariant(
            name="ocean",
            base_path=project_root / "src" / "assets" / "board" / "tiles" / "dough" / "ocean-dough.png",
            mask_path=project_root / "src" / "assets" / "board" / "tiles_simple" / "water-80x69.png",
            output_dir=project_root / "src" / "assets" / "board" / "tiles" / "ocean",
            res_prefix="res://src/assets/board/tiles/ocean",
        ),
    }


def iter_board_positions() -> Iterable[Tuple[int, int]]:
    for col in range(BOARD_COLS):
        row_count = BOARD_ROWS if col % 2 == 0 else ODD_COLUMN_ROWS
        for row in range(row_count):
            yield col, row


def logical_to_board_space(col: int, row: int) -> Tuple[float, float]:
    """Reproduce BoardGeometryUtil -> ClientConstants coordinate conversion."""
    x = col * CORE_HEX_H_SPACING
    y = row * CORE_HEX_V_SPACING
    if col % 2 == 1:
        y += CORE_HEX_HEIGHT / 2.0
    x *= CLIENT_HEX_H_SPACING / CORE_HEX_H_SPACING
    y *= CLIENT_HEX_V_SPACING / CORE_HEX_V_SPACING
    return x, y


def build_samples() -> Tuple[Tuple[Tuple[int, int, Tuple[float, float]], ...], Tuple[float, float, float, float]]:
    samples = []
    xs = []
    ys = []
    for col, row in iter_board_positions():
        center = logical_to_board_space(col, row)
        samples.append((col, row, center))
        xs.append(center[0])
        ys.append(center[1])
    bounds = (min(xs), max(xs), min(ys), max(ys))
    return tuple(samples), bounds


def clean_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for png in output_dir.glob("*.png"):
        png.unlink()
    for imp in output_dir.glob("*.png.import"):
        imp.unlink()


def load_mask(mask_path: Path) -> Image.Image:
    mask = Image.open(mask_path).convert("RGBA")
    alpha = mask.split()[-1]
    if alpha.size != mask.size:
        raise SystemExit(f"Failed to derive mask alpha from {mask_path}")
    return alpha


def derive_offsets(base_size: Tuple[int, int], bounds: Tuple[float, float, float, float]) -> Tuple[float, float]:
    min_x, max_x, min_y, max_y = bounds
    board_width = max_x - min_x
    board_height = max_y - min_y
    base_width, base_height = base_size
    if board_width > base_width or board_height > base_height:
        raise SystemExit(
            f"Base texture ({base_width}x{base_height}) is smaller than board footprint ({board_width}x{board_height})."
        )
    offset_x = (base_width - board_width) / 2.0 - min_x
    offset_y = (base_height - board_height) / 2.0 - min_y
    return offset_x, offset_y


def crop_hexes(
    base_image: Image.Image,
    mask: Image.Image,
    samples: Tuple[Tuple[int, int, Tuple[float, float]], ...],
    offsets: Tuple[float, float],
    output_dir: Path,
    res_prefix: str,
) -> Dict[str, str]:
    tile_width, tile_height = mask.size
    offset_x, offset_y = offsets
    manifest: Dict[str, str] = {}

    for col, row, center in samples:
        center_x = center[0] + offset_x
        center_y = center[1] + offset_y
        left = int(round(center_x - tile_width / 2.0))
        top = int(round(center_y - tile_height / 2.0))
        right = left + tile_width
        bottom = top + tile_height
        box = (left, top, right, bottom)
        tile = base_image.crop(box).convert("RGBA")
        tile.putalpha(mask)

        filename = f"{res_prefix.split('/')[-1]}_col{col}_row{row}.png"
        output_path = output_dir / filename
        tile.save(output_path)
        manifest[f"{col},{row}"] = f"{res_prefix}/{filename}"
    return manifest


def write_manifest(
    manifest_data: Dict[str, str],
    bounds: Tuple[float, float, float, float],
    offsets: Tuple[float, float],
    variant: TileVariant,
    tile_size: Tuple[int, int],
    repo_root: Path,
) -> None:
    min_x, max_x, min_y, max_y = bounds
    data = {
        "meta": {
            "variant": variant.name,
            "board_bounds": {"min": [min_x, min_y], "max": [max_x, max_y]},
            "offset": [offsets[0], offsets[1]],
            "tile_size": [tile_size[0], tile_size[1]],
            "source_image": display_path(variant.base_path, repo_root),
        },
        "tiles": manifest_data,
    }
    manifest_path = variant.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_variants(selected: Sequence[str], variants_by_name: Dict[str, TileVariant]) -> Sequence[TileVariant]:
    if not selected:
        return tuple(variants_by_name.values())
    variants = []
    for name in selected:
        lowered = name.lower()
        if lowered not in variants_by_name:
            raise SystemExit(f"Unknown variant '{name}'. Available: {', '.join(sorted(variants_by_name))}")
        variants.append(variants_by_name[lowered])
    return tuple(variants)


def generate_variant(
    variant: TileVariant,
    samples: Tuple[Tuple[int, int, Tuple[float, float]], ...],
    bounds: Tuple[float, float, float, float],
    repo_root: Path,
) -> int:
    if not variant.base_path.exists():
        raise SystemExit(f"Missing base texture for {variant.name}: {variant.base_path}")
    if not variant.mask_path.exists():
        raise SystemExit(f"Missing mask texture for {variant.name}: {variant.mask_path}")

    clean_output_dir(variant.output_dir)

    base_image = Image.open(variant.base_path).convert("RGBA")
    mask = load_mask(variant.mask_path)
    offsets = derive_offsets(base_image.size, bounds)
    manifest = crop_hexes(base_image, mask, samples, offsets, variant.output_dir, variant.res_prefix)
    write_manifest(manifest, bounds, offsets, variant, mask.size, repo_root)
    print(f"[{variant.name}] Generated {len(manifest)} tiles in {display_path(variant.output_dir, repo_root)}")
    return len(manifest)


def main(argv: Sequence[str]) -> None:
    args = parse_args(argv[1:])
    repo_root = args.project_root.expanduser().resolve()
    samples, bounds = build_samples()
    variants = resolve_variants(args.variants, build_variants(repo_root))
    total = 0
    for variant in variants:
        total += generate_variant(variant, samples, bounds, repo_root)
    if len(variants) > 1:
        print(f"Generated {total} tiles across {len(variants)} variants.")


if __name__ == "__main__":
    import sys

    main(sys.argv)
