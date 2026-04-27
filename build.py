# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "resvg-py"]
# ///
"""
Build SVG artwork for confessional Lutheran shirt designs.

Reads each markdown file in shirts/ and writes:
  output/<slug>/<color>/front.svg
  output/<slug>/<color>/back.svg
  output/preview.html  (loads every generated SVG side-by-side)

Run: uv run build.py            # build every design
     uv run build.py third-article    # build one design
"""
import re
import sys
from pathlib import Path
import yaml

# resvg-py renders SVG → PNG with proper @font-face / system font handling
# (cairosvg can't — it uses cairo's "toy" font API which ignores real font
# names). Bundled fonts live in fonts/ and are passed via font_dirs.
_PROJECT_DIR = Path(__file__).parent.resolve()
_FONTS_DIR = _PROJECT_DIR / "fonts"

try:
    import resvg_py
    HAVE_PNG = True
except ImportError:
    HAVE_PNG = False

ROOT = Path(__file__).parent
SHIRTS_DIR = ROOT / "shirts"
OUTPUT_DIR = ROOT / "output"   # preview/mockup artifacts (gitignored)
PRINTS_DIR = ROOT / "prints"   # upload-ready files (tracked in git)

CANVAS_W = 3600
CANVAS_H = 6000  # 12"x20" @ 300dpi — tall enough for big-headline + big-verse layout

PALETTES = {
    "black": {
        "bg": "#171717",
        "body": "#f4f1ea",
        "jesus": "#e63946",
        "citation": "#9a948a",
        "muted": "#8a857c",
        "rule": "#3a3733",
    },
    "gray": {
        "bg": "#7a7a7a",
        "body": "#15161a",
        "jesus": "#8a0e21",
        "citation": "#2a2a2a",
        "muted": "#2f2f2f",
        "rule": "#4a4a4a",
    },
}

SERIF = "'EB Garamond', 'Garamond', 'Hoefler Text', 'Times New Roman', serif"
SANS = "'Inter', 'Helvetica Neue', 'Arial', sans-serif"
TITLE_FAMILY = "'Archivo Black', 'Inter', 'Helvetica Neue', 'Arial Black', sans-serif"

SERIF_CW = 0.48
SANS_CW = 0.52
TITLE_CW = 0.58  # Archivo Black is heavier and wider per char than Inter


def parse_shirt(path: Path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"No YAML frontmatter in {path}")
    meta = yaml.safe_load(m.group(1))
    body = m.group(2)

    sections: dict[str, list[dict]] = {}
    cur_section = None
    cur_block = None

    for line in body.splitlines():
        h2 = re.match(r"^##\s+(\S.*?)\s*$", line)
        h3 = re.match(r"^###\s+(.*?)\s*$", line)
        if h2:
            cur_section = h2.group(1).strip()
            sections.setdefault(cur_section, [])
            cur_block = None
            continue
        if h3 and cur_section is not None:
            heading = h3.group(1).strip()
            tags: set[str] = set()
            tm = re.search(r"\{([^}]+)\}\s*$", heading)
            if tm:
                tags = {t.strip() for t in tm.group(1).split(",")}
                heading = heading[: tm.start()].strip()
            cur_block = {"heading": heading, "tags": tags, "lines": []}
            sections[cur_section].append(cur_block)
            continue
        if cur_section is not None:
            if cur_block is None:
                if line.strip() == "":
                    continue
                cur_block = {"heading": None, "tags": set(), "lines": []}
                sections[cur_section].append(cur_block)
            cur_block["lines"].append(line)

    for blocks in sections.values():
        for b in blocks:
            paras, buf = [], []
            for ln in b["lines"]:
                if ln.strip() == "":
                    if buf:
                        paras.append(" ".join(buf).strip())
                        buf = []
                else:
                    buf.append(ln.strip())
            if buf:
                paras.append(" ".join(buf).strip())
            b["paragraphs"] = paras

    return meta, sections


