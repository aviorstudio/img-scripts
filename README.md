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
# Generic connected-component sheet cutters
python ../img-scripts/scripts/cut_connected_sprite_sheet.py --input sheet.png --out-dir out
python ../img-scripts/scripts/cut_transparent_sheet.py --input sheet.png --out-dir out
python ../img-scripts/scripts/extract_sprites.py sheet.png out
python ../img-scripts/scripts/image_resize.py image.png

# Prizm
python ../img-scripts/scripts/cut_sprite_sheets.py --project-root .
python ../img-scripts/scripts/organize_cut_assets.py --project-root .

# Castledrop
python ../img-scripts/scripts/generate_tower_effect_assets.py --project-root .

# Revik
python ../img-scripts/scripts/generate_terrain_tiles.py --project-root . grass forest
```

## Script Inventory

| Script | Origin | Notes |
|---|---|---|
| `scripts/cut_connected_sprite_sheet.py` | Castledrop | Feature-rich connected alpha island cutter with grid/background options. |
| `scripts/cut_transparent_sheet.py` | Castledrop | Transparent sheet cutter with dilation/grouping. |
| `scripts/extract_sprites.py` | Revik | Pillow connected-component sprite extractor with optional grid sorting. |
| `scripts/image_resize.py` | Revik | Pillow force-resize to exactly 512x512 while preserving the source extension. |
| `scripts/cut_sprite_sheets.py` | Prizm | Batch transparent sheet cutter with auto alpha threshold. |
| `scripts/organize_cut_assets.py` | Prizm | Prizm-specific cut asset organizer. |
| `scripts/generate_tower_effect_assets.py` | Castledrop | Castledrop-specific tower effect generator. |
| `scripts/generate_terrain_tiles.py` | Revik | Revik-specific terrain hex tile generator. |
