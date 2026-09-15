.PHONY: dev test lint install

install:
	.venv\Scripts\pip install -r requirements.txt

dev:
	.venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	.venv\Scripts\pytest tests/ -v

lint:
	.venv\Scripts\ruff check app/ tests/