def wrap_text(text: str, max_w: float, font_size: float, char_w: float = SERIF_CW,
              min_last_words: int = 4) -> list[str]:
    words = text.split()
    if not words:
        return []
    space_w = font_size * char_w * 0.6

    def line_w(ws: list[str]) -> float:
        if not ws:
            return 0.0
        return sum(len(w) * font_size * char_w for w in ws) + (len(ws) - 1) * space_w

    lines, cur, cur_w = [], [], 0.0
    for w in words:
        ww = len(w) * font_size * char_w
        add = ww if not cur else ww + space_w
        if cur and cur_w + add > max_w:
            lines.append(" ".join(cur))
            cur, cur_w = [w], ww
        else:
            cur.append(w)
            cur_w += add
    if cur:
        lines.append(" ".join(cur))

    # Widow prevention: pull words up from the second-to-last line into the last
    # line until it has at least min_last_words. Don't strip the prior line below
    # 3 words, and don't push the last line past max_w.
    if len(lines) >= 2:
        prev_w = lines[-2].split()
        last_w = lines[-1].split()
        while len(last_w) < min_last_words and len(prev_w) > 3:
            candidate = [prev_w[-1]] + last_w
            if line_w(candidate) > max_w:
                break
            last_w = candidate
            prev_w.pop()
        lines[-2] = " ".join(prev_w)
        lines[-1] = " ".join(last_w)

    return lines


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_block(x, y, lines, size, color, family=SERIF, weight="normal", style="normal", anchor="middle", letter_spacing=0):
    line_h = size * 1.22
    parts = [
        f'<text x="{x}" y="{y}" fill="{color}" font-family="{family}" '
        f'font-size="{size}" font-weight="{weight}" font-style="{style}" '
        f'text-anchor="{anchor}" letter-spacing="{letter_spacing}">'
    ]
    for i, ln in enumerate(lines):
        dy = 0 if i == 0 else line_h
        parts.append(f'<tspan x="{x}" dy="{dy}">{escape(ln)}</tspan>')
    parts.append("</text>")
    end_y = y + line_h * (len(lines) - 1)
    return "\n".join(parts), end_y


TITLE_Y = 540
TITLE_FONT = 500  # ~1.7" tall on the print — readable across a room


def title_lines(text: str, max_w: float) -> list[str]:
    """Split a heading on YAML newlines (manual breaks) and auto-wrap each chunk."""
    lines: list[str] = []
    for ln in (text or "").split("\n"):
        ln = ln.strip()
        if ln:
            lines.extend(wrap_text(ln.upper(), max_w, TITLE_FONT, TITLE_CW))
    return lines


BOTTOM_MARGIN = 280  # whitespace below the last element in a side


