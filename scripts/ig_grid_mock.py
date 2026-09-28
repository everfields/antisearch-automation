"""Mock of the Instagram profile grid on a phone, with the reel covers (creatives/cover.py).

A 390 pt wide phone at 3x (1170 px), the profile header drawn with shapes, then the grid: three
columns of 3:4 tiles (Instagram's profile grid crops each reel's 9:16 cover to its centre 3:4).
Also writes one cover at full size (1080x1920). Deterministic, no model.

    python scripts/ig_grid_mock.py --posts state/posts.csv --out /tmp/ig-mock
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from antisearch_mill.creatives.cover import cover_image
from antisearch_mill.fonts import resolve_font

S = 3  # px per pt
W_PT = 390
GAP_PT = 1
BG, FG, DIM, LINE = (0, 0, 0), (245, 245, 245), (168, 168, 168), (38, 38, 38)


def latest_verdicts(posts: Path, n: int) -> list[str]:
    """The newest distinct Instagram reel verdicts that went out, newest first (the grid's order)."""
    rows = [r for r in csv.DictReader(posts.open(encoding="utf-8"))
            if r["network"] == "instagram" and r["status"] in ("published", "scheduled") and r.get("verdict")]
    out: list[str] = []
    for r in sorted(rows, key=lambda r: r["at"], reverse=True):
        if r["verdict"] not in out:
            out.append(r["verdict"])
    return out[:n]


def _font(path: str, pt: float, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    p = Path(path)
    heavier = p.with_name(p.name.replace("Regular", weight))
    return ImageFont.truetype(str(heavier if heavier.is_file() else p), round(pt * S))


def grid(covers: list[Image.Image], font_path: str) -> Image.Image:
    W = W_PT * S
    tile_w = (W - 2 * GAP_PT * S) // 3
    tile_h = round(tile_w * 4 / 3)
    rows = (len(covers) + 2) // 3
    header_h = 330 * S
    img = Image.new("RGB", (W, header_h + rows * (tile_h + GAP_PT * S) + 40 * S), BG)
    d = ImageDraw.Draw(img)
    f = lambda pt, w="Regular": _font(font_path, pt, w)  # noqa: E731
    d.text((16 * S, 14 * S), "9:41", font=f(15, "SemiBold"), fill=FG)
    d.text((16 * S, 56 * S), "antisearch_ai", font=f(20, "SemiBold"), fill=FG)
    cx, cy, r = 60 * S, 130 * S, 43 * S
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 18, 18), outline=LINE, width=S)
    d.text((cx, cy), "a", font=f(34, "SemiBold"), fill=FG, anchor="mm")
    for k, label in enumerate(("posts", "followers", "following")):  # counts left out: the mock is about the grid
        x = (150 + k * 82) * S
        d.text((x, 137 * S), label, font=f(13), fill=FG, anchor="mm")
    d.text((16 * S, 186 * S), "antisearch", font=f(14, "SemiBold"), fill=FG)
    d.text((16 * S, 205 * S), "antisearch.ai", font=f(14, "SemiBold"), fill=(224, 241, 255))
    for k, label in enumerate(("Follow", "Message")):
        x0 = (16 + k * 182) * S
        d.rounded_rectangle([x0, 252 * S, x0 + 176 * S, 284 * S], radius=8 * S,
                            fill=(0, 149, 246) if k == 0 else (38, 38, 38))
        d.text((x0 + 88 * S, 268 * S), label, font=f(14, "SemiBold"), fill=FG, anchor="mm")
    ty = 300 * S
    for k in range(3):  # tabs: grid (selected), reels, tagged, drawn as simple marks
        x = round((k + 0.5) * W / 3)
        col = FG if k == 0 else DIM
        if k == 0:
            for gx in range(3):
                for gy in range(3):
                    d.rectangle([x - 11 * S + gx * 8 * S, ty + gy * 8 * S, x - 5 * S + gx * 8 * S, ty + 6 * S + gy * 8 * S],
                                fill=col)
        elif k == 1:
            d.rounded_rectangle([x - 11 * S, ty, x + 11 * S, ty + 22 * S], radius=5 * S, outline=col, width=2 * S)
            d.polygon([(x - 4 * S, ty + 6 * S), (x - 4 * S, ty + 16 * S), (x + 5 * S, ty + 11 * S)], fill=col)
        else:
            d.rounded_rectangle([x - 11 * S, ty, x + 11 * S, ty + 22 * S], radius=5 * S, outline=col, width=2 * S)
            d.ellipse([x - 4 * S, ty + 5 * S, x + 4 * S, ty + 13 * S], outline=col, width=2 * S)
    d.line([(0, ty + 26 * S), (W / 3, ty + 26 * S)], fill=FG, width=S)
    top = header_h
    for i, cover in enumerate(covers):
        cw, ch = cover.size
        crop_h = round(cw * 4 / 3)
        tile = cover.crop((0, (ch - crop_h) // 2, cw, (ch - crop_h) // 2 + crop_h)).resize((tile_w, tile_h),
                                                                                           Image.LANCZOS)
        x = (i % 3) * (tile_w + GAP_PT * S)
        y = top + (i // 3) * (tile_h + GAP_PT * S)
        img.paste(tile, (x, y))
        mark = [(x + 8 * S, y + tile_h - 16 * S), (x + 8 * S, y + tile_h - 8 * S), (x + 14 * S, y + tile_h - 12 * S)]
        d.polygon(mark, fill=FG)  # the reel mark Instagram draws on a tile
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--posts", default="state/posts.csv")
    ap.add_argument("--out", default="/tmp/ig-mock")
    ap.add_argument("--n", type=int, default=9)
    args = ap.parse_args()
    font = resolve_font()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    verdicts = latest_verdicts(Path(args.posts), args.n)
    covers = [cover_image(v, font_path=font) for v in verdicts]
    covers[0].save(out / "cover-full.png")
    grid(covers, font).save(out / "ig-grid.png")
    print("\n".join(f"{i + 1}. {v}" for i, v in enumerate(verdicts)))
    print(out / "ig-grid.png", out / "cover-full.png")


if __name__ == "__main__":
    main()
