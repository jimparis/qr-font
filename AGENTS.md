# AGENTS.md

Context for future agents working on this repo.

## Project

This project generates an experimental OpenType font that renders bracketed
text as QR Code symbols while keeping surrounding text readable. The generated
font is a Modified Version of Liberation Sans Regular and is licensed under the
SIL Open Font License 1.1.

The current bounded QR target is:

- QR Code Version 1-L
- byte mode
- fixed mask pattern 0
- printable ASCII payloads up to 17 characters per bracketed block
- `[` and `]` delimiters

Example:

```text
Hello [QR coded] world!
Download this font: [http://qr.jim.sh/]
```

## Build

Use `uv` for Python commands and dependency management.

```sh
make
```

`make` runs the full Reed-Solomon parity build, then copies the font, demo,
reference page, license, and notice into `~/Downloads/qrfont/`.

Do not use the placeholder parity path for normal verification. It exists only
as a legacy layout-debug target:

```sh
make fast-placeholder
```

The generator defaults to:

```text
/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
```

Use `--base-font` to test another compatible TrueType base font.

## Important Implementation Details

- `tools/build_font.py` is the source of truth. It emits glyph outlines,
  OpenType feature code, HTML demo, and SVG reference output.
- Printable ASCII glyphs are copied from Liberation Sans and scaled down with
  `LATIN_SCALE`, so normal text can surround QR blocks in the same font.
- Latin advances are snapped to 100 font-unit increments. This helps QR blocks
  start on the QR module grid after ordinary text.
- QR modules are drawn as slightly overpainted rectangles. Current
  `MODULE_OVERPAINT` is intentional: it hides faint gray seams between QR
  helper glyph layers.
- QR helper glyphs carry a tiny no-op TrueType program (`PUSHB[1] 0`, `POP[]`).
  This was added after Chrome/Firefox showed one-pixel offsets between adjacent
  rectangles. The no-op program plus smoothing-only `gasp` table worked much
  better than grid-fitting.
- The current `gasp` table intentionally avoids grid-fit flags and uses
  grayscale/symmetric smoothing only.

## Verification

Lightweight checks:

```sh
uv run tools/shape_debug.py 'Hello [QR coded] world!' 'Download this font: [http://qr.jim.sh/]'
```

For QR matrix correctness, compare `matrix_for_text()` against an independent
QR encoder in byte mode, version 1, level L, mask 0. Previous checks used:

```sh
uv run --with qrcode[pil] python ...
```

Browser rendering is useful but time-consuming. The user asked to skip routine
Firefox rendering for now. If visual alignment regresses, inspect recent
screenshots in `~/Downloads`.

## Larger QR Codes

Version 1-L only supports 17 byte-mode characters. Larger QR versions are
possible, but the current implementation hardcodes Version 1 data capacity,
coordinate placement, format layout, and Reed-Solomon parity size. Extending to
larger versions means generating additional version-specific coordinate maps,
capacity tables, RS block structures, alignment patterns, and much larger
OpenType state/parity circuits.