def render_front_layout(meta, blocks, palette, with_bg=True):
    """Render the front design. Returns (parts, canvas_height)."""
    pad_x = 200
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    front_heading = meta.get("front_heading", "")

    # font sizes are in px (= svg user units); divide by ~4.17 for points.
    # 500 ≈ 120pt, 180 ≈ 43pt, 240 ≈ 58pt.
    verse_font = 180
    cite_font = 72
    closing_font = 240

    content: list[str] = []
    y = TITLE_Y
    if front_heading:
        t_lines = title_lines(front_heading, max_w)
        svg, end_y = text_block(
            cx, y, t_lines, TITLE_FONT, palette["body"],
            family=TITLE_FAMILY, weight="900", letter_spacing=8,
        )
        content.append(svg)
        rule_y = end_y + TITLE_FONT * 0.5
        rule_w = 320
        content.append(
            f'<line x1="{cx - rule_w // 2}" y1="{rule_y}" '
            f'x2="{cx + rule_w // 2}" y2="{rule_y}" '
            f'stroke="{palette["rule"]}" stroke-width="3" stroke-opacity="0.7"/>'
        )
        y = rule_y + TITLE_FONT * 0.5

    verse_blocks = [b for b in blocks if (b["heading"] or "").lower() != "closing"]
    closing = next((b for b in blocks if (b["heading"] or "").lower() == "closing"), None)

    last_y = y
    for i, b in enumerate(verse_blocks):
        is_jesus = "jesus" in b["tags"]
        color = palette["jesus"] if is_jesus else palette["body"]
        para = " ".join(b["paragraphs"])
        if is_jesus:
            para = f"“{para}”"
        lines = wrap_text(para, max_w, verse_font, SERIF_CW)
        svg, end_y = text_block(cx, y, lines, verse_font, color)
        content.append(svg)
        y = end_y + cite_font * 1.6

        cite = b["heading"].upper() if b["heading"] else ""
        cite_lines = wrap_text(cite, max_w, cite_font, SANS_CW)
        cs, end_y = text_block(
            cx, y, cite_lines, cite_font, palette["citation"],
            family=SANS, weight="600", letter_spacing=10,
        )
        content.append(cs)
        last_y = end_y
        if i < len(verse_blocks) - 1:
            y = end_y + verse_font * 1.55  # gap between verses

    if closing:
        para = " ".join(closing["paragraphs"])
        y = last_y + closing_font * 1.6  # snug gap so "Therefore..." stays near verses
        lines = wrap_text(para, max_w, closing_font, SERIF_CW)
        svg, end_y = text_block(cx, y, lines, closing_font, palette["body"], style="italic")
        content.append(svg)
        last_y = end_y

    height = int(last_y + BOTTOM_MARGIN)
    parts: list[str] = []
    if with_bg:
        parts.append(f'<rect width="{CANVAS_W}" height="{height}" fill="{palette["bg"]}"/>')
    parts.extend(content)
    return parts, height


def render_back_layout(meta, blocks, palette, with_bg=True):
    """Render the back design. Returns (parts, canvas_height)."""
    pad_x = 200
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    heading = meta.get("back_heading") or meta.get("title", "")
    sub = meta.get("back_subheading", "")
    body_font = 160

    content: list[str] = []
    y = TITLE_Y
    h_lines = title_lines(heading, max_w)
    svg, end_y = text_block(
        cx, y, h_lines, TITLE_FONT, palette["body"],
        family=TITLE_FAMILY, weight="900", letter_spacing=8,
    )
    content.append(svg)
    rule_y = end_y + TITLE_FONT * 0.5
    rule_w = 320
    content.append(
        f'<line x1="{cx - rule_w // 2}" y1="{rule_y}" '
        f'x2="{cx + rule_w // 2}" y2="{rule_y}" '
        f'stroke="{palette["rule"]}" stroke-width="3" stroke-opacity="0.7"/>'
    )
    y = rule_y + TITLE_FONT * 0.5

    if sub:
        s_font = 96
        s_lines = wrap_text(sub, max_w, s_font, SERIF_CW)
        svg, end_y = text_block(cx, y, s_lines, s_font, palette["muted"], style="italic")
        content.append(svg)
        y = end_y + s_font * 1.4

    body_blocks = [b for b in blocks if (b["heading"] or "").lower() != "closing"]
    closing = next((b for b in blocks if (b["heading"] or "").lower() == "closing"), None)

    last_y = y
    for body_block in body_blocks:
        for para in body_block["paragraphs"]:
            lines = wrap_text(para, max_w, body_font, SERIF_CW)
            svg, end_y = text_block(cx, y, lines, body_font, palette["body"])
            content.append(svg)
            last_y = end_y
            y = end_y + body_font * 1.95  # extra paragraph separation

    if closing:
        closing_font = 220
        para = " ".join(closing["paragraphs"])
        y = last_y + closing_font * 1.6
        lines = wrap_text(para, max_w, closing_font, SERIF_CW)
        svg, end_y = text_block(cx, y, lines, closing_font, palette["body"], style="italic")
        content.append(svg)
        last_y = end_y

    height = int(last_y + BOTTOM_MARGIN)
    parts: list[str] = []
    if with_bg:
        parts.append(f'<rect width="{CANVAS_W}" height="{height}" fill="{palette["bg"]}"/>')
    parts.extend(content)
    return parts, height


