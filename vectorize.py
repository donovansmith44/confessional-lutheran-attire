# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy"]
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


def vectorize(src: str, dst: str, scale: int = 4) -> None:
    g = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise SystemExit(f"can't read {src}")
    h, w = g.shape
    _, binv = cv2.threshold(g, 128, 255, cv2.THRESH_BINARY_INV)  # ink = 255
    cnts, hier = cv2.findContours(binv, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    hier = hier[0]
    canvas = np.full((h * scale, w * scale), 255, np.uint8)
    # fill outer ink contours black first, then carve holes back to white
    for want_outer in (True, False):
        for i, c in enumerate(cnts):
            is_outer = hier[i][3] == -1
            if is_outer != want_outer:
                continue
            cs = np.round(c.astype(np.float64) * scale).astype(np.int32)
            col = 0 if is_outer else 255
            cv2.drawContours(canvas, [cs], -1, col, thickness=cv2.FILLED, lineType=cv2.LINE_AA)
    cv2.imwrite(dst, canvas)
    print(f"{src} {w}x{h} -> {dst} {w * scale}x{h * scale} ({len(cnts)} contours)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + "-hires.png"
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    vectorize(src, dst, scale)
