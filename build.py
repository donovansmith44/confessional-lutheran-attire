# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
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

ROOT = Path(__file__).parent
SHIRTS_DIR = ROOT / "shirts"
OUTPUT_DIR = ROOT / "output"

CANVAS_W = 3600
CANVAS_H = 4500

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


def render_front(meta, blocks, palette):
    pad_x = 300
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    out = [f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{palette["bg"]}"/>']

    verse_blocks = [b for b in blocks if (b["heading"] or "").lower() != "closing"]
    closing = next((b for b in blocks if (b["heading"] or "").lower() == "closing"), None)

    verse_font = 78
    cite_font = 40
    closing_font = 110

    y = 600
    for b in verse_blocks:
        is_jesus = "jesus" in b["tags"]
        color = palette["jesus"] if is_jesus else palette["body"]
        para = " ".join(b["paragraphs"])
        if is_jesus:
            para = f"“{para}”"
        lines = wrap_text(para, max_w, verse_font, SERIF_CW)
        svg, end_y = text_block(
            cx, y, lines, verse_font, color,
            style="italic" if is_jesus else "normal",
        )
        out.append(svg)
        y = end_y + verse_font * 0.95

        cite = b["heading"].upper() if b["heading"] else ""
        cite_lines = wrap_text(cite, max_w, cite_font, SANS_CW)
        cs, end_y = text_block(
            cx, y, cite_lines, cite_font, palette["citation"],
            family=SANS, weight="600", letter_spacing=10,
        )
        out.append(cs)
        y = end_y + cite_font * 2.6

    if closing:
        para = " ".join(closing["paragraphs"])
        y = max(y + 200, CANVAS_H - 700)
        lines = wrap_text(para, max_w, closing_font, SERIF_CW)
        svg, _ = text_block(cx, y, lines, closing_font, palette["body"], style="italic")
        out.append(svg)

    return wrap_svg(out)


def render_back(meta, blocks, palette):
    pad_x = 240
    cx = CANVAS_W // 2
    max_w = CANVAS_W - 2 * pad_x

    out = [f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{palette["bg"]}"/>']

    heading = meta.get("back_heading") or meta.get("title", "")
    sub = meta.get("back_subheading", "")

    y = 480
    h_font = 140
    h_lines = wrap_text(heading.upper(), max_w, h_font, SANS_CW)
    svg, end_y = text_block(
        cx, y, h_lines, h_font, palette["body"],
        family=SANS, weight="800", letter_spacing=18,
    )
    out.append(svg)
    y = end_y + h_font * 1.1

    if sub:
        s_font = 64
        s_lines = wrap_text(sub, max_w, s_font, SERIF_CW)
        svg, end_y = text_block(cx, y, s_lines, s_font, palette["muted"], style="italic")
        out.append(svg)
        y = end_y + s_font * 1.6

    rule_w = 360
    out.append(
        f'<line x1="{cx - rule_w // 2}" y1="{y}" x2="{cx + rule_w // 2}" '
        f'y2="{y}" stroke="{palette["rule"]}" stroke-width="3"/>'
    )
    y += 130

    body_block = blocks[0] if blocks else None
    if body_block:
        body_font = 66
        for para in body_block["paragraphs"]:
            lines = wrap_text(para, max_w, body_font, SERIF_CW)
            svg, end_y = text_block(cx, y, lines, body_font, palette["body"])
            out.append(svg)
            y = end_y + body_font * 1.6

    return wrap_svg(out)


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
        (out_dir / "front.svg").write_text(render_front(meta, sections.get("Front", []), palette))
        (out_dir / "back.svg").write_text(render_back(meta, sections.get("Back", []), palette))
        print(f"  - {color}: {out_dir.relative_to(ROOT)}")
    return slug, colors, meta["title"]


def write_preview(designs):
    cards = []
    for slug, colors, title in designs:
        for color in colors:
            cards.append(f'''      <section class="design">
        <h2>{escape(title)} — <span class="meta">{color}</span></h2>
        <div class="pair">
          <figure><img src="{slug}/{color}/front.svg" alt="front"/><figcaption>front</figcaption></figure>
          <figure><img src="{slug}/{color}/back.svg" alt="back"/><figcaption>back</figcaption></figure>
        </div>
      </section>''')
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Confessional Lutheran Attire — preview</title>
<style>
  body {{ background:#202020; color:#eee; font:16px/1.5 -apple-system, system-ui, sans-serif; margin:0; padding:32px; }}
  h1 {{ font-weight:300; letter-spacing:.04em; margin:0 0 24px; }}
  .design {{ margin:48px 0; }}
  .design h2 {{ font-weight:500; letter-spacing:.06em; text-transform:uppercase; font-size:14px; color:#bbb; }}
  .meta {{ color:#888; }}
  .pair {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  figure {{ margin:0; background:#000; border-radius:6px; overflow:hidden; }}
  figcaption {{ padding:6px 12px; font-size:12px; color:#888; text-transform:uppercase; letter-spacing:.1em; }}
  img {{ display:block; width:100%; height:auto; }}
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


if __name__ == "__main__":
    main()