# legacy aliases used elsewhere
def render_front_inner(meta, blocks, palette, with_bg=True):
    parts, _ = render_front_layout(meta, blocks, palette, with_bg)
    return parts


def render_back_inner(meta, blocks, palette, with_bg=True):
    parts, _ = render_back_layout(meta, blocks, palette, with_bg)
    return parts


def render_front(meta, blocks, palette):
    parts, h = render_front_layout(meta, blocks, palette, with_bg=True)
    return wrap_svg(parts, h)


def render_back(meta, blocks, palette):
    parts, h = render_back_layout(meta, blocks, palette, with_bg=True)
    return wrap_svg(parts, h)


# Mockup: shirt silhouette with the design embedded over the chest+torso.
# Print box width is fixed; height is computed per-design from the canvas height
# returned by the layout function (so each shirt's print box matches its design).
MOCKUP_W, MOCKUP_H = 800, 880
PRINT_X, PRINT_Y, PRINT_W = 255, 285, 290  # PRINT_Y bumped down so the header doesn't sit on the collar


def shirt_path(side: str) -> str:
    """SVG path approximating a t-shirt outline. Front has a deeper neck scoop."""
    scoop = 62 if side == "front" else 24
    return (
        # collar top-left → smooth shoulder slope to shoulder peak
        "M 340 100 "
        "C 318 86 285 90 263 112 "
        # around shoulder into top of sleeve outer
        "C 240 132 200 152 175 178 "
        # sleeve outer side, slight outward flare
        "L 130 358 "
        # cuff: rounded outer corner, bottom, rounded inner corner
        "Q 122 384 145 386 "
        "L 233 386 "
        "Q 252 384 248 360 "
        # sleeve underarm curve back into body at the armpit
        "C 250 320 248 268 240 248 "
        # body left side down (very slight taper)
        "L 240 760 "
        # rounded hem corner left
        "Q 240 782 263 782 "
        # hem
        "L 537 782 "
        # rounded hem corner right
        "Q 560 782 560 760 "
        # body right side up to right armpit
        "L 560 248 "
        # right underarm curve out to sleeve cuff inner
        "C 552 268 550 320 552 360 "
        "Q 548 384 567 386 "
        "L 655 386 "
        "Q 678 384 670 358 "
        # sleeve outer up to right shoulder
        "L 625 178 "
        "C 600 152 560 132 537 112 "
        # shoulder slope to right collar top
        "C 515 90 482 86 460 100 "
        # neck scoop back to start (deeper for front, shallow for back)
        f"C 440 {100 + scoop} 360 {100 + scoop} 340 100 "
        "Z"
    )


