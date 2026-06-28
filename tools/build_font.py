#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
MASK = 0
RENDER_X_BIAS = 0
MODULE_OVERPAINT = 8
SUPPORTED_CODES = [c for c in range(32, 127) if c not in (ord("["), ord("]"))]
LATIN_SCALE = 1.00
LATIN_Y_SHIFT = 220


QR_CONFIGS = {
    "1L": {"version": 1, "size": 21, "data_codewords": 19, "ec_codewords": 7, "max_len": 17},
    "2L": {"version": 2, "size": 25, "data_codewords": 34, "ec_codewords": 10, "max_len": 32},
    "3L": {"version": 3, "size": 29, "data_codewords": 55, "ec_codewords": 15, "max_len": 53},
}

QR_LABEL = "1L"
QR_VERSION = 1
QR_SIZE = 21
ADVANCE = (QR_SIZE + QUIET * 2) * MODULE
UNITS_PER_EM = ADVANCE
ASCENT = ADVANCE
DESCENT = 0
MAX_LEN = 17
DATA_CODEWORDS = 19
EC_CODEWORDS = 7
DATA_BITS = DATA_CODEWORDS * 8
PARITY_BITS = EC_CODEWORDS * 8
TOTAL_BITS = DATA_BITS + PARITY_BITS
RS_GEN: list[int] = []

def configure_qr(label: str) -> None:
    global QR_LABEL, QR_VERSION, QR_SIZE, ADVANCE, UNITS_PER_EM, ASCENT, DESCENT
    global MAX_LEN, DATA_CODEWORDS, EC_CODEWORDS, DATA_BITS, PARITY_BITS, TOTAL_BITS, RS_GEN

    config = QR_CONFIGS[label]
    QR_LABEL = label
    QR_VERSION = config["version"]
    QR_SIZE = config["size"]
    ADVANCE = (QR_SIZE + QUIET * 2) * MODULE
    UNITS_PER_EM = ADVANCE
    ASCENT = ADVANCE
    DESCENT = 0
    MAX_LEN = config["max_len"]
    DATA_CODEWORDS = config["data_codewords"]
    EC_CODEWORDS = config["ec_codewords"]
    DATA_BITS = DATA_CODEWORDS * 8
    PARITY_BITS = EC_CODEWORDS * 8
    TOTAL_BITS = DATA_BITS + PARITY_BITS
    RS_GEN = rs_generator(EC_CODEWORDS)


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


def rs_encode(data: list[int], ec_count: int | None = None) -> list[int]:
    if ec_count is None:
        ec_count = EC_CODEWORDS
    ecc = [0] * ec_count
    for value in data:
        factor = value ^ ecc[0]
        ecc = ecc[1:] + [0]
        for i in range(ec_count):
            ecc[i] ^= gf_mul(RS_GEN[i + 1], factor)
    return ecc


configure_qr("1L")


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


def alignment_modules(center_row: int, center_col: int) -> set[tuple[int, int]]:
    black: set[tuple[int, int]] = set()
    for row in range(center_row - 2, center_row + 3):
        for col in range(center_col - 2, center_col + 3):
            dr = abs(row - center_row)
            dc = abs(col - center_col)
            if dr == 2 or dc == 2 or (dr == 0 and dc == 0):
                black.add((row, col))
    return black


def alignment_centers() -> list[tuple[int, int]]:
    if QR_VERSION == 1:
        return []
    if QR_VERSION == 2:
        return [(18, 18)]
    if QR_VERSION == 3:
        return [(22, 22)]
    raise ValueError("Only QR versions 1, 2, and 3 are implemented")


def reserved_matrix() -> list[list[bool]]:
    reserved = [[False] * QR_SIZE for _ in range(QR_SIZE)]

    def reserve(row: int, col: int) -> None:
        if 0 <= row < QR_SIZE and 0 <= col < QR_SIZE:
            reserved[row][col] = True

    for top, left in ((0, 0), (0, QR_SIZE - 7), (QR_SIZE - 7, 0)):
        for row in range(top - 1, top + 8):
            for col in range(left - 1, left + 8):
                reserve(row, col)

    for center_row, center_col in alignment_centers():
        for row in range(center_row - 2, center_row + 3):
            for col in range(center_col - 2, center_col + 3):
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

    reserve(4 * QR_VERSION + 9, 8)
    return reserved


