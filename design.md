Yes. The practical approach is to treat the font as a **compiled finite circuit**, not as one enormous ligature table.

A `.ttf` can contain OpenType `GSUB` tables. Those tables support one-to-many substitutions, contextual substitutions, and ordered sequences of lookups where later operations consume the output of earlier ones. That is enough to implement a bounded computation by unrolling every step in advance. ([Microsoft Learn][1])

## Define a manageable target

For a first implementation, I would constrain it to:

* QR Version 1-L: 21×21 modules
* ASCII byte mode
* Zero to 17 input characters
* One fixed legal mask pattern
* Input written as something like `⟦hello⟧`
* OpenType shaping enabled

Version 1-L has 152 data bits and can hold 17 byte-mode characters. It uses 19 data codewords followed by 7 Reed–Solomon error-correction codewords. ([QRCode][2])

The explicit delimiters matter because OpenType does not provide a convenient, universally reliable “this is the beginning/end of the shaping run” test.

## 1. Turn the text into a position-tagged byte sequence

The opening delimiter expands into:

```text
0100              Byte-mode indicator
????????          Eight character-count placeholders
LEN_0             A scanning-state glyph
```

The text initially looks internally like:

```text
D0_0 D1_1 D2_0 D3_0 C0 C1 ... C7 LEN_0 h e l l o END
```

Each of 17 ordered contextual lookups advances the length-state glyph through one character:

```text
LEN_0 h  → BYTE_0_h LEN_1
LEN_1 e  → BYTE_1_e LEN_2
LEN_2 l  → BYTE_2_l LEN_3
...
```

This is implemented as two simultaneous substitutions: the state position becomes the tagged character, while the character position becomes the next state. It is effectively a swap, although GSUB is only changing glyph identities.

After scanning:

```text
header BYTE_0_h BYTE_1_e BYTE_2_l BYTE_3_l BYTE_4_o LEN_5 END
```

If an eighteenth character appears, no rule matches and the font can render an error symbol instead.

## 2. Fill in the character-count field

Eight contextual lookups inspect the final `LEN_n` glyph and turn the count placeholders into the appropriate bits.

For length 5:

```text
C0 C1 C2 C3 C4 C5 C6 C7
↓
0  0  0  0  0  1  0  1
```

Each resulting glyph is position-tagged, such as:

```text
D4_0 D5_0 ... D11_1
```

The position tag is important because it eventually tells the glyph where its QR module belongs.

## 3. Expand each character into eight bits

A multiple-substitution lookup converts each tagged byte glyph into eight data-bit glyphs:

```text
BYTE_0_h
    → D12_0 D13_1 D14_1 D15_0 D16_1 D17_0 D18_0 D19_0
```

That is the ASCII value `0x68`.

There would be a mapping for every supported character at every possible character position. For 128 ASCII characters and 17 positions, that is 2,176 input glyph mappings—not small, but entirely reasonable for a generated font.

OpenType explicitly supports replacing one glyph with a sequence of glyphs. ([Microsoft Learn][1])

## 4. Generate terminator and padding

The final length state determines exactly how many bits remain.

For each possible length, the closing delimiter expands into the appropriate combination of:

* Up to four terminator zero bits
* Zero bits needed to reach a byte boundary
* Alternating `0xEC` and `0x11` pad codewords
* Fifty-six parity accumulator glyphs initialized to zero
* One final base/output glyph

The resulting sequence has a fixed shape:

```text
D0 ... D151 P0 ... P55 QR_BASE
```

Every data position and parity position has its own glyph identity.

## 5. Compute Reed–Solomon error correction as XOR circuitry

This is the interesting part.

It is unnecessary to implement polynomial division and `GF(256)` arithmetic directly inside the font. For a fixed QR version and error-correction level, the 56 parity bits are a fixed **linear transformation** of the 152 data bits:

```text
parity = M × data     over GF(2)
```

I would derive the 56×152 binary matrix `M` offline:

1. Feed a reference QR encoder 152 test vectors.
2. In test vector `i`, set only data bit `i`.
3. Record the resulting 56 parity bits.
4. That result is column `i` of the matrix.

Then generate one contextual lookup for each data bit.

Conceptually:

```text
when D37 is 1:
    toggle P2
    toggle P5
    toggle P8
    toggle P11
    ...
```

Each lookup matches the entire fixed 208-cell sequence, constraining only the relevant source bit to `1`. Nested substitutions toggle every parity glyph selected by that matrix column:

```text
P7_0 → P7_1
P7_1 → P7_0
```

After all 152 lookups have run, `P0` through `P55` contain the correct Reed–Solomon parity.

This works because OpenType lookups are applied in defined order, and each lookup operates on the glyph sequence produced by all preceding lookups. Contextual lookups can invoke substitution actions at particular positions within the matched sequence. ([Microsoft Learn][3])

