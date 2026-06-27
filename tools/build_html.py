import argparse
from pathlib import Path

DIST = Path("/home/jim/git/qr-font/dist")

def write_demo(font_filenames: dict[str, str]) -> None:
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jim's TrueType QR Code Font</title>
<style>
@font-face {
  font-family: "QR Font 1-L";
  src: url("./__FONT_1L__") format("truetype");
}
@font-face {
  font-family: "QR Font 2-L";
  src: url("./__FONT_2L__") format("truetype");
}
@font-face {
  font-family: "QR Font 3-L";
  src: url("./__FONT_3L__") format("truetype");
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
select {
  margin-bottom: 14px;
  padding: 8px 10px;
  border: 1px solid #b7c0cc;
  border-radius: 6px;
  font: 15px system-ui, sans-serif;
}
.qr {
  margin-top: 32px;
  font-feature-settings: "rlig" 1, "kern" 1;
  line-height: 1;
  color: #000;
  background: #fff;
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-height: 222px;
  padding: 0;
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
.qr.mode-mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 18px;
  min-height: 198px;
  padding: 16px;
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
  <label for="mode">Font</label>
  <select id="mode">
    <option value="1L">QR Font 1-L (up to 17 characters)</option>
    <option value="2L" selected>QR Font 2-L (up to 32 characters)</option>
    <option value="3L">QR Font 3-L (up to 53 characters)</option>
    <option value="mono">Mono</option>
  </select>
  <label for="text">Text</label>
  <textarea id="text" autocomplete="off" spellcheck="false">Hello [QR coded] world!
Download this font: [http://qr.jim.sh/]</textarea>
  <p class="meta">Use printable ASCII inside square brackets. QR Font 1-L supports up to 17 characters per block; QR Font 2-L supports up to 32; QR Font 3-L supports up to 53. Text outside brackets remains ordinary Liberation Sans-derived text.</p>
  <div id="qr" class="qr mode-2L">Hello [QR coded] world!
Download this font: [http://qr.jim.sh/]</div>
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
function render() {
  const value = input.value;
  qr.replaceChildren(document.createTextNode(value));
  qr.className = `qr mode-${mode.value}`;
}
input.addEventListener("input", render);
input.addEventListener("change", render);
input.addEventListener("keyup", render);
mode.addEventListener("change", render);
render();
</script>
</body>
</html>
"""
    html = (
        html.replace("__FONT_1L__", font_filenames["1L"])
        .replace("__FONT_2L__", font_filenames["2L"])
        .replace("__FONT_3L__", font_filenames["3L"])
    )
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
