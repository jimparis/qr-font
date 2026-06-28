.PHONY: all clean deploy
.PHONY: fast-placeholder full-parity

export UV_CACHE_DIR := .uv-cache

FONTS = dist/qrfont-1L.ttf dist/qrfont-2L.ttf dist/qrfont-3L.ttf
INDEX = dist/index.html

all: $(FONTS) $(INDEX)

$(FONTS): tools/build_font.py
	uv run tools/build_font.py

$(INDEX): tools/build_html.py
	uv run tools/build_html.py

fast-placeholder:
	uv run tools/build_font.py --placeholder-parity

deploy: all
	rsync -avz --delete dist/ psy:/www/qr/

full-parity: all

clean:
	rm -rf build dist .uv-cache