def all_data_coordinates() -> list[tuple[int, int]]:
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
    return coords


def data_coordinates() -> list[tuple[int, int]]:
    coords = all_data_coordinates()
    if len(coords) < TOTAL_BITS:
        raise RuntimeError(f"expected at least {TOTAL_BITS} data coordinates, got {len(coords)}")
    return coords[:TOTAL_BITS]


def remainder_coordinates() -> list[tuple[int, int]]:
    return all_data_coordinates()[TOTAL_BITS:]


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
    black |= finder_modules(0, QR_SIZE - 7)
    black |= finder_modules(QR_SIZE - 7, 0)
    for center_row, center_col in alignment_centers():
        black |= alignment_modules(center_row, center_col)

    for i in range(8, QR_SIZE - 8):
        if i % 2 == 0:
            black.add((6, i))
            black.add((i, 6))

    black.add((4 * QR_VERSION + 9, 8))
    for row, col in remainder_coordinates():
        if is_masked(row, col):
            black.add((row, col))

    fmt = format_bits()
    first = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
             (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    second = [(QR_SIZE - 1 - i, 8) for i in range(7)]
    second.extend((8, QR_SIZE - 8 + i) for i in range(8))
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
        data.advance_widths[target_name] = scaled_width
    else:
        data.advance_widths[target_name] = 0


def add_printable_base_glyphs(data: FontData, base_font_path: Path) -> None:
    base_font = TTFont(base_font_path)
    scale = (UNITS_PER_EM / base_font["head"].unitsPerEm) * LATIN_SCALE
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
            add_empty(target_name, data, round(base_font["head"].unitsPerEm * 0.25 * scale) if code == 32 else 0)
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
    data.advance_widths["header_bits"] = 0

    for i in range(8):
        add_empty(g_c(i), data)
    for n in range(MAX_LEN + 1):
        add_empty(g_len(n), data)
    for j in range(EC_CODEWORDS):
        for val in range(256):
            add_empty(f"s{j}_{val:03d}", data)
    for pos in range(MAX_LEN):
        for code in SUPPORTED_CODES:
            name = g_byte(pos, code)
            start = 12 + pos * 8
            bits = ((start + i, bit) for i, bit in enumerate(bits_of(code, 8)))
            data.glyph_order.append(name)
            data.glyphs[name] = bit_group_glyph(bits, coords)
            data.advance_widths[name] = 0

    for length in range(MAX_LEN + 1):
        count_name = f"count_{length:02d}"
        data.glyph_order.append(count_name)
        data.glyphs[count_name] = bit_group_glyph(
            ((4 + i, bit) for i, bit in enumerate(bits_of(length, 8))),
            coords,
        )
        data.advance_widths[count_name] = 0

        used = 12 + length * 8
        tail = close_tail_bits(length)
        tail_name = f"tail_{length:02d}"
        data.glyph_order.append(tail_name)
        data.glyphs[tail_name] = bit_group_glyph(
            ((used + i, bit) for i, bit in enumerate(tail)),
            coords,
        )
        data.advance_widths[tail_name] = 0

        parity_name = f"parity_zero_{length:02d}"
        data.glyph_order.append(parity_name)
        data.glyphs[parity_name] = bit_group_glyph(
            ((DATA_BITS + i, 0) for i in range(PARITY_BITS)),
            coords,
        )
        data.advance_widths[parity_name] = 0

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

    # Fused glyphs: p55_bit + qr_base_NN merged into one glyph.
    # These are produced by the MergeAll ligature lookup.
    last_parity_idx = PARITY_BITS - 1
    last_row, last_col = coords[DATA_BITS + last_parity_idx]
    for bit in (0, 1):
        p55_draws = bool(bit ^ is_masked(last_row, last_col))
        for length in range(MAX_LEN + 1):
            name = f"qr_base_p55_{bit}_{length:02d}"
            pen = TTGlyphPen(None)
            for r, c in sorted(base_black_modules()):
                draw_square(pen, r, c)
            if p55_draws:
                draw_square(pen, last_row, last_col)
            data.glyph_order.append(name)
            data.glyphs[name] = pen.glyph()
            data.advance_widths[name] = ADVANCE


    return data


def class_line(name: str, members: Iterable[str]) -> str:
    return f"@{name} = [{' '.join(members)}];"


def grouped_internal_glyphs(include_parity_circuit: bool = False) -> list[str]:
    names = ["header_bits"]
    for pos in range(MAX_LEN):
        names.extend(g_byte(pos, code) for code in SUPPORTED_CODES)
    for length in range(MAX_LEN + 1):
        names.extend((f"count_{length:02d}", f"tail_{length:02d}"))
        if not include_parity_circuit:
            names.append(f"parity_zero_{length:02d}")
    if include_parity_circuit:
        for j in range(EC_CODEWORDS):
            names.extend(f"s{j}_{val:03d}" for val in range(256))
        for i in range(PARITY_BITS):
            names.extend((g_p(i, 0), g_p(i, 1)))
    return names


def grouped_any_glyphs(include_parity_circuit: bool = False) -> list[str]:
    names = grouped_internal_glyphs(include_parity_circuit)
    names.extend(f"qr_base_{length:02d}" for length in range(MAX_LEN + 1))
    return names


def grouped_follow_glyphs(include_parity_circuit: bool = False) -> list[str]:
    names = ["empty", *grouped_any_glyphs(include_parity_circuit)]
    if include_parity_circuit:
        for j in range(EC_CODEWORDS):
            for val in range(256):
                names.append(f"s{j}_{val:03d}")
        for i in range(PARITY_BITS):
            for bit in (0, 1):
                names.append(g_p(i, bit))
    return names


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


def parity_contribution_for_byte(pos: int, code: int, matrix: list[list[int]]) -> list[int]:
    start = 12 + pos * 8
    bits = bits_of(code, 8)
    contribution = [0] * PARITY_BITS
    for i, bit in enumerate(bits):
        if bit:
            column = matrix[start + i]
            for p in range(PARITY_BITS):
                contribution[p] ^= column[p]
    return contribution


def fixed_parity_contribution(length: int, matrix: list[list[int]]) -> list[int]:
    fixed_bits = [0] * DATA_BITS
    
    # Mode: 0, 1, 0, 0
    mode = [0, 1, 0, 0]
    for i in range(4):
        fixed_bits[i] = mode[i]
        
    # Length:
    len_bits = bits_of(length, 8)
    for i in range(8):
        fixed_bits[4 + i] = len_bits[i]
        
    # Tail/padding:
    tail = close_tail_bits(length)
    start = 12 + length * 8
    for i, bit in enumerate(tail):
        fixed_bits[start + i] = bit
        
    # XOR sum of columns of the matrix for all fixed bits that are 1:
    contribution = [0] * PARITY_BITS
    for i in range(DATA_BITS):
        if fixed_bits[i]:
            column = matrix[i]
            for p in range(PARITY_BITS):
                contribution[p] ^= column[p]
    return contribution


def generate_features(include_parity_circuit: bool = False) -> str:
    languagesystems = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", ""]
    
    # We will build all_lines from the ground up
    all_lines: list[str] = [*languagesystems]

    # 1. Define classes first!
    for pos in range(MAX_LEN):
        all_lines.append(class_line(f"byte_{pos:02d}", (g_byte(pos, c) for c in SUPPORTED_CODES)))
    if include_parity_circuit:
        # Define parity classes
        for i in range(PARITY_BITS):
            all_lines.append(class_line(f"p{i:02d}", (g_p(i, 0), g_p(i, 1))))
        # Define state classes and their XOR permutations
        for j in range(EC_CODEWORDS):
            all_lines.append(class_line(f"s{j}", (f"s{j}_{val:03d}" for val in range(256))))
            for contrib in range(1, 256):
                permuted_glyphs = [f"s{j}_{val ^ contrib:03d}" for val in range(256)]
                all_lines.append(class_line(f"s{j}_x{contrib:03d}", permuted_glyphs))
            
    all_lines.append(class_line("SUPPORTED_CHARS", (g_char(c) for c in SUPPORTED_CODES)))
    all_lines.append("")

    # 2. Generate NoOp, XorS, and helper lookups
    helper_lookups: list[str] = []
    if include_parity_circuit:
        # Generate NoOp lookup using class-to-class identity substitutions and useExtension
        helper_lookups.append("lookup NoOp useExtension {")
        for j in range(EC_CODEWORDS):
            helper_lookups.append(f"    sub @s{j} by @s{j};")
        for pos in range(MAX_LEN):
            helper_lookups.append(f"    sub @byte_{pos:02d} by @byte_{pos:02d};")
        helper_lookups.append("} NoOp;")
        helper_lookups.append("")

        # Generate Xor lookups using class-to-class substitutions and useExtension
        for contrib in range(1, 256):
            lookup_name = f"Xor_{contrib:03d}"
            helper_lookups.append(f"lookup {lookup_name} useExtension {{")
            for j in range(EC_CODEWORDS):
                helper_lookups.append(f"    sub @s{j} by @s{j}_x{contrib:03d};")
            helper_lookups.append(f"}} {lookup_name};")
            helper_lookups.append("")
                


    # Generate Scan helper lookups
    if include_parity_circuit:
        # Pre-generate SetByte lookups (combined per character to reduce lookup count)
        for code in SUPPORTED_CODES:
            a = f"SetByte_{code:03d}"
            helper_lookups.append(
                f"lookup {a} useExtension {{ "
                + " ".join(f"sub len_{pos:02d} by {g_byte(pos, code)};" for pos in range(MAX_LEN))
                + f" }} {a};"
            )
        # Pre-generate SetLen lookups
        for pos in range(MAX_LEN):
            b = f"SetLen{pos + 1:02d}"
            helper_lookups.append(
                f"lookup {b} useExtension {{ sub @SUPPORTED_CHARS by len_{pos+1:02d}; }} {b};"
            )
    else:
        # Placeholder Scan helper lookups (combined to reduce lookup count)
        for code in SUPPORTED_CODES:
            a = f"SetByte_{code:03d}"
            b = f"SetLen_{code:03d}"
            helper_lookups.extend([
                f"lookup {a} useExtension {{ "
                + " ".join(f"sub {g_len(pos)} by {g_byte(pos, code)};" for pos in range(MAX_LEN))
                + f" }} {a};",
                f"lookup {b} useExtension {{ "
                + " ".join(f"sub {g_char(code)} by {g_len(pos + 1)};" for pos in range(MAX_LEN))
                + f" }} {b};",
            ])

    # Generate Close helper lookups
    if include_parity_circuit:
        # Pre-generate SetCountTail lookups
        for length in range(MAX_LEN + 1):
            helper_lookups.append(
                f"lookup SetCountTail_{length:02d} useExtension {{ "
                f"sub len_{length:02d} by count_{length:02d} tail_{length:02d}; "
                f"}} SetCountTail_{length:02d};"
            )
        # Pre-generate SetBase lookups
        for length in range(MAX_LEN + 1):
            helper_lookups.append(
                f"lookup SetBase_{length:02d} useExtension {{ "
                f"sub close_delim by qr_base_{length:02d}; "
                f"}} SetBase_{length:02d};"
            )
    else:
        # Placeholder Close helper lookups
        helper_lookups.append("lookup HideClose useExtension {")
        helper_lookups.append("    sub close_delim by empty;")
        helper_lookups.append("} HideClose;")
        helper_lookups.append("")
        for length in range(MAX_LEN + 1):
            name = f"Close{length:02d}"
            helper_lookups.append(f"lookup {name} useExtension {{")
            close_payload = grouped_close_payload(length)
            helper_lookups.append(f"    sub {g_len(length)} by {' '.join(close_payload)};")
            helper_lookups.append(f"}} {name};")
            helper_lookups.append("")

    # Add all helper lookups to all_lines
    all_lines.extend(helper_lookups)

    # 3. Main lookups (OpenQR, Scan{pos}, CloseQR)
    main_lines: list[str] = []
    
    # OpenQR
    if include_parity_circuit:
        open_replacement = "header_bits len_00 " + " ".join(f"s{j}_000" for j in range(EC_CODEWORDS))
    else:
        open_replacement = "header_bits len_00"
    main_lines.extend([
        "lookup OpenQR useExtension {",
        f"    sub open_delim by {open_replacement};",
        "} OpenQR;",
        "",
    ])
    feature_lookups: list[str] = ["OpenQR"]

    # Scan{pos}
    if include_parity_circuit:
        matrix = derive_parity_matrix()
        for pos in range(MAX_LEN):
            scan_name = f"Scan{pos:02d}"
            main_lines.append(f"lookup {scan_name} useExtension {{")
            for code in SUPPORTED_CODES:
                bit_contrib = parity_contribution_for_byte(pos, code, matrix)
                byte_contrib = bytes_from_bits(bit_contrib)
                rule_parts = []
                
                if pos == 0:
                    rule_parts.append(f"len_{pos:02d}' lookup SetByte_{code:03d}")
                    for j in range(EC_CODEWORDS):
                        contrib = byte_contrib[j]
                        if contrib:
                            rule_parts.append(f"@s{j}' lookup Xor_{contrib:03d}")
                        else:
                            rule_parts.append(f"@s{j}' lookup NoOp")
                    rule_parts.append(f"{g_char(code)}' lookup SetLen{pos + 1:02d}")
                else:
                    for j in range(EC_CODEWORDS):
                        contrib = byte_contrib[j]
                        if contrib:
                            rule_parts.append(f"@s{j}' lookup Xor_{contrib:03d}")
                        else:
                            rule_parts.append(f"@s{j}' lookup NoOp")
                    for k in range(1, pos):
                        rule_parts.append(f"@byte_{k:02d}' lookup NoOp")
                    rule_parts.append(f"len_{pos:02d}' lookup SetByte_{code:03d}")
                    rule_parts.append(f"{g_char(code)}' lookup SetLen{pos + 1:02d}")
                    
                main_lines.append(f"    sub {' '.join(rule_parts)};")
            main_lines.append(f"}} {scan_name};")
            main_lines.append("")
            feature_lookups.append(scan_name)
    else:
        for pos in range(MAX_LEN):
            scan_name = f"Scan{pos:02d}"
            main_lines.append(f"lookup {scan_name} useExtension {{")
            for code in SUPPORTED_CODES:
                a = f"SetByte_{code:03d}"
                b = f"SetLen_{code:03d}"
                main_lines.append(f"    sub {g_len(pos)}' lookup {a} {g_char(code)}' lookup {b};")
            main_lines.append(f"}} {scan_name};")
            main_lines.append("")
            feature_lookups.append(scan_name)

    # CloseQR
    if include_parity_circuit:
        matrix = derive_parity_matrix()
        main_lines.append("lookup CloseQR useExtension {")
        for length in range(MAX_LEN + 1):
            bit_fixed = fixed_parity_contribution(length, matrix)
            byte_fixed = bytes_from_bits(bit_fixed)
            rule_parts = []
            for j in range(EC_CODEWORDS):
                contrib = byte_fixed[j]
                if contrib:
                    rule_parts.append(f"@s{j}' lookup Xor_{contrib:03d}")
                else:
                    rule_parts.append(f"@s{j}' lookup NoOp")
            for k in range(1, length):
                rule_parts.append(f"@byte_{k:02d}' lookup NoOp")
            rule_parts.append(f"len_{length:02d}' lookup NoOp")
            rule_parts.append(f"close_delim' lookup SetBase_{length:02d}")
            main_lines.append(f"    sub {' '.join(rule_parts)};")
        main_lines.append("} CloseQR;")
        main_lines.append("")
        feature_lookups.append("CloseQR")

        main_lines.append("lookup CloseQR_CountTail useExtension {")
        for length in range(MAX_LEN + 1):
            main_lines.append(f"    sub len_{length:02d}' lookup SetCountTail_{length:02d} qr_base_{length:02d};")
        main_lines.append("} CloseQR_CountTail;")
        main_lines.append("")
        feature_lookups.append("CloseQR_CountTail")
    else:
        main_lines.append("lookup CloseQR useExtension {")
        for length in range(MAX_LEN + 1):
            main_lines.append(f"    sub {g_len(length)}' lookup Close{length:02d} close_delim' lookup HideClose;")
        main_lines.append("} CloseQR;")
        main_lines.append("")
        feature_lookups.append("CloseQR")

    # Add ExpandState to main_lines and feature_lookups
    if include_parity_circuit:
        main_lines.append("lookup ExpandState useExtension {")
        for j in range(EC_CODEWORDS):
            for val in range(256):
                bits = bits_of(val, 8)
                target_glyphs = [g_p(j * 8 + b, bit) for b, bit in enumerate(bits)]
                main_lines.append(f"    sub s{j}_{val:03d} by {' '.join(target_glyphs)};")
        main_lines.append("} ExpandState;")
        main_lines.append("")
        feature_lookups.append("ExpandState")

        # MergeAll
        main_lines.append("lookup MergeAll {")
        for bit in (0, 1):
            for length in range(MAX_LEN + 1):
                p55_name = g_p(PARITY_BITS - 1, bit)
                fused_name = f"qr_base_p55_{bit}_{length:02d}"
                main_lines.append(
                    f"    sub {p55_name} qr_base_{length:02d} by {fused_name};"
                )
        main_lines.append("} MergeAll;")
        main_lines.append("")
        feature_lookups.append("MergeAll")



    # Add main lines to all_lines
    all_lines.extend(main_lines)

    # 4. Feature sections
    all_lines.append("feature rlig {")
    for name in feature_lookups:
        all_lines.append(f"    lookup {name};")
    all_lines.append("} rlig;")
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
            "familyName": f"QR Font {QR_LABEL}",
            "styleName": "Regular",
            "uniqueFontIdentifier": f"QR Font {QR_LABEL} Regular 0.1",
            "fullName": f"QR Font {QR_LABEL} Regular",
            "psName": f"QRFont-{QR_LABEL}-Regular",
            "version": "Version 0.1",
            "copyright": (
                "Derived from Liberation Sans: digitized data copyright (c) 2010 "
                "Google Corporation; copyright (c) 2012 Red Hat, Inc. QR Font "
                "additions copyright their contributors. See https://qr.jim.sh/ for updates."
            ),
            "licenseDescription": "Licensed under the SIL Open Font License, Version 1.1.",
            "licenseInfoURL": "https://scripts.sil.org/OFL",
            "designerURL": "https://qr.jim.sh/",
            "vendorURL": "https://qr.jim.sh/",
        }
    )
    fb.setupPost(keepGlyphNames=True)
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

    for stale_font in DIST.glob("qrfont*.ttf"):
        stale_font.unlink()

    for label in ("1L", "2L", "3L"):
        configure_qr(label)
        print(f"building QR Font {label}...", flush=True)
        font_data = build_font_data(args.base_font)
        feature_text = generate_features(include_parity_circuit=not args.placeholder_parity)
        (BUILD / f"qrfont-{label}.fea").write_text(feature_text, encoding="utf-8")
        output_name = f"qrfont-{label}.ttf"
        build_ttf(font_data, feature_text, DIST / output_name)
        print(f"wrote {DIST / output_name}")


if __name__ == "__main__":
    main()
