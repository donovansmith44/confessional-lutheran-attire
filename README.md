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

Two output trees:

```
prints/<slug>/<color>/   ← upload these to POD services (tracked in git)
  front.svg              transparent vector, 12 in wide @ 300 dpi
  back.svg               same, back side
  front.png              transparent raster, 3600 px wide @ 300 dpi
  back.png               same, back side

output/<slug>/<color>/   ← preview/mockup artifacts (gitignored)
  front-mockup.svg       shirt silhouette w/ design
  back-mockup.svg
  front.svg / back.svg   flat artwork w/ shirt-color background (visual review)
output/preview.html      browser preview, all designs side-by-side
```

Canvas height is sized to the design — the front (5 verses + closing) ends
up taller than the back (catechism). Width is fixed at 12 in.

## Uploading to a print-on-demand service

Pick the folder matching your shirt color (`prints/<slug>/black/` for black
tees, `prints/<slug>/gray/` for gray) and upload both front and back.

- **Printful, Printify, Spreadshirt** — accept SVG directly (recommended).
- **Bonfire, Custom Ink, Teespring** — usually want PNG.
- Print area: 12 in wide. Most services cap height at ~16 in, so they will
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
