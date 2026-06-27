.PHONY: all clean
.PHONY: fast-placeholder full-parity

export UV_CACHE_DIR := .uv-cache

all:
	uv run tools/build_font.py
	mkdir -p $(HOME)/Downloads/qrfont
	rm -f $(HOME)/Downloads/qrfont/qrfont*.ttf
	cp dist/qrfont*.ttf dist/demo.html dist/reference.html LICENSE-OFL.txt NOTICE.md $(HOME)/Downloads/qrfont/

fast-placeholder:
	uv run tools/build_font.py --placeholder-parity
	mkdir -p $(HOME)/Downloads/qrfont
	rm -f $(HOME)/Downloads/qrfont/qrfont*.ttf
	cp dist/qrfont*.ttf dist/demo.html dist/reference.html LICENSE-OFL.txt NOTICE.md $(HOME)/Downloads/qrfont/

full-parity: all

clean:
	rm -rf build dist .uv-cache
