.PHONY: install seed run test lint typecheck e2e demo clean

install:
	pip install -e ".[dev]"

seed:
	python -m paari.seed

run:
	uvicorn paari.main:app --reload --host 127.0.0.1 --port 8000

test:
	python -m pytest -q

lint:
	python -m ruff check paari tests scripts

typecheck:
	python -m mypy paari

e2e:
	python -m pytest tests/test_e2e.py -q

demo:
	python scripts/buyer_flow.py

clean:
	rm -f paari.db tests/_test_*.db
