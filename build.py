# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "cairosvg"]
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

try:
    import cairosvg
    HAVE_CAIROSVG = True
except (ImportError, OSError):
    # cairosvg requires the libcairo C library at runtime; if it's not present
    # we fall back to SVG-only output and tell the user how to fix it.
    HAVE_CAIROSVG = False

ROOT = Path(__file__).parent
SHIRTS_DIR = ROOT / "shirts"
OUTPUT_DIR = ROOT / "output"

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

SERIF_CW = 0.48
SANS_CW = 0.52


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


def wrap_text(text: str, max_w: float, font_size: float, char_w: float = SERIF_CW) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines, cur, cur_w = [], [], 0.0
    space_w = font_size * char_w * 0.6
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
            lines.extend(wrap_text(ln.upper(), max_w, TITLE_FONT, SANS_CW))
    return lines


def render_front_inner(meta, blocks, palette, with_bg=True):
    pad_x = 200
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    out = []
    if with_bg:
        out.append(f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{palette["bg"]}"/>')

    front_heading = meta.get("front_heading", "")

    # font sizes are in px (= svg user units). canvas 3600x6000 = 12"x20" @ 300dpi,
    # divide px by ~4.17 for points. 500 ≈ 120pt, 180 ≈ 43pt, 240 ≈ 58pt.
    verse_font = 180
    cite_font = 72
    closing_font = 240

    heading_zone_bottom = 360
    if front_heading:
        t_lines = title_lines(front_heading, max_w)
        svg, end_y = text_block(
            cx, TITLE_Y, t_lines, TITLE_FONT, palette["body"],
            family=SANS, weight="800", letter_spacing=18,
        )
        out.append(svg)
        rule_y = end_y + TITLE_FONT * 0.55
        rule_w = 700
        out.append(
            f'<line x1="{cx - rule_w // 2}" y1="{rule_y}" '
            f'x2="{cx + rule_w // 2}" y2="{rule_y}" '
            f'stroke="{palette["rule"]}" stroke-width="6"/>'
        )
        heading_zone_bottom = rule_y + 140

    verse_blocks = [b for b in blocks if (b["heading"] or "").lower() != "closing"]
    closing = next((b for b in blocks if (b["heading"] or "").lower() == "closing"), None)

    def block_h(b):
        para = " ".join(b["paragraphs"])
        if "jesus" in b["tags"]:
            para = f"“{para}”"
        n = len(wrap_text(para, max_w, verse_font, SERIF_CW))
        cite_n = len(wrap_text((b["heading"] or "").upper(), max_w, cite_font, SANS_CW))
        return n * verse_font * 1.22 + cite_font * 1.6 + cite_n * cite_font * 1.22

    # Distribute verses across the full vertical space between heading and closing
    # so the design fills the shirt instead of clumping at the chest.
    closing_baseline = CANVAS_H - 360
    closing_top = closing_baseline - closing_font * 0.75 if closing else CANVAS_H - 200
    top_pad = 180
    n_verses = len(verse_blocks)
    content_h = sum(block_h(b) for b in verse_blocks)
    slack = closing_top - heading_zone_bottom - top_pad - content_h - 220  # 220 buffer above closing
    if n_verses > 1:
        inter_gap = max(verse_font * 1.3, slack / (n_verses - 1))
        inter_gap = min(inter_gap, verse_font * 2.6)
    else:
        inter_gap = 0

    y = heading_zone_bottom + top_pad
    for i, b in enumerate(verse_blocks):
        is_jesus = "jesus" in b["tags"]
        color = palette["jesus"] if is_jesus else palette["body"]
        para = " ".join(b["paragraphs"])
        if is_jesus:
            para = f"“{para}”"
        lines = wrap_text(para, max_w, verse_font, SERIF_CW)
        svg, end_y = text_block(cx, y, lines, verse_font, color)
        out.append(svg)
        y = end_y + cite_font * 1.6

        cite = b["heading"].upper() if b["heading"] else ""
        cite_lines = wrap_text(cite, max_w, cite_font, SANS_CW)
        cs, end_y = text_block(
            cx, y, cite_lines, cite_font, palette["citation"],
            family=SANS, weight="600", letter_spacing=10,
        )
        out.append(cs)
        if i < n_verses - 1:
            y = end_y + inter_gap

    if closing:
        para = " ".join(closing["paragraphs"])
        lines = wrap_text(para, max_w, closing_font, SERIF_CW)
        svg, _ = text_block(cx, closing_baseline, lines, closing_font, palette["body"], style="italic")
        out.append(svg)

    return out


def render_back_inner(meta, blocks, palette, with_bg=True):
    pad_x = 200
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    out = []
    if with_bg:
        out.append(f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{palette["bg"]}"/>')

    heading = meta.get("back_heading") or meta.get("title", "")
    sub = meta.get("back_subheading", "")

    h_lines = title_lines(heading, max_w)
    svg, end_y = text_block(
        cx, TITLE_Y, h_lines, TITLE_FONT, palette["body"],
        family=SANS, weight="800", letter_spacing=18,
    )
    out.append(svg)
    y = end_y + TITLE_FONT * 0.55

    if sub:
        s_font = 96
        s_lines = wrap_text(sub, max_w, s_font, SERIF_CW)
        svg, end_y = text_block(cx, y, s_lines, s_font, palette["muted"], style="italic")
        out.append(svg)
        y = end_y + s_font * 1.4

    rule_w = 700
    out.append(
        f'<line x1="{cx - rule_w // 2}" y1="{y}" x2="{cx + rule_w // 2}" '
        f'y2="{y}" stroke="{palette["rule"]}" stroke-width="6"/>'
    )
    y += 200

    body_blocks = [b for b in blocks if (b["heading"] or "").lower() != "closing"]
    closing = next((b for b in blocks if (b["heading"] or "").lower() == "closing"), None)

    body_font = 160
    for body_block in body_blocks:
        for para in body_block["paragraphs"]:
            lines = wrap_text(para, max_w, body_font, SERIF_CW)
            svg, end_y = text_block(cx, y, lines, body_font, palette["body"])
            out.append(svg)
            y = end_y + body_font * 1.95  # extra paragraph separation

    if closing:
        closing_font = 220
        para = " ".join(closing["paragraphs"])
        y += body_font * 0.5
        lines = wrap_text(para, max_w, closing_font, SERIF_CW)
        svg, _ = text_block(cx, y, lines, closing_font, palette["body"], style="italic")
        out.append(svg)

    return out


def render_front(meta, blocks, palette):
    return wrap_svg(render_front_inner(meta, blocks, palette, with_bg=True))


def render_back(meta, blocks, palette):
    return wrap_svg(render_back_inner(meta, blocks, palette, with_bg=True))


# Mockup: shirt silhouette with the design embedded over the chest+torso.
# viewBox 800x880; print region matches canvas aspect (0.667) for full chest-to-belly.
MOCKUP_W, MOCKUP_H = 800, 880
PRINT_X, PRINT_Y, PRINT_W, PRINT_H = 255, 195, 290, 483  # aspect 0.6 to match 3600x6000 canvas


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
        inner = render_front_inner(meta, sections.get("Front", []), palette, with_bg=False)
    else:
        inner = render_back_inner(meta, sections.get("Back", []), palette, with_bg=False)

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
        f'    <svg x="{PRINT_X}" y="{PRINT_Y}" width="{PRINT_W}" height="{PRINT_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" preserveAspectRatio="xMidYMid meet">\n'
        f'      {inner_str}\n'
        f'    </svg>\n'
        f'  </g>\n'
        f'</svg>\n'
    )


def wrap_svg(parts):
    body = "\n".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" '
        f'width="{CANVAS_W}" height="{CANVAS_H}">\n{body}\n</svg>\n'
    )


