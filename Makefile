PYTHON ?= python3

.PHONY: test coverage compile build smoke clean

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

coverage:
	PYTHONPATH=src $(PYTHON) -m pytest --cov=rss_publisher --cov-report=term-missing

compile:
	$(PYTHON) -m compileall -q src tests

build:
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation -w dist .

smoke:
	PYTHONPATH=src $(PYTHON) scripts/smoke_core.py

clean:
	rm -rf .pytest_cache .coverage htmlcov build dist src/*.egg-info src/rss_publisher_mcp.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
