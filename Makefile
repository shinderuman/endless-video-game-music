UV ?= uv
MAKE ?= make
OPEN ?= open
CURL ?= curl
PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
SERVER_DIR ?= $(abspath ../local-web-app-server)
SERVER_BINARY ?= $(BINDIR)/local-web-app-server
SERVER_URL ?= http://127.0.0.1:8766
SERVER_LISTEN ?= 127.0.0.1:8766
LIBRARY_LOG ?= $(HOME)/Library/Caches/Endless Video Game Music/library-refresh.log

APPSDIR ?= $(HOME)/Library/Application Support/LocalWebAppServer/apps
APPDIR ?= $(APPSDIR)/endless-vgm
DISTDIR ?= dist/endless-vgm
APP_URL := $(SERVER_URL)/apps/endless-vgm/

.PHONY: setup doctor library install install-server install-app build-app start run open stop test lint format check clean

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
	@test -x "$(SERVER_BINARY)"
	@echo "依存関係は利用可能です。"

library:
	$(UV) run endless-vgm --refresh-library --library-log "$(LIBRARY_LOG)"

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

check: lint test

install: install-server install-app start

install-server:
	$(MAKE) -C "$(SERVER_DIR)" install PREFIX="$(PREFIX)"

install-app: build-app
	mkdir -p "$(APPSDIR)"
	rm -rf "$(APPDIR)"
	cp -R "$(DISTDIR)" "$(APPDIR)"

build-app:
	rm -rf "$(DISTDIR)"
	mkdir -p "$(DISTDIR)/bin" "$(DISTDIR)/web" "$(DISTDIR)/src"
	cp local-web-app.json pyproject.toml uv.lock README.md "$(DISTDIR)/"
	cp -R src/endless_vgm "$(DISTDIR)/src/"
	cp src/endless_vgm/static/* "$(DISTDIR)/web/"
	cp scripts/endless-vgm-backend "$(DISTDIR)/bin/endless-vgm"
	chmod 0755 "$(DISTDIR)/bin/endless-vgm"
	$(UV) sync --project "$(DISTDIR)" --no-dev

start:
	@"$(SERVER_BINARY)" --stop || true
	@nohup "$(SERVER_BINARY)" --listen "$(SERVER_LISTEN)" >/dev/null 2>&1 &
	@attempt=0; \
	while ! "$(CURL)" -fsS "$(APP_URL)api/status" >/dev/null 2>&1; do \
		attempt=$$((attempt + 1)); \
		if [ $$attempt -ge 100 ]; then \
			echo "Endless VGM backend did not become ready: $(APP_URL)" >&2; \
			exit 1; \
		fi; \
		sleep 0.1; \
	done
	@$(OPEN) "$(APP_URL)"
	@echo "Endless VGM: $(APP_URL)"

run: start

open:
	@$(OPEN) "$(APP_URL)"

stop:
	@"$(SERVER_BINARY)" --stop

clean:
	rm -rf dist
