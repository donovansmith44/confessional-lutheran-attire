# Confessional Lutheran Attire

T-shirt designs that pair Bible passages on the front with the corresponding
explanation from Luther's Small Catechism on the back. The verse hits you,
"Therefore..." flips you over, and you read what we are to make of it.

## How a design is structured

Each shirt lives as a single markdown file in `shirts/`. YAML frontmatter
holds metadata; the body uses `## Front` and `## Back` to split sides, with
`### <citation>` introducing each verse on the front.

```markdown
---
title: The Third Article
slug: third-article
colors: [black, gray]
back_heading: The Third Article
back_subheading: Sanctification
---

## Front

### John 6:44 {jesus}
No one can come to me unless the Father who sent me draws him.

### Ephesians 2:8-9
For by grace you have been saved through faith...

### Closing
Therefore...

## Back

I believe that I cannot by my own reason or strength...
```

### Conventions

- `### <citation> {jesus}` — the `{jesus}` tag renders this verse in red and italic.
- `### Closing` — special section rendered larger and italic at the bottom of the front (e.g. "Therefore...").
- Back side is a single body block (no `###` needed); paragraphs separated by blank lines.
- `colors:` is a list — each entry produces its own pair of SVGs.

## Building

```bash
uv run build.py                  # build every design
uv run build.py third-article    # build one design
open output/preview.html         # see them all
```

Each design produces 8 files per color, in `output/<slug>/<color>/`:

| file                   | purpose                                                  |
|------------------------|----------------------------------------------------------|
| `front-mockup.svg`     | t-shirt silhouette w/ design — visual preview            |
| `back-mockup.svg`      | same, back side                                          |
| `front.svg` / `back.svg` | flat artwork w/ shirt-color background — preview only |
| **`front-print.svg`**  | **upload to POD — transparent vector, 12×20 in**         |
| **`back-print.svg`**   | **upload to POD — transparent vector, back side**        |
| **`front-print.png`**  | **upload to POD — transparent raster, 3600×6000 px**     |
| **`back-print.png`**   | **upload to POD — transparent raster, back side**        |

## Uploading to a print-on-demand service

The `*-print.svg` and `*-print.png` files have a transparent background and
the colors baked in for that specific shirt color. Pick the file matching
your shirt color (`black/` for black tees, `gray/` for gray) and upload
both front and back.

- **Printful, Printify, Spreadshirt** — accept SVG directly (recommended).
- **Bonfire, Custom Ink, Teespring** — usually want PNG. Use `*-print.png`.
- Print area: 12"×20" at 300 dpi. Most services use 12×16 max so they will
  scale down — that's fine, just means even bigger headers in real life.

PNG output requires `cairosvg` + the libcairo C library. On macOS:
`brew install cairo pango libffi`. If unavailable, the build still produces
SVGs and most POD services accept those.

For best font fidelity in PNGs, install [EB Garamond](https://fonts.google.com/specimen/EB+Garamond)
and [Inter](https://fonts.google.com/specimen/Inter) on the rendering
machine. SVGs reference these font names; if absent, system serif/sans
fallbacks are used.

## Color palette

| token       | black shirt | gray shirt |
|-------------|-------------|------------|
| background  | `#171717`   | `#7a7a7a`  |
| body text   | `#f4f1ea`   | `#15161a`  |
| Jesus' words| `#e63946`   | `#8a0e21`  |
| citations   | `#9a948a`   | `#2a2a2a`  |

## Adding a new design

1. Copy an existing file in `shirts/` to a new slug.
2. Swap the verses and the catechism body.
3. `uv run build.py <slug>` and check `output/preview.html`.
