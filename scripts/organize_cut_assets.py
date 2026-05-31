#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize Prizm cut sprites into the asset library.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Prizm repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=None,
        help="Asset root. Defaults to <project-root>/godot_client/src/assets.",
    )
    return parser.parse_args()


def resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def sprite_name(num: int) -> str:
    return f"sprite_{num:03d}.png"


def copy_group(cut_root: Path, lib_root: Path, sheet: str, category: str, numbers: list[int]) -> None:
    src_dir = cut_root / sheet
    dst_dir = lib_root / category
    dst_dir.mkdir(parents=True, exist_ok=True)
    for num in numbers:
        src = src_dir / sprite_name(num)
        if not src.exists():
            continue
        dst = dst_dir / f"{sheet}--{sprite_name(num)}"
        shutil.copy2(src, dst)


def reset_library(lib_root: Path) -> None:
    if lib_root.exists():
        shutil.rmtree(lib_root)
    lib_root.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    assets_root = (
        resolve_project_path(args.assets_root, project_root)
        if args.assets_root is not None
        else project_root / "godot_client/src/assets"
    )
    cut_root = assets_root / "cut_sheets"
    lib_root = assets_root / "library"
    reset_library(lib_root)

    core = "crystal-temple-sheet-01-core-atlas-transparent"
    env = "crystal-temple-sheet-02-environment-atlas-transparent"
    fx = "crystal-temple-sheet-03-fx-character-atlas-transparent"
    objectives = "objective-crystals-sheet-transparent"

    copy_group(cut_root, lib_root, core, "characters", [1, 2, 6, 7, 11, 29, 32, 39, 40])
    copy_group(cut_root, lib_root, core, "floors", [3, 4, 5, 14, 15])
    copy_group(cut_root, lib_root, core, "ledges", [8])
    copy_group(cut_root, lib_root, core, "ramps", [9, 10, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24])
    copy_group(cut_root, lib_root, core, "blocks", [25, 26, 27, 28, 30, 31])
    copy_group(cut_root, lib_root, core, "doors", [33, 34, 35, 36, 37, 38])
    copy_group(cut_root, lib_root, core, "devices", [41])
    copy_group(cut_root, lib_root, core, "props", [42])
    copy_group(cut_root, lib_root, core, "effects", [43])

    copy_group(cut_root, lib_root, env, "floors", [1, 2, 3, 4, 5, 6])
    copy_group(cut_root, lib_root, env, "ledges", list(range(7, 36)))
    copy_group(cut_root, lib_root, env, "ramps", list(range(36, 46)))
    copy_group(cut_root, lib_root, env, "doors", list(range(46, 60)))
    copy_group(cut_root, lib_root, env, "blocks", list(range(60, 71)))
    copy_group(cut_root, lib_root, env, "props", list(range(71, 85)))
    copy_group(cut_root, lib_root, env, "crystals", list(range(85, 90)) + list(range(93, 98)))
    copy_group(cut_root, lib_root, env, "symbols", [90, 91, 92])

    copy_group(cut_root, lib_root, fx, "characters", list(range(2, 10)) + [17])
    copy_group(cut_root, lib_root, fx, "transmitters", [10, 11, 12, 18, 19, 20])
    copy_group(cut_root, lib_root, fx, "receivers", [13, 14, 15, 16])
    copy_group(cut_root, lib_root, fx, "doors", [21])
    copy_group(cut_root, lib_root, fx, "effects", list(range(22, 47)))
    copy_group(cut_root, lib_root, fx, "ui", list(range(47, 53)))

    copy_group(cut_root, lib_root, objectives, "objective_crystals", list(range(1, 8)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