This would involve roughly:

* 152 large contextual parity lookups
* About 4,000 parity-toggle actions
* A few thousand intermediate glyphs

That is cumbersome but not absurd.

## 6. Render the one-dimensional glyph sequence as a 2D QR code

No complicated positioning is actually required.

Every bit-position glyph has two versions:

```text
D37_0
D37_1
```

Their outlines are defined according to the module location assigned to data bit 37:

* One variant has no outline.
* The other contains a filled square at that module’s `(x,y)` coordinates.
* Which variant is black is reversed when the fixed mask bit at that coordinate is 1.

All these glyphs have zero advance width, so they are drawn on top of one another at the same origin.

`QR_BASE`, placed last, contains:

* Finder patterns
* Separators
* Timing patterns
* Dark module
* Fixed error-correction/mask format bits
* The final nonzero advance width
* Space for the quiet zone

The rendered result is therefore the union of hundreds of tiny glyph outlines.

GPOS could position generic square glyphs instead, but putting the final coordinate directly into each glyph outline is simpler. GPOS does provide precise per-glyph positioning if that route is preferred. ([Microsoft Learn][4])

## What the generated feature logic would resemble

Not exact feature-file syntax, but structurally:

```text
lookup ScanCharacter0 {
    sub LEN_0' a' lookup PutByte0A lookup PutLen1;
    sub LEN_0' b' lookup PutByte0B lookup PutLen1;
    ...
} ScanCharacter0;

lookup ExpandBytes {
    sub BYTE_0_A by D12_0 D13_1 D14_0 D15_0
                    D16_0 D17_0 D18_0 D19_1;
    ...
} ExpandBytes;

lookup ApplyDataBit37 {
    sub @D0 @D1 ... D37_1 ... @D151
        P0 P1 P2' lookup ToggleP2
        P3 P4 P5' lookup ToggleP5
        ...
        P55;
} ApplyDataBit37;
```

I would generate the glyph set and `.fea` source with Python, then compile it using `fontTools.feaLib`, which can turn feature definitions into the font’s GSUB and GPOS tables. ([fonttools.readthedocs.io][5])

## What hinting contributes

TrueType hinting bytecode really can perform substantial computation. It has arithmetic, conditionals, functions, storage and coordinate-manipulation instructions. A 2026 demonstration even implemented a raycaster in the TrueType hinting VM. ([Microsoft Learn][6])

But hinting is the wrong primary mechanism here:

* It normally executes on individual glyphs.
* It does not naturally receive the surrounding Unicode string.
* Glyph execution order and shared state are not a safe text-input channel.
* Rasterizers may disable or alter hinting behavior.

So I would use:

```text
GSUB = parse and compute
glyf outlines = display
hinting = optional pixel alignment
```

## Extending it beyond the prototype

A more complete font could add:

* Versions 1 through perhaps 4
* UTF-8 encoding
* L/M/Q/H error-correction choices selected by delimiters
* All eight masks
* Actual mask-penalty calculation
* Numeric and alphanumeric modes
* An error glyph for unsupported input

Automatic mask selection is possible using more unrolled Boolean circuitry, but it would probably exceed the Reed–Solomon portion in complexity. For the initial font, choosing a fixed mask and baking its format bits and coordinate inversions into the glyphs is far simpler.

So the basic answer is: **compile a fixed-capacity QR encoder into thousands of ordered contextual substitutions, represent every intermediate bit as a glyph identity, and overlay position-specific square outlines to produce the final matrix.** It is not an unrestricted program running inside ordinary OpenType, but for a bounded input size it is a legitimate and implementable finite computation.

[1]: https://learn.microsoft.com/en-us/typography/opentype/otspec180/gsub?utm_source=chatgpt.com "GSUB — Glyph Substitution Table (OpenType 1.8) - Typography | Microsoft Learn"
[2]: https://www.qrcode.com/en/about/version.html?utm_source=chatgpt.com "Information capacity and versions of QR Code | QRcode.com"
[3]: https://learn.microsoft.com/en-us/typography/opentype/spec/gsub?utm_source=chatgpt.com "GSUB — Glyph Substitution Table (OpenType 1.9.1) - Typography | Microsoft Learn"
[4]: https://learn.microsoft.com/en-us/typography/opentype/spec/gpos?utm_source=chatgpt.com "GPOS — Glyph Positioning Table (OpenType 1.9.1)"
[5]: https://fonttools.readthedocs.io/en/latest/feaLib/index.html?highlight=baseline&utm_source=chatgpt.com "feaLib: Read and write OpenType feature files — fontTools Documentation"
[6]: https://learn.microsoft.com/en-us/typography/truetype/hinting?utm_source=chatgpt.com "TrueType hinting - Typography | Microsoft Learn"

