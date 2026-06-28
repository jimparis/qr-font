import argparse
from pathlib import Path
import hashlib

DIST = Path("/home/jim/git/qr-font/dist")

def file_hash(filepath: Path) -> str:
    if not filepath.exists():
        return "unknown"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8]

def write_demo(font_filenames: dict[str, str]) -> None:
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jim's TrueType QR Code Font</title>
<link rel="icon" type="image/x-icon" href="./favicon.ico">
<link rel="preload" href="./__FONT_1L__" as="font" type="font/ttf" crossorigin>
<link rel="preload" href="./__FONT_2L__" as="font" type="font/ttf" crossorigin>
<link rel="preload" href="./__FONT_3L__" as="font" type="font/ttf" crossorigin>
<style>
@font-face {
  font-family: "QR Font 1-L";
  src: url("./__FONT_1L__") format("truetype");
  font-display: block;
}
@font-face {
  font-family: "QR Font 2-L";
  src: url("./__FONT_2L__") format("truetype");
  font-display: block;
}
@font-face {
  font-family: "QR Font 3-L";
  src: url("./__FONT_3L__") format("truetype");
  font-display: block;
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
h1 {
  margin: 0 0 14px;
  font-size: 34px;
  line-height: 1.15;
}
p {
  line-height: 1.5;
}
.intro {
  max-width: 760px;
  margin: 0 0 28px;
  color: #334155;
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
textarea.apply-qr {
  font-feature-settings: "rlig" 1, "kern" 1;
}
textarea.apply-qr.mode-1L {
  font-family: "QR Font 1-L", system-ui, sans-serif;
}
textarea.apply-qr.mode-2L {
  font-family: "QR Font 2-L", system-ui, sans-serif;
}
textarea.apply-qr.mode-3L {
  font-family: "QR Font 3-L", system-ui, sans-serif;
}
textarea.apply-qr.mode-sans {
  font-family: "Liberation Sans", system-ui, sans-serif;
}
select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #b7c0cc;
  border-radius: 6px;
  font: 15px system-ui, sans-serif;
  box-sizing: border-box;
}
.control-row {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.control-group {
  flex: 1;
  min-width: 200px;
}
.slider-container {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 38px;
}
input[type="range"] {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #cbd5e1;
  outline: none;
  -webkit-appearance: none;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #0f5fb8;
  cursor: pointer;
  transition: transform 0.1s ease;
}
input[type="range"]::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}
input[type="number"] {
  width: 65px;
  padding: 6px 8px;
  border: 1px solid #b7c0cc;
  border-radius: 6px;
  font: 15px system-ui, sans-serif;
  text-align: center;
  box-sizing: border-box;
}
.font-size-control {
  transition: opacity 0.2s ease;
}
.qr {
  margin-top: 32px;
  font-feature-settings: "rlig" 1, "kern" 1;
  line-height: 1.2;
  color: #000;
  background: #fff;
  display: block;
  box-sizing: content-box;
  width: 100%;
  min-height: 222px;
  padding: 12px 16px;
  overflow-x: auto;
  overflow-y: auto;
  white-space: pre-wrap;
}
.qr.mode-1L {
  font-family: "QR Font 1-L";
  font-size: 203px;
  min-height: 203px;
}
.qr.mode-2L {
  font-family: "QR Font 2-L";
  font-size: 198px;
  min-height: 198px;
}
.qr.mode-3L {
  font-family: "QR Font 3-L";
  font-size: 222px;
  min-height: 222px;
}
.qr.mode-sans {
  font-family: "Liberation Sans", system-ui, -apple-system, sans-serif;
}
.meta {
  margin-top: 10px;
  color: #4b5563;
  font-size: 14px;
}
.links {
  margin-top: 28px;
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}
a {
  color: #0f5fb8;
}
</style>
</head>
<body>
<main>
  <h1>Jim's TrueType QR Code Font</h1>
  <p class="intro">This is a real TrueType/OpenType font that turns bracketed text into QR codes during text shaping. There is no separate image generation or preprocessing step: type text like <code>[hello]</code>, apply the font, and the font's built-in OpenType rules render the QR code.</p>
  <p class="intro">Because the QR code is still text, you can copy and paste the rendered QR block as ordinary characters, store it in plain text, or mix it inline with regular Latin text. Text outside brackets remains readable.</p>
  <p class="intro"><strong>Browser Line-Wrapping Note:</strong> Because layout engines perform line-breaking on the Unicode text before shaping, browsers may split a QR code across lines if it contains break opportunities (like spaces, dots, or slashes) and hits the edge of a text container. For reliable rendering in HTML, wrap the bracketed block in a container styled with <code>white-space: nowrap;</code> or <code>display: inline-block;</code>.</p>
  <div class="control-row">
    <div class="control-group">
      <label for="mode">Font</label>
      <select id="mode">
        <option value="1L">QR Font 1-L (up to 17 characters)</option>
        <option value="2L" selected>QR Font 2-L (up to 32 characters)</option>
        <option value="3L">QR Font 3-L (up to 53 characters)</option>
        <option value="sans">Plain Sans (no QR parsing)</option>
      </select>
    </div>
    <div class="control-group font-size-control">
      <label for="size-slider">Font Size</label>
      <div class="slider-container">
        <input type="range" id="size-slider" min="10" max="300" value="100">
        <input type="number" id="size-input" min="10" max="300" value="100">
        <span style="font-size: 15px; color: #4b5563;">px</span>
      </div>
    </div>
    <div class="control-group">
      <label for="apply-input-font">Direct Input Font</label>
      <div style="height: 38px; display: flex; align-items: center;">
        <label style="font-weight: normal; margin-bottom: 0; display: flex; align-items: center; gap: 8px; cursor: pointer;">
          <input type="checkbox" id="apply-input-font">
          Apply QR font to textbox
        </label>
      </div>
    </div>
  </div>
  <label for="text">Text</label>
  <textarea id="text" autocomplete="off" spellcheck="false">Hello [QR coded] world!
This page: [http://qr.jim.sh/]</textarea>
  <p class="meta">Use printable ASCII inside square brackets. QR Font 1-L supports up to 17 characters per block; QR Font 2-L supports up to 32; QR Font 3-L supports up to 53. Text outside brackets remains ordinary Liberation Sans-derived text.</p>
  <div id="qr" class="qr mode-2L">Hello [QR coded] world!
This page: [http://qr.jim.sh/]</div>
  <p class="links">
    <a href="./__FONT_1L__">Download QR Font 1-L</a>
    <a href="./__FONT_2L__">Download QR Font 2-L</a>
    <a href="./__FONT_3L__">Download QR Font 3-L</a>
    <a href="https://git.jim.sh/jim/qr-font.git">Source repository</a>
  </p>
</main>
<script>
const input = document.getElementById("text");
const mode = document.getElementById("mode");
const qr = document.getElementById("qr");
const sizeSlider = document.getElementById("size-slider");
const sizeInput = document.getElementById("size-input");
const sizeControl = document.querySelector(".font-size-control");

function updateSize(value) {
  sizeSlider.value = value;
  sizeInput.value = value;
  qr.style.fontSize = value + "px";
  qr.style.minHeight = value + "px";
  if (applyInputFont.checked) {
    input.style.fontSize = value + "px";
  }
}

sizeSlider.addEventListener("input", (e) => updateSize(e.target.value));
sizeInput.addEventListener("input", (e) => {
  let val = parseInt(e.target.value, 10);
  if (isNaN(val)) return;
  if (val < 10) val = 10;
  if (val > 300) val = 300;
  updateSize(val);
});

function render() {
  const value = input.value;
  qr.replaceChildren(document.createTextNode(value));
  qr.className = `qr mode-${mode.value}`;
  qr.style.fontSize = sizeSlider.value + "px";
  qr.style.minHeight = sizeSlider.value + "px";
}

input.addEventListener("input", render);
input.addEventListener("change", render);
input.addEventListener("keyup", render);
mode.addEventListener("change", render);

const applyInputFont = document.getElementById("apply-input-font");
function updateInputFont() {
  if (applyInputFont.checked) {
    input.className = `apply-qr mode-${mode.value}`;
    input.style.fontSize = sizeSlider.value + "px";
    input.style.lineHeight = "1.2";
    qr.style.display = "none";
  } else {
    input.className = "";
    input.style.fontSize = "";
    input.style.lineHeight = "";
    qr.style.display = "block";
  }
}
applyInputFont.addEventListener("change", updateInputFont);
mode.addEventListener("change", updateInputFont);

render();
updateInputFont();
</script>
</body>
</html>
"""
    for label, filename in font_filenames.items():
        font_path = DIST / filename
        h = file_hash(font_path) if font_path.exists() else "0"
        html = html.replace(f"./__FONT_{label}__", f"./{filename}?h={h}")
        html = html.replace(f"__FONT_{label}__", filename)
    (DIST / "index.html").write_text(html, encoding="utf-8")

def main() -> None:
    font_filenames = {
        "1L": "qrfont-1L.ttf",
        "2L": "qrfont-2L.ttf",
        "3L": "qrfont-3L.ttf",
    }
    DIST.mkdir(exist_ok=True)
    write_demo(font_filenames)
    print(f"wrote {DIST / 'index.html'}")

if __name__ == "__main__":
    main()
