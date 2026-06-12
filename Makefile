# LitePaperReader Makefile
.PHONY: install install-all test test-cov lint clean build-exe docker

# Installation
install:
	pip install -e .

install-all:
	pip install -e .[all]

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=litepaperreader --cov-report=term-missing

# Code quality
lint:
	ruff check litepaperreader/

# Cleanup
clean:
	rm -rf build/ dist/ .pytest_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Build
build-exe:
	python build_exe.py

# Docker
docker:
	docker-compose up --build

# Release helpers
dist:
	python -m build