def build_one(path: Path):
    meta, sections = parse_shirt(path)
    slug = meta["slug"]
    colors = meta.get("colors", ["black"])
    print(f"Building {meta['title']} ({slug}):")
    for color in colors:
        palette = PALETTES[color]
        out_dir = OUTPUT_DIR / slug / color
        out_dir.mkdir(parents=True, exist_ok=True)

        front_blocks = sections.get("Front", [])
        back_blocks = sections.get("Back", [])

        # preview artwork (with shirt-color background) — for visual review
        (out_dir / "front.svg").write_text(render_front(meta, front_blocks, palette))
        (out_dir / "back.svg").write_text(render_back(meta, back_blocks, palette))

        # shirt mockups (silhouette + design)
        (out_dir / "front-mockup.svg").write_text(render_mockup(meta, sections, color, "front"))
        (out_dir / "back-mockup.svg").write_text(render_mockup(meta, sections, color, "back"))

        # print-ready (transparent background) — upload these to POD services
        front_print_svg = wrap_svg(render_front_inner(meta, front_blocks, palette, with_bg=False))
        back_print_svg = wrap_svg(render_back_inner(meta, back_blocks, palette, with_bg=False))
        (out_dir / "front-print.svg").write_text(front_print_svg)
        (out_dir / "back-print.svg").write_text(back_print_svg)

        if HAVE_CAIROSVG:
            cairosvg.svg2png(
                bytestring=front_print_svg.encode("utf-8"),
                write_to=str(out_dir / "front-print.png"),
                output_width=CANVAS_W, output_height=CANVAS_H,
            )
            cairosvg.svg2png(
                bytestring=back_print_svg.encode("utf-8"),
                write_to=str(out_dir / "back-print.png"),
                output_width=CANVAS_W, output_height=CANVAS_H,
            )

        print(f"  - {color}: {out_dir.relative_to(ROOT)}")
    return slug, colors, meta["title"]


def write_preview(designs):
    png_note = "" if HAVE_CAIROSVG else " <em>(PNG not generated — install cairosvg + libcairo)</em>"
    cards = []
    for slug, colors, title in designs:
        for color in colors:
            png_links = (
                f' &middot; <a href="{slug}/{color}/front-print.png">front PNG</a>'
                f' &middot; <a href="{slug}/{color}/back-print.png">back PNG</a>'
            ) if HAVE_CAIROSVG else ""
            cards.append(f'''      <section class="design">
        <h2>{escape(title)} — <span class="meta">{color}</span></h2>
        <div class="pair">
          <figure><img src="{slug}/{color}/front-mockup.svg" alt="front"/><figcaption>front</figcaption></figure>
          <figure><img src="{slug}/{color}/back-mockup.svg" alt="back"/><figcaption>back</figcaption></figure>
        </div>
        <p class="upload">
          Upload to your POD service (transparent, 12&times;20 in @ 300 dpi):
          <a href="{slug}/{color}/front-print.svg">front SVG</a> &middot;
          <a href="{slug}/{color}/back-print.svg">back SVG</a>{png_links}
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
    if not HAVE_CAIROSVG:
        print(
            "\nNote: PNG output skipped (cairosvg / libcairo not available).\n"
            "      To enable PNG generation: brew install cairo pango libffi\n"
            "      Most POD services accept the SVG directly anyway."
        )


if __name__ == "__main__":
    main()