def render_mockup(meta, sections, color, side):
    palette = PALETTES[color]
    if side == "front":
        inner, design_h = render_front_layout(meta, sections.get("Front", []), palette, with_bg=False)
    else:
        inner, design_h = render_back_layout(meta, sections.get("Back", []), palette, with_bg=False)

    # let print box match the design's natural aspect; clamp only if it would
    # push past the shirt hem.
    natural_h = PRINT_W * design_h / CANVAS_W
    max_h = MOCKUP_H - PRINT_Y - 130  # leave room above the hem
    print_h = min(natural_h, max_h)
    inner_str = "\n      ".join(inner)
    backdrop = "#1d1d1d"
    # subtle vertical shading on the shirt fabric for a hint of depth
    shade_id = f"shade-{color}-{side}"
    highlight_alpha = 0.12 if color == "black" else 0.08
    shadow_alpha = 0.22 if color == "black" else 0.18
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MOCKUP_W} {MOCKUP_H}" '
        f'width="{MOCKUP_W}" height="{MOCKUP_H}">\n'
        f'  <defs>\n'
        f'    <linearGradient id="{shade_id}" x1="0" y1="0" x2="0" y2="1">\n'
        f'      <stop offset="0%" stop-color="white" stop-opacity="{highlight_alpha}"/>\n'
        f'      <stop offset="55%" stop-color="white" stop-opacity="0"/>\n'
        f'      <stop offset="100%" stop-color="black" stop-opacity="{shadow_alpha}"/>\n'
        f'    </linearGradient>\n'
        f'    <filter id="drop" x="-10%" y="-10%" width="120%" height="120%">\n'
        f'      <feDropShadow dx="0" dy="6" stdDeviation="10" flood-opacity="0.35"/>\n'
        f'    </filter>\n'
        f'    <clipPath id="clip-{side}"><path d="{shirt_path(side)}"/></clipPath>\n'
        f'  </defs>\n'
        f'  <rect width="{MOCKUP_W}" height="{MOCKUP_H}" fill="{backdrop}"/>\n'
        f'  <path d="{shirt_path(side)}" fill="{palette["bg"]}" '
        f'stroke="rgba(0,0,0,0.45)" stroke-width="1.5" filter="url(#drop)"/>\n'
        f'  <path d="{shirt_path(side)}" fill="url(#{shade_id})"/>\n'
        f'  <g clip-path="url(#clip-{side})">\n'
        f'    <svg x="{PRINT_X}" y="{PRINT_Y}" width="{PRINT_W}" height="{print_h:.1f}" '
        f'viewBox="0 0 {CANVAS_W} {design_h}" preserveAspectRatio="xMidYMin meet">\n'
        f'      {inner_str}\n'
        f'    </svg>\n'
        f'  </g>\n'
        f'</svg>\n'
    )


def wrap_svg(parts, height=None):
    h = height if height is not None else CANVAS_H
    body = "\n".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {h}" '
        f'width="{CANVAS_W}" height="{h}">\n{body}\n</svg>\n'
    )


def build_one(path: Path):
    meta, sections = parse_shirt(path)
    slug = meta["slug"]
    colors = meta.get("colors", ["black"])
    print(f"Building {meta['title']} ({slug}):")
    for color in colors:
        palette = PALETTES[color]
        out_dir = OUTPUT_DIR / slug / color
        prints_dir = PRINTS_DIR / slug / color
        out_dir.mkdir(parents=True, exist_ok=True)
        prints_dir.mkdir(parents=True, exist_ok=True)

        front_blocks = sections.get("Front", [])
        back_blocks = sections.get("Back", [])

        # preview artwork (with shirt-color background) — for visual review
        (out_dir / "front.svg").write_text(render_front(meta, front_blocks, palette))
        (out_dir / "back.svg").write_text(render_back(meta, back_blocks, palette))

        # shirt mockups (silhouette + design)
        (out_dir / "front-mockup.svg").write_text(render_mockup(meta, sections, color, "front"))
        (out_dir / "back-mockup.svg").write_text(render_mockup(meta, sections, color, "back"))

        # print-ready (transparent bg) — written to tracked prints/<slug>/<color>/
        front_parts, front_h = render_front_layout(meta, front_blocks, palette, with_bg=False)
        back_parts, back_h = render_back_layout(meta, back_blocks, palette, with_bg=False)
        front_print_svg = wrap_svg(front_parts, front_h)
        back_print_svg = wrap_svg(back_parts, back_h)
        (prints_dir / "front.svg").write_text(front_print_svg)
        (prints_dir / "back.svg").write_text(back_print_svg)

        if HAVE_PNG:
            font_dirs = [str(_FONTS_DIR)] if _FONTS_DIR.exists() else None
            (prints_dir / "front.png").write_bytes(bytes(resvg_py.svg_to_bytes(
                svg_string=front_print_svg, font_dirs=font_dirs,
                width=CANVAS_W, height=front_h,
            )))
            (prints_dir / "back.png").write_bytes(bytes(resvg_py.svg_to_bytes(
                svg_string=back_print_svg, font_dirs=font_dirs,
                width=CANVAS_W, height=back_h,
            )))

        print(f"  - {color}: preview→{out_dir.relative_to(ROOT)}  prints→{prints_dir.relative_to(ROOT)}")
    return slug, colors, meta["title"]


