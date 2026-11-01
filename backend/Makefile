.PHONY: dev test lint install

install:
	.venv\Scripts\pip install -r requirements.txt

HOST ?= 127.0.0.1
PORT ?= 8000
export HOST
export PORT

dev:
	.venv\Scripts\python run.py

test:
	.venv\Scripts\pytest tests/ -v

lint:
	.venv\Scripts\ruff check app/ tests/
