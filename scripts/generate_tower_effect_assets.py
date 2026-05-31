#!/usr/bin/env python3
from __future__ import annotations

import argparse
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


SIZE = 256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Castledrop tower effect PNG assets.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Castledrop repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to <project-root>/godot_client/src/assets/sprites/effects/tower_combo.",
    )
    return parser.parse_args()


def resolve_project_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _canvas() -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _save(out_dir: Path, name: str, image: Image.Image) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    image.save(out_dir / f"{name}.png")


def _glow(draw_fn, blur: int = 8) -> Image.Image:
    base = _canvas()
    draw = ImageDraw.Draw(base)
    draw_fn(draw, 0.32)
    halo = base.filter(ImageFilter.GaussianBlur(blur))
    image = _canvas()
    image.alpha_composite(halo)
    draw = ImageDraw.Draw(image)
    draw_fn(draw, 1.0)
    return image


def lane_band() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        a = int(180 * alpha)
        draw.rounded_rectangle((10, 88, 246, 168), radius=28, fill=(248, 236, 150, int(42 * alpha)), outline=(255, 246, 183, a), width=5)
        for x in range(34, 232, 38):
            draw.line((x, 74, x - 16, 184), fill=(255, 255, 255, int(90 * alpha)), width=3)

    return _glow(draw_fn)


def column_strike() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        draw.rounded_rectangle((88, 6, 168, 250), radius=24, fill=(134, 196, 255, int(38 * alpha)), outline=(190, 225, 255, int(175 * alpha)), width=5)
        draw.line((118, 14, 92, 238), fill=(255, 255, 255, int(130 * alpha)), width=4)
        draw.line((148, 18, 164, 232), fill=(87, 152, 255, int(130 * alpha)), width=4)

    return _glow(draw_fn)


def cone_fan() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        origin = (24, 128)
        points = [origin, (244, 34), (244, 222)]
        draw.polygon(points, fill=(255, 185, 110, int(35 * alpha)))
        for y in (56, 92, 128, 164, 200):
            draw.line((32, 128, 244, y), fill=(255, 228, 177, int(150 * alpha)), width=4)
        draw.arc((10, 2, 270, 254), -28, 28, fill=(255, 245, 205, int(170 * alpha)), width=5)

    return _glow(draw_fn)


