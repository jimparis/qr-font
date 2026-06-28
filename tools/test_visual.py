#!/usr/bin/env python3
import subprocess
from pathlib import Path
import shutil

DIST = Path(__file__).resolve().parent.parent / "dist"
# Fallback for artifacts folder if home directory is different
home_dir = Path.home()
ARTIFACTS = home_dir / ".gemini/antigravity-cli/brain/b99818b3-5da0-4033-8da1-3a74b472fb71"
if not ARTIFACTS.exists():
    ARTIFACTS = Path("/tmp")
PROFILE_DIR = Path("/tmp/ff_test_prof")
TEST_HTML_PATH = Path("/tmp/test_visual.html")

def run_visual_test():
    # Clean old file from dist to avoid deploying it
    old_dist_html = DIST / "test_visual.html"
    if old_dist_html.exists():
        old_dist_html.unlink()

    # 1. Create test_visual.html in /tmp
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'QR Font 1-L';
  src: url('file://{DIST.absolute()}/qrfont-1L.ttf') format('truetype');
}}
@font-face {{
  font-family: 'QR Font 2-L';
  src: url('file://{DIST.absolute()}/qrfont-2L.ttf') format('truetype');
}}
body {{
  background: white;
  color: black;
  font-family: sans-serif;
  padding: 20px;
  margin: 0;
}}
.test-row {{
  margin-bottom: 40px;
}}
.label {{
  font-size: 16px;
  color: #555;
  margin-bottom: 5px;
}}
.qr {{
  font-family: 'QR Font 2-L';
  font-feature-settings: 'rlig' 1, 'kern' 1;
  background: white;
  color: black;
  line-height: 1.0;
  display: block;
}}
</style>
</head>
<body>
  <div class="test-row">
    <div class="label">Font Size: 50px</div>
    <div class="qr" style="font-size: 50px;">Hello [QR coded] world!</div>
  </div>
  <div class="test-row">
    <div class="label">Font Size: 100px</div>
    <div class="qr" style="font-size: 100px;">Hello [QR coded] world!</div>
  </div>
  <div class="test-row">
    <div class="label">Font Size: 150px</div>
    <div class="qr" style="font-size: 150px;">Hello [QR coded] world!</div>
  </div>
  <div class="test-row">
    <div class="label">Font Size: 200px</div>
    <div class="qr" style="font-size: 200px;">Hello [QR coded] world!</div>
  </div>
  <div class="test-row">
    <div class="label">Font Size: 250px</div>
    <div class="qr" style="font-size: 250px;">Hello [QR coded] world!</div>
  </div>
</body>
</html>
"""
    TEST_HTML_PATH.write_text(html, encoding="utf-8")
    
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    PROFILE_DIR.mkdir()
    
    screenshot_path = ARTIFACTS / "screenshot_ff.png"
    cmd = [
        "firefox",
        "--headless",
        "--window-size=1200,1600",
        "-no-remote",
        "-profile",
        str(PROFILE_DIR),
        "--screenshot",
        str(screenshot_path),
        f"file://{TEST_HTML_PATH.absolute()}"
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Screenshot saved to {screenshot_path}")

if __name__ == "__main__":
    run_visual_test()
