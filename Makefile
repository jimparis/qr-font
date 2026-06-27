.PHONY: all clean deploy
.PHONY: fast-placeholder full-parity

export UV_CACHE_DIR := .uv-cache

FONTS = dist/qrfont-1L.ttf dist/qrfont-2L.ttf
INDEX = dist/index.html

all: $(FONTS) $(INDEX)
	mkdir -p $(HOME)/Downloads/qrfont
	rm -f $(HOME)/Downloads/qrfont/qrfont*.ttf
	cp dist/qrfont*.ttf dist/index.html dist/favicon.ico LICENSE-OFL.txt NOTICE.md $(HOME)/Downloads/qrfont/

$(FONTS): tools/build_font.py
	uv run tools/build_font.py

$(INDEX): tools/build_html.py
	uv run tools/build_html.py

fast-placeholder:
	uv run tools/build_font.py --placeholder-parity
	mkdir -p $(HOME)/Downloads/qrfont
	rm -f $(HOME)/Downloads/qrfont/qrfont*.ttf
	cp dist/qrfont*.ttf dist/index.html dist/favicon.ico LICENSE-OFL.txt NOTICE.md $(HOME)/Downloads/qrfont/

deploy: all
	rsync -avz dist/ psy:/www/qr/

full-parity: all

clean:
	rm -rf build dist .uv-cache
