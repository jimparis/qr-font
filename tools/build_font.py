#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.transform import Transform
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import _g_a_s_p
from fontTools.ttLib.tables.ttProgram import Program


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
DEFAULT_BASE_FONT = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")

MODULE = 100
QUIET = 4
QR_SIZE = 21
ADVANCE = (QR_SIZE + QUIET * 2) * MODULE
UNITS_PER_EM = ADVANCE
ASCENT = ADVANCE
DESCENT = 0
MAX_LEN = 17
DATA_BITS = 152
PARITY_BITS = 56
TOTAL_BITS = DATA_BITS + PARITY_BITS
MASK = 0
RENDER_X_BIAS = 0
MODULE_OVERPAINT = 8
SUPPORTED_CODES = [c for c in range(32, 127) if c not in (ord("["), ord("]"))]
LATIN_SCALE = 0.20
LATIN_Y_SHIFT = 220


def g_char(code: int) -> str:
    return f"char_{code:03d}"


def g_byte(pos: int, code: int) -> str:
    return f"byte_{pos:02d}_{code:03d}"


def g_d(pos: int, bit: int) -> str:
    return f"d{pos:03d}_{bit}"


def g_p(pos: int, bit: int) -> str:
    return f"p{pos:02d}_{bit}"


def g_c(pos: int) -> str:
    return f"c{pos:02d}"


def g_len(n: int) -> str:
    return f"len_{n:02d}"


def bits_of(value: int, width: int) -> list[int]:
    return [(value >> shift) & 1 for shift in range(width - 1, -1, -1)]


def gf_tables() -> tuple[list[int], list[int]]:
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