def arc_projectile() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        for offset, width in ((0, 7), (16, 4), (32, 3)):
            draw.arc((26 + offset, 58 + offset // 2, 238 - offset, 256 - offset // 2), 204, 314, fill=(255, 232, 144, int(190 * alpha)), width=width)
        draw.ellipse((162, 46, 222, 106), fill=(255, 112, 66, int(210 * alpha)), outline=(255, 239, 163, int(210 * alpha)), width=4)

    return _glow(draw_fn)


def empower_aura() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        draw.ellipse((34, 34, 222, 222), fill=(94, 225, 150, int(24 * alpha)), outline=(168, 255, 198, int(185 * alpha)), width=6)
        for i in range(12):
            angle = i * pi / 6.0
            p1 = (128 + cos(angle) * 70, 128 + sin(angle) * 70)
            p2 = (128 + cos(angle) * 102, 128 + sin(angle) * 102)
            draw.line((p1[0], p1[1], p2[0], p2[1]), fill=(245, 255, 190, int(150 * alpha)), width=3)

    return _glow(draw_fn)


def mark_ring() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        draw.ellipse((54, 54, 202, 202), outline=(255, 216, 91, int(220 * alpha)), width=8)
        draw.line((128, 26, 128, 86), fill=(255, 246, 170, int(180 * alpha)), width=5)
        draw.line((128, 170, 128, 230), fill=(255, 246, 170, int(180 * alpha)), width=5)
        draw.line((26, 128, 86, 128), fill=(255, 246, 170, int(180 * alpha)), width=5)
        draw.line((170, 128, 230, 128), fill=(255, 246, 170, int(180 * alpha)), width=5)

    return _glow(draw_fn)


def brittle_shatter() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        shards = [((128, 24), (100, 116), (148, 112)), ((54, 54), (92, 128), (34, 168)), ((202, 54), (164, 128), (222, 168)), ((92, 146), (128, 230), (160, 146))]
        for shard in shards:
            draw.polygon(shard, fill=(155, 230, 255, int(78 * alpha)), outline=(226, 249, 255, int(180 * alpha)))
        draw.line((54, 202, 202, 54), fill=(255, 255, 255, int(150 * alpha)), width=4)

    return _glow(draw_fn)


def spark() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        pts = [(126, 12), (94, 112), (130, 106), (104, 244), (170, 88), (132, 96), (158, 12)]
        draw.polygon(pts, fill=(255, 244, 122, int(210 * alpha)), outline=(120, 218, 255, int(170 * alpha)))

    return _glow(draw_fn, 10)


def wind_lane() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        for y, length in ((80, 188), (126, 220), (174, 168)):
            draw.arc((22, y - 42, length, y + 42), 210, 28, fill=(188, 245, 255, int(185 * alpha)), width=7)
            draw.polygon([(length - 10, y - 12), (length + 24, y), (length - 10, y + 12)], fill=(188, 245, 255, int(150 * alpha)))

    return _glow(draw_fn)


def crusher_jaws() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        for y in (58, 198):
            teeth = []
            for i in range(6):
                x = 48 + i * 32
                if y < 128:
                    teeth.extend([(x, y), (x + 14, y + 48), (x + 28, y)])
                else:
                    teeth.extend([(x, y), (x + 14, y - 48), (x + 28, y)])
            draw.polygon(teeth, fill=(180, 195, 205, int(130 * alpha)), outline=(245, 250, 255, int(200 * alpha)))
        draw.line((44, 128, 212, 128), fill=(255, 104, 104, int(160 * alpha)), width=5)

    return _glow(draw_fn)


def tar_lane() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 84, 238, 172), radius=32, fill=(56, 34, 22, 190), outline=(126, 92, 55, 175), width=5)
    for x in (52, 96, 146, 196):
        draw.ellipse((x, 106, x + 32, 144), fill=(92, 58, 31, 150))
    return image.filter(ImageFilter.GaussianBlur(0.4))


def saw_blade() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    points = []
    for i in range(32):
        radius = 112 if i % 2 == 0 else 82
        angle = i * pi / 16.0
        points.append((128 + cos(angle) * radius, 128 + sin(angle) * radius))
    draw.polygon(points, fill=(190, 204, 216, 210), outline=(255, 255, 255, 220))
    draw.ellipse((78, 78, 178, 178), fill=(84, 94, 105, 220), outline=(245, 250, 255, 220), width=5)
    draw.ellipse((112, 112, 144, 144), fill=(23, 28, 36, 230))
    return image


def net_unfurl() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.ellipse((24, 56, 232, 200), fill=(130, 195, 185, 36), outline=(212, 255, 238, 185), width=5)
    for x in range(54, 212, 26):
        draw.line((x, 62, x - 18, 194), fill=(212, 255, 238, 135), width=3)
        draw.line((x, 194, x + 18, 62), fill=(212, 255, 238, 115), width=3)
    return image.filter(ImageFilter.GaussianBlur(0.3))


def plague_cloud() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    for cx, cy, r, a in ((92, 126, 62, 105), (136, 102, 74, 95), (162, 150, 58, 110), (78, 162, 42, 95)):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(133, 202, 99, a))
    for cx, cy in ((92, 102), (158, 120), (128, 168), (184, 156)):
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(222, 255, 156, 160))
    return image.filter(ImageFilter.GaussianBlur(3))


