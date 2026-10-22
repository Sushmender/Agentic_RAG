.PHONY: dev test lint install

install:
	.venv\Scripts\pip install -r requirements.txt

HOST ?= 127.0.0.1
PORT ?= 8000

dev:
	.venv\Scripts\uvicorn.exe app.main:app --reload --host $(HOST) --port $(PORT)

test:
	.venv\Scripts\pytest tests/ -v

lint:
	.venv\Scripts\ruff check app/ tests/