GF_EXP, GF_LOG = gf_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def poly_mul(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, av in enumerate(a):
        for j, bv in enumerate(b):
            out[i + j] ^= gf_mul(av, bv)
    return out


def rs_generator(ec_count: int) -> list[int]:
    gen = [1]
    for i in range(ec_count):
        gen = poly_mul(gen, [1, GF_EXP[i]])
    return gen


RS_GEN = rs_generator(7)


def rs_encode(data: list[int], ec_count: int = 7) -> list[int]:
    ecc = [0] * ec_count
    for value in data:
        factor = value ^ ecc[0]
        ecc = ecc[1:] + [0]
        for i in range(ec_count):
            ecc[i] ^= gf_mul(RS_GEN[i + 1], factor)
    return ecc


def data_bits_for_text(text: str) -> list[int]:
    payload: list[int] = []
    payload.extend([0, 1, 0, 0])
    payload.extend(bits_of(len(text), 8))
    for ch in text:
        payload.extend(bits_of(ord(ch), 8))

    remaining = DATA_BITS - len(payload)
    payload.extend([0] * min(4, remaining))
    while len(payload) % 8:
        payload.append(0)
    pad_words = (0xEC, 0x11)
    i = 0
    while len(payload) < DATA_BITS:
        payload.extend(bits_of(pad_words[i % 2], 8))
        i += 1
    return payload[:DATA_BITS]


def bytes_from_bits(bit_values: list[int]) -> list[int]:
    return [
        int("".join(str(b) for b in bit_values[i : i + 8]), 2)
        for i in range(0, len(bit_values), 8)
    ]


def parity_bits_for_data(data_bits: list[int]) -> list[int]:
    parity = rs_encode(bytes_from_bits(data_bits))
    out: list[int] = []
    for value in parity:
        out.extend(bits_of(value, 8))
    return out


def derive_parity_matrix() -> list[list[int]]:
    columns: list[list[int]] = []
    for i in range(DATA_BITS):
        data = [0] * DATA_BITS
        data[i] = 1
        columns.append(parity_bits_for_data(data))
    return columns


def is_masked(row: int, col: int) -> bool:
    if MASK == 0:
        return (row + col) % 2 == 0
    raise ValueError("Only mask 0 is implemented")


def draw_square(pen: TTGlyphPen, row: int, col: int, x_shift: int = 0) -> None:
    x0 = (QUIET + col) * MODULE + x_shift + RENDER_X_BIAS - MODULE_OVERPAINT
    y1 = (QUIET + QR_SIZE - row) * MODULE + MODULE_OVERPAINT
    x1 = x0 + MODULE + MODULE_OVERPAINT * 2
    y0 = y1 - MODULE - MODULE_OVERPAINT * 2
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def empty_glyph():
    return TTGlyphPen(None).glyph()


def square_glyph(row: int, col: int, x_shift: int = 0):
    pen = TTGlyphPen(None)
    draw_square(pen, row, col, x_shift)
    return pen.glyph()


def draw_bit_square(pen: TTGlyphPen, bit_index: int, bit: int, coords: list[tuple[int, int]]) -> None:
    row, col = coords[bit_index]
    if bit ^ is_masked(row, col):
        draw_square(pen, row, col)


def bit_group_glyph(bits: Iterable[tuple[int, int]], coords: list[tuple[int, int]], x_shift: int = 0):
    pen = TTGlyphPen(None)
    for bit_index, bit in bits:
        row, col = coords[bit_index]
        if bit ^ is_masked(row, col):
            draw_square(pen, row, col, x_shift)
    return pen.glyph()


def finder_modules(top: int, left: int) -> set[tuple[int, int]]:
    black: set[tuple[int, int]] = set()
    for r in range(7):
        for c in range(7):
            if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                black.add((top + r, left + c))
    return black


def reserved_matrix() -> list[list[bool]]:
    reserved = [[False] * QR_SIZE for _ in range(QR_SIZE)]

    def reserve(row: int, col: int) -> None:
        if 0 <= row < QR_SIZE and 0 <= col < QR_SIZE:
            reserved[row][col] = True

    for top, left in ((0, 0), (0, 14), (14, 0)):
        for row in range(top - 1, top + 8):
            for col in range(left - 1, left + 8):
                reserve(row, col)

    for i in range(QR_SIZE):
        reserve(6, i)
        reserve(i, 6)

    for col in range(0, 9):
        reserve(8, col)
    for row in range(0, 9):
        reserve(row, 8)
    for col in range(QR_SIZE - 8, QR_SIZE):
        reserve(8, col)
    for row in range(QR_SIZE - 7, QR_SIZE):
        reserve(row, 8)

    reserve(13, 8)
    return reserved


def data_coordinates() -> list[tuple[int, int]]:
    reserved = reserved_matrix()
    coords: list[tuple[int, int]] = []
    upward = True
    col = QR_SIZE - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(QR_SIZE - 1, -1, -1) if upward else range(QR_SIZE)
        for row in rows:
            for c in (col, col - 1):
                if not reserved[row][c]:
                    coords.append((row, c))
        upward = not upward
        col -= 2
    if len(coords) != TOTAL_BITS:
        raise RuntimeError(f"expected {TOTAL_BITS} data coordinates, got {len(coords)}")
    return coords


def format_bits() -> list[int]:
    # EC level L is 01; mask pattern 0 is 000.
    data = (0b01 << 3) | MASK
    value = data << 10
    poly = 0x537
    for shift in range(14, 9, -1):
        if value & (1 << shift):
            value ^= poly << (shift - 10)
    encoded = ((data << 10) | value) ^ 0x5412
    return bits_of(encoded, 15)


def base_black_modules() -> set[tuple[int, int]]:
    black: set[tuple[int, int]] = set()
    black |= finder_modules(0, 0)
    black |= finder_modules(0, 14)
    black |= finder_modules(14, 0)

    for i in range(8, 13):
        if i % 2 == 0:
            black.add((6, i))
            black.add((i, 6))

    black.add((13, 8))

    fmt = format_bits()
    first = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
             (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    second = [(20, 8), (19, 8), (18, 8), (17, 8), (16, 8), (15, 8), (14, 8),
              (8, 13), (8, 14), (8, 15), (8, 16), (8, 17), (8, 18), (8, 19), (8, 20)]
    for bit, coord in zip(fmt, first):
        if bit:
            black.add(coord)
    for bit, coord in zip(fmt, second):
        if bit:
            black.add(coord)
    return black


def base_glyph(x_shift: int = 0):
    pen = TTGlyphPen(None)
    for row, col in sorted(base_black_modules()):
        draw_square(pen, row, col, x_shift)
    return pen.glyph()


@dataclass
class FontData:
    glyph_order: list[str]
    glyphs: dict[str, object]
    advance_widths: dict[str, int]
    cmap: dict[int, str]


def add_empty(name: str, data: FontData, width: int = 0) -> None:
    if name not in data.glyphs:
        data.glyph_order.append(name)
        data.glyphs[name] = empty_glyph()
        data.advance_widths[name] = width


def copy_base_glyph(
    base_font: TTFont,
    source_name: str,
    target_name: str,
    data: FontData,
    scale: float,
    y_shift: int,
) -> None:
    glyph_set = base_font.getGlyphSet()
    source_glyph = glyph_set[source_name]
    pen = TTGlyphPen(None)
    transform_pen = TransformPen(pen, Transform(scale, 0, 0, scale, 0, y_shift))
    source_glyph.draw(transform_pen)
    data.glyph_order.append(target_name)
    data.glyphs[target_name] = pen.glyph()
    source_width, _ = base_font["hmtx"][source_name]
    scaled_width = round(source_width * scale)
    if scaled_width > 0:
        data.advance_widths[target_name] = max(MODULE, round(scaled_width / MODULE) * MODULE)
    else:
        data.advance_widths[target_name] = 0


def add_printable_base_glyphs(data: FontData, base_font_path: Path) -> None:
    base_font = TTFont(base_font_path)
    scale = (ADVANCE / base_font["head"].unitsPerEm) * LATIN_SCALE
    cmap = base_font.getBestCmap()

    notdef_name = ".notdef"
    if notdef_name in base_font.getGlyphOrder():
        copy_base_glyph(base_font, notdef_name, ".notdef", data, scale, LATIN_Y_SHIFT)
    else:
        data.glyph_order.append(".notdef")
        data.glyphs[".notdef"] = empty_glyph()
        data.advance_widths[".notdef"] = ADVANCE

    printable_names = {
        32: "space",
        ord("["): "open_delim",
        ord("]"): "close_delim",
    }
    printable_names.update({code: g_char(code) for code in SUPPORTED_CODES})

    for code in range(32, 127):
        target_name = printable_names[code]
        source_name = cmap.get(code)
        if source_name is None:
            add_empty(target_name, data, round(ADVANCE * LATIN_SCALE) if code == 32 else 0)
        else:
            copy_base_glyph(base_font, source_name, target_name, data, scale, LATIN_Y_SHIFT)
        data.cmap[code] = target_name


def build_font_data(base_font_path: Path = DEFAULT_BASE_FONT) -> FontData:
    data = FontData([], {}, {}, {})
    add_printable_base_glyphs(data, base_font_path)
    coords = data_coordinates()

    add_empty("empty", data)

    data.glyph_order.append("header_bits")
    data.glyphs["header_bits"] = bit_group_glyph(
        ((i, bit) for i, bit in enumerate([0, 1, 0, 0])), coords
    )
    data.advance_widths["header_bits"] = ADVANCE

    for i in range(8):
        add_empty(g_c(i), data)
    for n in range(MAX_LEN + 1):
        add_empty(g_len(n), data)
    for pos in range(MAX_LEN):
        for code in SUPPORTED_CODES:
            name = g_byte(pos, code)
            start = 12 + pos * 8
            bits = ((start + i, bit) for i, bit in enumerate(bits_of(code, 8)))
            data.glyph_order.append(name)
            data.glyphs[name] = bit_group_glyph(bits, coords)
            data.advance_widths[name] = ADVANCE

    for length in range(MAX_LEN + 1):
        count_name = f"count_{length:02d}"
        data.glyph_order.append(count_name)
        data.glyphs[count_name] = bit_group_glyph(
            ((4 + i, bit) for i, bit in enumerate(bits_of(length, 8))),
            coords,
        )
        data.advance_widths[count_name] = ADVANCE

        used = 12 + length * 8
        tail = close_tail_bits(length)
        tail_name = f"tail_{length:02d}"
        data.glyph_order.append(tail_name)
        data.glyphs[tail_name] = bit_group_glyph(
            ((used + i, bit) for i, bit in enumerate(tail)),
            coords,
        )
        data.advance_widths[tail_name] = ADVANCE

        parity_name = f"parity_zero_{length:02d}"
        data.glyph_order.append(parity_name)
        data.glyphs[parity_name] = bit_group_glyph(
            ((DATA_BITS + i, 0) for i in range(PARITY_BITS)),
            coords,
        )
        data.advance_widths[parity_name] = ADVANCE

        base_name = f"qr_base_{length:02d}"
        data.glyph_order.append(base_name)
        data.glyphs[base_name] = base_glyph()
        data.advance_widths[base_name] = ADVANCE

    for i, (row, col) in enumerate(coords[:DATA_BITS]):
        for bit in (0, 1):
            name = g_d(i, bit)
            data.glyph_order.append(name)
            data.glyphs[name] = square_glyph(row, col) if (bit ^ is_masked(row, col)) else empty_glyph()
            data.advance_widths[name] = 0
    for i, (row, col) in enumerate(coords[DATA_BITS:]):
        for bit in (0, 1):
            name = g_p(i, bit)
            data.glyph_order.append(name)
            data.glyphs[name] = square_glyph(row, col) if (bit ^ is_masked(row, col)) else empty_glyph()
            data.advance_widths[name] = 0

    return data


def class_line(name: str, members: Iterable[str]) -> str:
    return f"@{name} = [{' '.join(members)}];"


def grouped_internal_glyphs() -> list[str]:
    names = ["header_bits"]
    for pos in range(MAX_LEN):
        names.extend(g_byte(pos, code) for code in SUPPORTED_CODES)
    for length in range(MAX_LEN + 1):
        names.extend((f"count_{length:02d}", f"tail_{length:02d}", f"parity_zero_{length:02d}"))
    return names


def grouped_any_glyphs() -> list[str]:
    names = grouped_internal_glyphs()
    names.extend(f"qr_base_{length:02d}" for length in range(MAX_LEN + 1))
    return names


def grouped_follow_glyphs() -> list[str]:
    return ["empty", *grouped_any_glyphs()]


def is_qr_render_glyph(name: str) -> bool:
    return (
        name == "header_bits"
        or name.startswith("byte_")
        or name.startswith("count_")
        or name.startswith("tail_")
        or name.startswith("parity_zero_")
        or name.startswith("qr_base_")
        or name.startswith("d")
        or name.startswith("p")
    )


def add_qr_noop_programs(font_data: FontData) -> None:
    program = Program()
    program.fromAssembly(["PUSHB[1] 0", "POP[]"])
    for name, glyph in font_data.glyphs.items():
        if is_qr_render_glyph(name) and getattr(glyph, "numberOfContours", 0):
            glyph.program = program


def close_tail_bits(length: int) -> list[int]:
    used = 12 + length * 8
    bits: list[int] = []
    remaining = DATA_BITS - used
    bits.extend([0] * min(4, remaining))
    while (used + len(bits)) % 8:
        bits.append(0)
    pads = [0xEC, 0x11]
    i = 0
    while used + len(bits) < DATA_BITS:
        bits.extend(bits_of(pads[i % 2], 8))
        i += 1
    return bits

def grouped_close_payload(length: int) -> list[str]:
    return [f"count_{length:02d}", f"tail_{length:02d}", f"parity_zero_{length:02d}", f"qr_base_{length:02d}"]


def bit_close_payload(length: int) -> list[str]:
    used = 12 + length * 8
    payload = [g_d(used + i, bit) for i, bit in enumerate(close_tail_bits(length))]
    payload.extend(g_p(i, 0) for i in range(PARITY_BITS))
    payload.append(f"qr_base_{length:02d}")
    return payload


def data_context_parts(length: int, focus_index: int) -> list[str]:
    def data_part(index: int) -> str:
        return g_d(index, 1) if index == focus_index else f"@d{index:03d}"

    parts = [data_part(i) for i in range(12)]
    for pos in range(length):
        parts.append("empty")
        start = 12 + pos * 8
        parts.extend(data_part(i) for i in range(start, start + 8))
    used = 12 + length * 8
    parts.append("empty")
    parts.extend(data_part(i) for i in range(used, DATA_BITS))
    return parts


def generate_features(include_parity_circuit: bool = False) -> str:
    languagesystems = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", ""]
    lines: list[str] = [*languagesystems]

    for pos in range(MAX_LEN):
        lines.append(class_line(f"byte_{pos:02d}", (g_byte(pos, c) for c in SUPPORTED_CODES)))
    for i in range(DATA_BITS):
        lines.append(class_line(f"d{i:03d}", (g_d(i, 0), g_d(i, 1))))
    for i in range(PARITY_BITS):
        lines.append(class_line(f"p{i:02d}", (g_p(i, 0), g_p(i, 1))))
    lines.append("")

    if include_parity_circuit:
        open_replacement = "d000_0 d001_1 d002_0 d003_0 c00 c01 c02 c03 c04 c05 c06 c07 len_00"
    else:
        open_replacement = "header_bits len_00"

    lines.extend([
        "lookup OpenQR {",
        f"    sub open_delim by {open_replacement};",
        "} OpenQR;",
        "",
    ])

    helper_lookups: list[str] = []
    feature_lookups: list[str] = ["OpenQR"]

    for pos in range(MAX_LEN):
        scan_name = f"Scan{pos:02d}"
        hide_name = f"HideScanLen{pos:02d}"
        lines.append(f"lookup {scan_name} {{")
        for code in SUPPORTED_CODES:
            a = f"SetByte{pos:02d}_{code:03d}"
            helper_lookups.extend([
                f"lookup {a} {{ sub {g_char(code)} by {g_byte(pos, code)} {g_len(pos + 1)}; }} {a};",
            ])
            lines.append(f"    sub {g_len(pos)} {g_char(code)}' lookup {a};")
        lines.append(f"}} {scan_name};")
        lines.append("")
        lines.append(f"lookup {hide_name} {{")
        lines.append(f"    sub {g_len(pos)}' @byte_{pos:02d} {g_len(pos + 1)} by empty;")
        lines.append(f"}} {hide_name};")
        lines.append("")
        feature_lookups.append(scan_name)
        feature_lookups.append(hide_name)

    count_lookups: list[str] = []
    for length in range(MAX_LEN + 1):
        length_bits = bits_of(length, 8)
        for cpos, bit in enumerate(length_bits):
            name = f"SetCount{length:02d}_{cpos:02d}"
            count_lookups.append(f"lookup {name} {{ sub {g_c(cpos)} by {g_d(4 + cpos, bit)}; }} {name};")

    if include_parity_circuit:
        for cpos in range(8):
            lookup_name = f"FillCount{cpos:02d}"
            lines.append(f"lookup {lookup_name} {{")
            for length in range(MAX_LEN + 1):
                tail = [g_c(i) for i in range(cpos + 1, 8)]
                for i in range(length):
                    tail.append("empty")
                    tail.append(f"@byte_{i:02d}")
                tail.append(g_len(length))
                context_tail = " ".join(tail)
                setter = f"SetCount{length:02d}_{cpos:02d}"
                if context_tail:
                    lines.append(f"    sub {g_c(cpos)}' lookup {setter} {context_tail};")
                else:
                    lines.append(f"    sub {g_c(cpos)}' lookup {setter};")
            lines.append(f"}} {lookup_name};")
            lines.append("")
            feature_lookups.append(lookup_name)

    lines.append("lookup ExpandBytes {")
    for pos in range(MAX_LEN):
        start = 12 + pos * 8
        for code in SUPPORTED_CODES:
            names = " ".join(g_d(start + i, bit) for i, bit in enumerate(bits_of(code, 8)))
            lines.append(f"    sub {g_byte(pos, code)} by {names};")
    lines.append("} ExpandBytes;")
    lines.append("")

    lines.append("lookup HideLen {")
    for length in range(MAX_LEN + 1):
        lines.append(f"    sub {g_len(length)} by empty;")
    lines.append("} HideLen;")
    lines.append("")

    for length in range(MAX_LEN + 1):
        name = f"Close{length:02d}"
        lines.append(f"lookup {name} {{")
        close_payload = bit_close_payload(length) if include_parity_circuit else grouped_close_payload(length)
        lines.append(f"    sub close_delim by {' '.join(close_payload)};")
        lines.append(f"}} {name};")
        lines.append("")

    lines.append("lookup CloseQR {")
    for length in range(MAX_LEN + 1):
        lines.append(f"    sub {g_len(length)}' lookup HideLen close_delim' lookup Close{length:02d};")
    lines.append("} CloseQR;")
    lines.append("")
    feature_lookups.append("CloseQR")
    if include_parity_circuit:
        feature_lookups.append("ExpandBytes")

    if include_parity_circuit:
        for i in range(PARITY_BITS):
            lines.extend([
                f"lookup ToggleP{i:02d} {{",
                f"    sub {g_p(i, 0)} by {g_p(i, 1)};",
                f"    sub {g_p(i, 1)} by {g_p(i, 0)};",
                f"}} ToggleP{i:02d};",
                "",
            ])

        matrix = derive_parity_matrix()
        for length in range(MAX_LEN + 1):
            for data_index, parity_column in enumerate(matrix):
                toggles = [i for i, bit in enumerate(parity_column) if bit]
                if not toggles:
                    continue
                name = f"ApplyL{length:02d}D{data_index:03d}"
                toggle_name = f"ToggleL{length:02d}D{data_index:03d}"
                lines.append(f"lookup {toggle_name} {{")
                for p in toggles:
                    lines.append(f"    sub {g_p(p, 0)} by {g_p(p, 1)};")
                    lines.append(f"    sub {g_p(p, 1)} by {g_p(p, 0)};")
                lines.append(f"}} {toggle_name};")
                lines.append("")
                lines.append(f"lookup {name} {{")
                parts = data_context_parts(length, data_index)
                for p in range(PARITY_BITS):
                    parts.append(f"@p{p:02d}' lookup {toggle_name}")
                parts.append(f"qr_base_{length:02d}")
                lines.append(f"    sub {' '.join(parts)};")
                lines.append(f"}} {name};")
                lines.append("")
                feature_lookups.append(name)

    all_lines = [*languagesystems]
    all_lines.extend(helper_lookups)
    all_lines.extend(count_lookups)
    all_lines.extend(lines[2:])

    all_lines.append("feature rlig {")
    for name in feature_lookups:
        all_lines.append(f"    lookup {name};")
    all_lines.append("} rlig;")
    all_lines.append("")
    if not include_parity_circuit:
        all_lines.append(class_line("qr_internal", grouped_internal_glyphs()))
        all_lines.append(class_line("qr_any", grouped_any_glyphs()))
        all_lines.append(class_line("qr_follow", grouped_follow_glyphs()))
        all_lines.append("feature kern {")
        all_lines.append(f"    pos @qr_internal <0 0 {-ADVANCE} 0> @qr_follow;")
        all_lines.append("} kern;")
        all_lines.append("")
    return "\n".join(all_lines)


def build_ttf(font_data: FontData, feature_text: str, output: Path) -> None:
    add_qr_noop_programs(font_data)
    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(font_data.glyph_order)
    fb.setupCharacterMap(font_data.cmap)
    fb.setupGlyf(font_data.glyphs)
    metrics = {}
    for name in font_data.glyph_order:
        glyph = font_data.glyphs[name]
        left_side_bearing = getattr(glyph, "xMin", 0) or 0
        metrics[name] = (font_data.advance_widths[name], left_side_bearing)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        usWinAscent=ASCENT,
        usWinDescent=DESCENT,
    )
    fb.setupNameTable(
        {
            "familyName": "QR Font",
            "styleName": "Regular",
            "uniqueFontIdentifier": "QR Font Regular 0.1",
            "fullName": "QR Font Regular",
            "psName": "QRFont-Regular",
            "version": "Version 0.1",
            "copyright": (
                "Derived from Liberation Sans: digitized data copyright (c) 2010 "
                "Google Corporation; copyright (c) 2012 Red Hat, Inc. QR Font "
                "additions copyright their contributors."
            ),
            "licenseDescription": "Licensed under the SIL Open Font License, Version 1.1.",
            "licenseInfoURL": "https://scripts.sil.org/OFL",
        }
    )
    fb.setupPost()
    font = fb.font
    gasp = newTable("gasp")
    gasp.gaspRange = {
        0xFFFF: (
            _g_a_s_p.GASP_DOGRAY
            | _g_a_s_p.GASP_SYMMETRIC_SMOOTHING
        )
    }
    font["gasp"] = gasp
    addOpenTypeFeaturesFromString(font, feature_text)
    font.save(output)


def write_demo(font_filename: str) -> None:
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QR Font Demo</title>
<style>
@font-face {
  font-family: "QR Font";
  src: url("./__FONT_FILENAME__") format("truetype");
}
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  background: #f6f7f9;
  color: #17202a;
}
main {
  max-width: 900px;
  margin: 48px auto;
  padding: 0 24px;
}
label {
  display: block;
  font-size: 14px;
  font-weight: 650;
  margin-bottom: 8px;
}
textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 92px;
  resize: vertical;
  padding: 12px 14px;
  border: 1px solid #b7c0cc;
  border-radius: 6px;
  font: 18px system-ui, sans-serif;
}
.qr {
  margin-top: 32px;
  font-family: "QR Font";
  font-feature-settings: "rlig" 1, "kern" 1;
  font-size: 203px;
  line-height: 1;
  color: #000;
  background: #fff;
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-height: 203px;
  padding: 0;
  overflow-x: auto;
  overflow-y: auto;
  white-space: pre-wrap;
}
.meta {
  margin-top: 10px;
  color: #4b5563;
  font-size: 14px;
}
</style>
</head>
<body>
<main>
  <label for="text">Text</label>
  <textarea id="text" autocomplete="off" spellcheck="false">Hello [QR coded] world!