def time_bubble() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        draw.ellipse((34, 34, 222, 222), fill=(145, 190, 255, int(24 * alpha)), outline=(214, 230, 255, int(190 * alpha)), width=5)
        draw.line((128, 62, 128, 132), fill=(255, 255, 255, int(160 * alpha)), width=5)
        draw.line((128, 132, 172, 162), fill=(255, 255, 255, int(160 * alpha)), width=5)

    return _glow(draw_fn)


def gravity_lens() -> Image.Image:
    def draw_fn(draw: ImageDraw.ImageDraw, alpha: float) -> None:
        for i in range(4):
            inset = 28 + i * 20
            draw.ellipse((inset, inset, SIZE - inset, SIZE - inset), outline=(174, 128, 255, int((180 - i * 30) * alpha)), width=5)
        draw.ellipse((108, 108, 148, 148), fill=(255, 255, 255, int(120 * alpha)))

    return _glow(draw_fn, 12)


def portcullis() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    for x in range(58, 210, 32):
        draw.rounded_rectangle((x, 28, x + 12, 226), radius=5, fill=(168, 178, 186, 220), outline=(245, 250, 255, 170), width=2)
    draw.rounded_rectangle((44, 60, 212, 78), radius=6, fill=(108, 118, 128, 220))
    draw.rounded_rectangle((44, 178, 212, 196), radius=6, fill=(108, 118, 128, 220))
    return image


def pike_flash() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    for y in (70, 112, 154, 196):
        draw.line((24, y, 214, y - 34), fill=(230, 235, 232, 220), width=6)
        draw.polygon([(214, y - 34), (244, y - 48), (224, y - 16)], fill=(255, 245, 210, 230))
    return image.filter(ImageFilter.GaussianBlur(0.2))


def raven_swoop() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.arc((18, 32, 138, 174), 210, 350, fill=(30, 34, 44, 230), width=18)
    draw.arc((118, 32, 238, 174), 190, 330, fill=(30, 34, 44, 230), width=18)
    draw.polygon([(128, 134), (108, 176), (148, 176)], fill=(30, 34, 44, 230))
    draw.line((60, 196, 196, 58), fill=(114, 190, 255, 150), width=5)
    return image.filter(ImageFilter.GaussianBlur(0.4))


def mirror_echo() -> Image.Image:
    image = _canvas()
    draw = ImageDraw.Draw(image)
    draw.polygon([(128, 20), (218, 128), (128, 236), (38, 128)], fill=(198, 238, 255, 48), outline=(229, 253, 255, 215))
    draw.line((74, 128, 182, 128), fill=(255, 255, 255, 150), width=5)
    draw.line((128, 70, 128, 186), fill=(255, 255, 255, 95), width=3)
    return image


ASSETS = {
    "tower_lane_band": lane_band,
    "tower_column_strike": column_strike,
    "tower_cone_fan": cone_fan,
    "tower_arc_projectile": arc_projectile,
    "tower_empower_aura": empower_aura,
    "tower_mark_ring": mark_ring,
    "tower_brittle_shatter": brittle_shatter,
    "tower_conductive_spark": spark,
    "tower_wind_lane": wind_lane,
    "tower_crusher_jaws": crusher_jaws,
    "tower_tar_lane": tar_lane,
    "tower_saw_blade": saw_blade,
    "tower_net_unfurl": net_unfurl,
    "tower_plague_cloud": plague_cloud,
    "tower_time_bubble": time_bubble,
    "tower_gravity_lens": gravity_lens,
    "tower_portcullis_slam": portcullis,
    "tower_pike_flash": pike_flash,
    "tower_raven_swoop": raven_swoop,
    "tower_mirror_echo": mirror_echo,
}


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    out_dir = (
        resolve_project_path(args.out_dir, project_root)
        if args.out_dir is not None
        else project_root / "godot_client/src/assets/sprites/effects/tower_combo"
    )
    for name, factory in ASSETS.items():
        _save(out_dir, name, factory())
    print(f"generated {len(ASSETS)} tower effect assets in {out_dir}")


if __name__ == "__main__":
    main()
