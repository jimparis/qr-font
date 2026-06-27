# QR Font

This repo generates an experimental OpenType font that turns bracket-delimited
text into a QR Code symbol while leaving surrounding text readable.

```text
abc[hello]ghi
```

The first target is intentionally bounded:

- QR Code Version 1-L, 21 by 21 modules
- byte mode
- printable ASCII input, up to 17 characters
- fixed mask pattern 0
- `[` and `]` as delimiters

The font is generated rather than hand-authored. The build script emits glyph
outlines and GSUB feature logic, then compiles them into `dist/qrfont.ttf`.
The default build compiles the delimiter parser, byte expansion, Reed-Solomon
parity circuit, QR module placement, and fixed mask rendering.

Printable ASCII glyphs are copied from Liberation Sans Regular, scaled into the
QR Font em square, so text outside bracketed QR blocks renders as ordinary text
in the same font. `Liberation` is a reserved font name under the source font
license, so the generated family is named `QR Font`.

## Build

```sh
make
```

The project uses `uv` for Python dependency management. You can also run the
generator directly with:

```sh
uv run tools/build_font.py
```

By default the generator reads Liberation Sans Regular from:

```text
/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
```

Use a different compatible TrueType source with:

```sh
uv run tools/build_font.py --base-font /path/to/BaseFont-Regular.ttf
```

To try the full generated Reed-Solomon circuit:

```sh
make full-parity
```

This is also the default `make` path. It emits thousands of contextual lookups
and usually takes noticeably longer than a layout-only build.

For a faster layout-only build with placeholder zero parity:

```sh
make fast-placeholder
```

To inspect the shaped glyph stream:

```sh
uv run tools/shape_debug.py '[a]' '[b]'
```

Outputs:

- `dist/qrfont.ttf`
- `dist/demo.html`
- `build/qrfont.fea`

Open `dist/demo.html` in a browser and type bracketed text such as `[hello]`.
Mixed text such as `abc[def]ghi` should render as normal text, then a QR code
for `def`, then normal text.

## License

The generated font is a Modified Version of Liberation Sans Regular and is
licensed under the SIL Open Font License, Version 1.1. See
`LICENSE-OFL.txt` and `NOTICE.md`.

## Notes

This is a proof-of-concept font. It relies on OpenType shaping, so it needs an
environment that applies GSUB features to the font. Inputs inside a QR block
are bounded to printable ASCII, up to 17 characters.
