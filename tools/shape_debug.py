#!/usr/bin/env python3
from __future__ import annotations

import argparse

import uharfbuzz as hb
from fontTools.ttLib import TTFont


def shape(font_path: str, text: str) -> list[str]:
    font_data = open(font_path, "rb").read()
    face = hb.Face(font_data)
    font = hb.Font(face)
    ttfont = TTFont(font_path)
    glyph_order = ttfont.getGlyphOrder()

    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, {"rlig": True})
    return [glyph_order[item.codepoint] for item in buffer.glyph_infos]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("texts", nargs="+")
    parser.add_argument("--font", default="dist/qrfont.ttf")
    args = parser.parse_args()

    shaped = [(text, shape(args.font, text)) for text in args.texts]
    for text, glyphs in shaped:
        ones = [name for name in glyphs if name.startswith("d") and name.endswith("_1")]
        print(f"{text}: {len(glyphs)} glyphs, {len(ones)} one-valued data bits")
        print("  first glyphs:", " ".join(glyphs[:24]))

    if len(shaped) == 2:
        left_text, left = shaped[0]
        right_text, right = shaped[1]
        diffs = [i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        print(f"{left_text} vs {right_text}: {len(diffs)} differing shaped glyph positions")
        if diffs:
            preview = ", ".join(f"{i}:{left[i]}->{right[i]}" for i in diffs[:24])
            print("  " + preview)


if __name__ == "__main__":
    main()
