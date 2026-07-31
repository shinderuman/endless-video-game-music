UV ?= uv
HOST ?= 0.0.0.0
PORT ?= 8765
LIBRARY_LOG ?= $(HOME)/Library/Caches/Endless Video Game Music/library-refresh.log

.PHONY: setup doctor library run open test lint format check

setup:
	@command -v $(UV) >/dev/null || { \
		echo "uv が必要です: https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	}
	$(UV) sync --extra dev
	$(MAKE) doctor

doctor:
	@command -v ffmpeg >/dev/null || { \
		echo "ffmpeg が必要です: brew install ffmpeg"; \
		exit 1; \
	}
	@command -v ffprobe >/dev/null || { \
		echo "ffprobe が必要です: brew install ffmpeg"; \
		exit 1; \
	}
	$(UV) run pymusiclooper --version
	$(UV) run endless-vgm --help >/dev/null
	@echo "依存関係は利用可能です。"

library:
	$(UV) run endless-vgm --refresh-library --library-log "$(LIBRARY_LOG)"

run:
	$(UV) run endless-vgm -H $(HOST) -p $(PORT)

open:
	$(UV) run endless-vgm -H $(HOST) -p $(PORT) -o

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

check: lint test
