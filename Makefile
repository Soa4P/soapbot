# soapbot developer entry points.
#
# The point of this file is that a contributor never has to read a document to
# find the right command. Every target here is also what CI runs, so "works on my
# machine" and "passes in CI" are the same command rather than two similar ones.

PY ?= python
VENV ?= .venv
ifeq ($(OS),Windows_NT)
	BIN := $(VENV)/Scripts
else
	BIN := $(VENV)/bin
endif

.PHONY: help venv install dev test lint fmt typecheck contrast check webui build ui run doctor clean check-deps progress deploy-check

help:
	@echo "make install    创建虚拟环境并安装开发依赖"
	@echo "make test       运行全部后端测试"
	@echo "make lint       静态检查（ruff）"
	@echo "make fmt        自动格式化 + 修可修问题"
	@echo "make typecheck  mypy（当前基线非零，非阻断）"
	@echo "make contrast   WCAG 对比度校验（含在 check 内）"
	@echo "make check      lint + contrast + test（CI 阻断项同款）"
	@echo "make deploy-check 容器部署配置静态检查（不需要 docker）"
	@echo "make ui         构建前端到 src/soapbot/webui/dist"
	@echo "make progress   启动开发进度看板 http://127.0.0.1:8099/"
	@echo "make run        启动服务（自动先构建前端）"
	@echo "make doctor     部署姿态检查"

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e ".[dev]"

# Editable install over a wheel on purpose: the panel is served from
# `src/soapbot/webui/dist`, so a build there is picked up without reinstalling.
dev: install ui

test:
	$(BIN)/python -m pytest -q

lint:
	$(BIN)/python -m ruff check src tests

fmt:
	$(BIN)/python -m ruff check --fix src tests
	$(BIN)/python -m ruff format src tests

typecheck:
	$(BIN)/python -m mypy src

contrast:
	$(BIN)/python scripts/check_contrast.py

# The board is a static page; this is the shortest way to look at it without
# remembering the flags. Must be HTTP — `file://` blocks the fetch of progress.json.
progress:
	@echo "http://127.0.0.1:8099/  (Ctrl+C 停止)"
	$(BIN)/python -m http.server 8099 --directory docs/progress

# `check` is what CI gates on: lint + tests. Type checking stays separate because its
# baseline is not clean yet (42 pre-existing errors); folding it in would make
# `make check` fail on a correct change and train people to ignore the target.
# Contrast rides along with `check` because it is the one accessibility rule that can
# be verified mechanically. Auditing focus order or ARIA still needs a human; a
# palette regression does not, and a palette regression is what actually happens.
check: lint contrast test

# `npm ci` when a lockfile exists so CI and a fresh clone resolve identically.
webui:
	cd webui && (test -f package-lock.json && npm ci || npm install)

ui: webui
	cd webui && npm run build

build:
	$(BIN)/python -m build

run: ui
	$(BIN)/python -m soapbot.cli start

doctor:
	$(BIN)/python -m soapbot.cli doctor

# Fails when requirements.txt and pyproject.toml disagree, so the two cannot drift
# silently — a stale requirements.txt is how a deployment ends up running a
# dependency set nobody tested.
check-deps:
	$(PY) scripts/check_deps.py

# Container config cannot be *executed* here (no docker on this machine), but the
# mistakes that make `compose up` fail are findable without a daemon — and two of them
# were present until this target existed. Pass MIRROR=... on a host that needs one.
MIRROR ?=
deploy-check:
	$(BIN)/python scripts/check_deploy.py $(if $(MIRROR),--mirror $(MIRROR),)

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
