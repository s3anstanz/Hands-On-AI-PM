# make course   start the tutorial (options: make course ARGS="--lesson 2")
# make setup    one-time setup: create .venv and install requirements.txt

PYTHON ?= .venv/bin/python
SYSTEM_PYTHON ?= python3
ARGS ?=

.PHONY: course setup

course:
	@test -x $(PYTHON) || { echo "Not set up yet. Run: make setup"; exit 1; }
	@$(PYTHON) tutorial.py $(ARGS)

setup:
	@$(SYSTEM_PYTHON) -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "The tutorial needs Python 3.11 or newer, but python3 here is $$($(SYSTEM_PYTHON) --version 2>&1)."; echo "Install a newer Python from https://www.python.org/downloads/ and run make setup again."; exit 1; }
	$(SYSTEM_PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt
