# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy", "pillow"]
# ///
"""Vectorize-upscale black-on-white line art for crisp printing.

AI-generated line art tends to come out ~1024px wide, which at shirt size is
only ~85 PPI — below Printful's 150 DPI floor, so the lines print soft. This
traces the ink into contours and redraws them at a higher scale with
anti-aliased edges, so the linework stays crisp at any print size while the
composition is left untouched. Holes (e.g. the inside of the stone ring) are
preserved via the contour hierarchy.

Usage:
    python vectorize.py input.png [output.png] [scale]

Defaults: output = <input>-hires.png, scale = 4.
"""
import sys
import cv2
import numpy as np
from PIL import Image


def _ink_contours(inkbin: np.ndarray, scale: int) -> np.ndarray:
    """Trace a binary ink mask (ink = 255) into contours and redraw filled at
    `scale`, carving holes back to white via the contour hierarchy. Returns a
    grayscale canvas (black ink on white)."""
    h, w = inkbin.shape
    cnts, hier = cv2.findContours(inkbin, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    canvas = np.full((h * scale, w * scale), 255, np.uint8)
    if hier is None:
        return canvas
    hier = hier[0]
    # fill outer ink contours black first, then carve holes back to white
    for want_outer in (True, False):
        for i, c in enumerate(cnts):
            is_outer = hier[i][3] == -1
            if is_outer != want_outer:
                continue
            cs = np.round(c.astype(np.float64) * scale).astype(np.int32)
            col = 0 if is_outer else 255
            cv2.drawContours(canvas, [cs], -1, col, thickness=cv2.FILLED, lineType=cv2.LINE_AA)
    return canvas


def _gold_mask(rgb: np.ndarray) -> np.ndarray:
    """Boolean mask of warm/gold pixels (e.g. coloured light rays): warmer than
    blue, reasonably saturated, and neither near-white nor near-black."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (r > 120) & (g > 90) & ((r + g) / 2 - b > 35) & (lum > 60) & (lum < 235)


def vectorize(src: str, dst: str, scale: int = 4) -> None:
    g = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise SystemExit(f"can't read {src}")
    h, w = g.shape
    _, binv = cv2.threshold(g, 128, 255, cv2.THRESH_BINARY_INV)  # ink = 255
    canvas = _ink_contours(binv, scale)
    cv2.imwrite(dst, canvas)
    print(f"{src} {w}x{h} -> {dst} {w * scale}x{h * scale} (b/w)")


def vectorize_color(src: str, dst: str, scale: int = 4) -> None:
    """Like vectorize(), but for line art that carries a gold/warm accent (e.g.
    coloured light rays). The black linework is traced crisp as usual; the gold
    pixels are kept in colour and laid over the linework (LANCZOS-upscaled), so
    the accent survives the upscale instead of collapsing to black."""
    rgb = np.asarray(Image.open(src).convert("RGB")).astype(int)
    h, w = rgb.shape[:2]
    gold = _gold_mask(rgb)
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    ink = (lum < 110) & ~gold

    base = np.stack([_ink_contours(np.where(ink, 255, 0).astype(np.uint8), scale)] * 3, -1)

    gold_src = np.full((h, w, 3), 255, np.uint8)
    gold_src[gold] = rgb[gold].astype(np.uint8)
    gold_up = np.asarray(
        Image.fromarray(gold_src).resize((w * scale, h * scale), Image.LANCZOS)
    ).astype(int)
    glum = 0.299 * gold_up[..., 0] + 0.587 * gold_up[..., 1] + 0.114 * gold_up[..., 2]
    out = base.copy()
    out[glum < 245] = gold_up[glum < 245]
    Image.fromarray(out.astype(np.uint8)).save(dst)
    print(f"{src} {w}x{h} -> {dst} {w * scale}x{h * scale} ({int(gold.sum())} gold px)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + "-hires.png"
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    # Auto-detect gold/warm accents: if the art has a meaningful patch of them,
    # preserve their colour; otherwise treat it as plain black-on-white line art.
    rgb = np.asarray(Image.open(src).convert("RGB")).astype(int)
    if _gold_mask(rgb).sum() > 0.0005 * rgb.shape[0] * rgb.shape[1]:
        vectorize_color(src, dst, scale)
    else:
        vectorize(src, dst, scale)