def write_preview(designs):
    cards = []
    for slug, colors, title in designs:
        for color in colors:
            png_links = (
                f' &middot; <a href="../prints/{slug}/{color}/front.png">front PNG</a>'
                f' &middot; <a href="../prints/{slug}/{color}/back.png">back PNG</a>'
            ) if HAVE_PNG else ""
            cards.append(f'''      <section class="design">
        <h2>{escape(title)} — <span class="meta">{color}</span></h2>
        <div class="pair">
          <figure><img src="{slug}/{color}/front-mockup.svg" alt="front"/><figcaption>front</figcaption></figure>
          <figure><img src="{slug}/{color}/back-mockup.svg" alt="back"/><figcaption>back</figcaption></figure>
        </div>
        <p class="upload">
          Upload to your POD service (transparent, 12 in wide @ 300 dpi):
          <a href="../prints/{slug}/{color}/front.svg">front SVG</a> &middot;
          <a href="../prints/{slug}/{color}/back.svg">back SVG</a>{png_links}
        </p>
        <details>
          <summary>preview artwork (with shirt color filled)</summary>
          <div class="pair art">
            <figure><img src="{slug}/{color}/front.svg" alt="front art"/><figcaption>front</figcaption></figure>
            <figure><img src="{slug}/{color}/back.svg" alt="back art"/><figcaption>back</figcaption></figure>
          </div>
        </details>
      </section>''')
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Confessional Lutheran Attire — preview</title>
<style>
  body {{ background:#181818; color:#eee; font:16px/1.5 -apple-system, system-ui, sans-serif; margin:0; padding:32px; }}
  h1 {{ font-weight:300; letter-spacing:.04em; margin:0 0 32px; }}
  .design {{ margin:64px 0; }}
  .design h2 {{ font-weight:500; letter-spacing:.06em; text-transform:uppercase; font-size:13px; color:#bbb; margin:0 0 16px; }}
  .meta {{ color:#888; }}
  .pair {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  figure {{ margin:0; border-radius:6px; overflow:hidden; }}
  .pair > figure {{ background:transparent; }}
  .art figure {{ background:#000; }}
  figcaption {{ padding:6px 12px; font-size:11px; color:#888; text-transform:uppercase; letter-spacing:.12em; }}
  img {{ display:block; width:100%; height:auto; }}
  details {{ margin-top:16px; }}
  summary {{ cursor:pointer; color:#888; font-size:12px; letter-spacing:.05em; padding:6px 0; }}
  summary:hover {{ color:#ccc; }}
  .upload {{ font-size:12px; color:#aaa; letter-spacing:.04em; margin:14px 0 0; }}
  .upload a {{ color:#9bd; text-decoration:none; border-bottom:1px dotted #557; }}
  .upload a:hover {{ color:#cef; }}
</style>
</head>
<body>
  <h1>Confessional Lutheran Attire</h1>
{chr(10).join(cards)}
</body>
</html>
'''
    (OUTPUT_DIR / "preview.html").write_text(html)


def main():
    args = sys.argv[1:]
    if args:
        targets = []
        for a in args:
            p = Path(a)
            if not p.exists():
                p = SHIRTS_DIR / (a if a.endswith(".md") else a + ".md")
            targets.append(p)
    else:
        targets = sorted(SHIRTS_DIR.glob("*.md"))

    designs = [build_one(t) for t in targets]
    write_preview(designs)
    print(f"\nPreview: open {OUTPUT_DIR.relative_to(ROOT)}/preview.html")
    if not HAVE_PNG:
        print(
            "\nNote: PNG output skipped (resvg-py not available).\n"
            "      Install with: uv pip install resvg-py\n"
            "      Most POD services accept the SVG directly anyway."
        )


if __name__ == "__main__":
    main()