Download this font: [http://qr.jim.sh/]</textarea>
  <p class="meta">Use printable ASCII inside square brackets, up to 17 characters per QR block. Text outside brackets remains ordinary Liberation Sans-derived text.</p>
  <div id="qr" class="qr">Hello [QR coded] world!
Download this font: [http://qr.jim.sh/]</div>
</main>
<script>
const input = document.getElementById("text");
const qr = document.getElementById("qr");
function render() {
  const value = input.value;
  qr.replaceChildren(document.createTextNode(value));
}
input.addEventListener("input", render);
input.addEventListener("change", render);
input.addEventListener("keyup", render);
render();
</script>
</body>
</html>
""".replace("__FONT_FILENAME__", font_filename)
    (DIST / "demo.html").write_text(html, encoding="utf-8")


def matrix_for_text(text: str) -> set[tuple[int, int]]:
    coords = data_coordinates()
    black = set(base_black_modules())
    data = data_bits_for_text(text)
    parity = parity_bits_for_data(data)
    for i, bit in enumerate(data + parity):
        row, col = coords[i]
        if bit ^ is_masked(row, col):
            black.add((row, col))
    return black


def svg_for_text(text: str, size: int = 150) -> str:
    scale = size / (QR_SIZE + QUIET * 2)
    rects = []
    for row, col in sorted(matrix_for_text(text)):
        x = (QUIET + col) * scale
        y = (QUIET + row) * scale
        rects.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{scale:.3f}" height="{scale:.3f}"/>')
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<g fill="black">{"".join(rects)}</g></svg>'
    )


def write_reference() -> None:
    samples = ["hello", "world", "asdfasdfasdfasdf"]
    cards = []
    for sample in samples:
        cards.append(f"<section><code>[{sample}]</code>{svg_for_text(sample)}</section>")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QR Font Reference</title>
<style>
body {{ margin: 40px; font-family: system-ui, sans-serif; background: #f6f7f9; }}
main {{ display: flex; gap: 32px; flex-wrap: wrap; align-items: flex-start; }}
section {{ display: grid; gap: 8px; }}
code {{ font: 14px ui-monospace, SFMono-Regular, Consolas, monospace; }}
</style>
</head>
<body><main>{''.join(cards)}</main></body>
</html>
"""
    (DIST / "reference.html").write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-font",
        type=Path,
        default=DEFAULT_BASE_FONT,
        help="TrueType font to copy printable glyphs from",
    )
    parser.add_argument(
        "--full-parity-circuit",
        action="store_true",
        help="deprecated no-op; full Reed-Solomon parity is emitted by default",
    )
    parser.add_argument(
        "--placeholder-parity",
        action="store_true",
        help="use zero parity bits for a faster layout-only build",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    for stale_font in DIST.glob("qrfont-*.ttf"):
        stale_font.unlink()
    font_data = build_font_data(args.base_font)
    feature_text = generate_features(include_parity_circuit=not args.placeholder_parity)
    (BUILD / "qrfont.fea").write_text(feature_text, encoding="utf-8")
    build_ttf(font_data, feature_text, DIST / "qrfont.ttf")
    font_version = hashlib.sha256((DIST / "qrfont.ttf").read_bytes()).hexdigest()[:16]
    font_filename = f"qrfont-{font_version}.ttf"
    (DIST / font_filename).write_bytes((DIST / "qrfont.ttf").read_bytes())
    write_demo(font_filename)
    write_reference()
    print(f"wrote {DIST / 'qrfont.ttf'}")
    print(f"wrote {DIST / 'demo.html'}")


if __name__ == "__main__":
    main()
