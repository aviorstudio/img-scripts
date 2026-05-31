# img-scripts

Shared Avior Studio image scripts. Keep image automation here instead of copying Python scripts into individual game repositories.

## Setup

These scripts require Python 3.12 and Pillow.

```sh
python -m pip install -e .
```

## Usage

Run project-specific scripts from the target game repository root, or pass `--project-root` explicitly.

```sh
python ../img-scripts/scripts/cut_sheet.py sheet.png --out-dir out
python ../img-scripts/scripts/image_resize.py image.png

# Prizm
python ../img-scripts/scripts/cut_sheet.py --project-root .

# Fixed-grid sheets
python ../img-scripts/scripts/cut_sheet.py sheet.png --grid 4x3 --out-dir out

# Revik
python ../img-scripts/scripts/generate_terrain_tiles.py --project-root . grass forest
```

## Script Inventory

| Script | Origin | Notes |
|---|---|---|
| `scripts/cut_sheet.py` | Shared | Sprite sheet cutter with alpha/background detection, connected components, optional grid mode, auto threshold, padding, and manifest output. |
| `scripts/generate_terrain_tiles.py` | Revik | Revik-specific terrain hex tile generator. |
| `scripts/image_resize.py` | Revik | Pillow force-resize to exactly 512x512 while preserving the source extension. |
